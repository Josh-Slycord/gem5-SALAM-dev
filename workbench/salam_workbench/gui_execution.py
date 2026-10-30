"""Apply live GUI requests through generation, optional rebuild and real gem5.

Only independent local engine copies are used. Source benchmark YAML is an
immutable input; edited documents are staged inside each experiment workspace.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import sys
import uuid

import yaml

from .configurator import (PROJECT, _record, _relative, stage_configuration,
                           run_configuration, validate_spec, verify_engine)
from .config_contract import analyze_configuration, _Loader
from .configuration_import import import_configuration
from .configurator_gui_bridge import _verify_generated_outputs
from .regression import _save
from .runner import file_hash
from .fu_capability import (inspect_fu_capability, requested_fu_capacity,
                            validate_limit_parameters)

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _summarize_fu_witness(witness):
    """Compact only independently replayed, complete direct SALAM FU traces."""
    if witness is None:
        return None
    if not isinstance(witness, dict) or witness.get('state') != 'passed':
        raise ValueError('FU scheduling witness did not pass')
    invocations = witness.get('invocations')
    if not isinstance(invocations, list) or not invocations:
        raise ValueError('FU scheduling witness has no invocations')
    summary = []
    counters = ('attempts', 'grants', 'denials', 'releases', 'peak', 'outstanding')
    for invocation in invocations:
        trace = invocation.get('trace') if isinstance(invocation, dict) else None
        if (invocation.get('state') != 'passed' or not isinstance(trace, dict)
                or trace.get('state') != 'passed'
                or trace.get('trace_complete') is not True):
            raise ValueError('FU invocation lacks a complete validated replay')
        path = Path(invocation.get('path', ''))
        name = path.name
        if not name.startswith('fu-scheduling-') or '.invocation-' not in name:
            raise ValueError('FU invocation path has no validated identity')
        accelerator = name[len('fu-scheduling-'):].split('.invocation-', 1)[0]
        units = []
        for unit in trace.get('units', []):
            if not isinstance(unit, dict) or not isinstance(unit.get('name'), str):
                raise ValueError('FU replay unit is incomplete')
            if type(unit.get('limit')) is not int or unit['limit'] < 0:
                raise ValueError('FU replay limit is invalid')
            values = {key: unit.get(key) for key in counters}
            if any(type(value) is not int or value < 0 for value in values.values()):
                raise ValueError('FU replay counter is invalid')
            if not (unit['limit'] or values['grants'] or values['denials']):
                continue
            units.append({'name': unit['name'], 'limit': unit['limit'], **values})
        summary.append({'accelerator': accelerator,
                        'source_path': str(path),
                        'source_sha256': invocation.get('source_sha256'),
                        'units': units})
    return {'state': 'validated_direct_salam_trace', 'invocations': summary}


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_request(text):
    if len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('GUI request exceeds 2 MiB')
    return json.loads(text, object_pairs_hook=_json_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def validate_request(request, project=PROJECT):
    allowed = {'schema_version', 'action', 'benchmark', 'engine_root', 'distro',
               'configuration_documents', 'system', 'parameters', 'base_address',
               'hardware_profile', 'provenance'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError('Unknown GUI request fields')
    if request.get('schema_version') != 2 or request.get('action') != 'apply_and_run':
        raise ValueError('Expected live GUI apply_and_run schema 2')
    json.dumps(request, allow_nan=False)
    manifest = json.loads((Path(project) / 'workspace.json').read_text(encoding='utf-8-sig'))
    configuration = manifest['configuration_engine']
    base = Path(configuration['path']).resolve(strict=True)
    if Path(request['engine_root']).resolve(strict=True) != base:
        raise ValueError('GUI may apply only to the configured independent base engine')
    if request.get('distro') != configuration['distribution']:
        raise ValueError('GUI distribution does not match the independent engine')
    benchmark = _relative(request.get('benchmark'))
    if len(benchmark.parts) != 3 or benchmark.parts[0] != 'benchmarks':
        raise ValueError('GUI benchmark must identify one existing suite/workload')
    source = request.get('provenance', {}).get('source_config', {})
    relative = _relative(source.get('relative_path'))
    if relative.parent != benchmark or relative.name not in ('config.yml', 'config.yaml'):
        raise ValueError('GUI source config must belong to the selected benchmark')
    source_path = (base / relative).resolve(strict=True)
    source_path.relative_to(base)
    if source_path.is_symlink() or file_hash(source_path) != source.get('sha256'):
        raise ValueError('Loaded GUI source YAML changed; reload before applying')
    editor = request.get('provenance', {}).get('editor_snapshot')
    if not isinstance(editor, dict) or editor.get('alignment') != 64:
        raise ValueError('A live widget snapshot with supported 64-byte alignment is required')
    from .gui_editor import build_gui_request
    originals = list(yaml.load_all(source_path.read_text(), Loader=_Loader))
    if len(originals) != 1:
        raise ValueError('GUI editor currently requires a single source YAML document')
    reconstructed = build_gui_request(originals[0], editor, benchmark=request['benchmark'],
                      engine_root=request['engine_root'], distro=request['distro'],
                      source_config_relative=source['relative_path'], source_config_sha256=source['sha256'])
    for key in allowed - {'provenance'}:
        if request.get(key) != reconstructed.get(key):
            raise ValueError('GUI request differs from the actual widget snapshot: ' + key)
    profile = request.get('hardware_profile')
    if not isinstance(profile, dict) or set(profile) - {'model', 'period', 'profile', 'fu_overrides'}:
        raise ValueError('Invalid hardware profile selection')
    for key in ('model', 'period', 'profile'):
        if not isinstance(profile.get(key), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', profile[key]):
            raise ValueError('Invalid hardware profile ' + key)
    from .hardware_codegen import _normalize_profile_overrides
    capable = inspect_fu_capability(base)['supported']
    _normalize_profile_overrides(profile.get('fu_overrides', {}),
                                 allow_fu_limit=capable)
    validate_limit_parameters(base, request.get('parameters', {}))
    return base, configuration, source_path


def normalize_request(request, engine, directory):
    raw = directory / 'request-configuration.yml'
    raw.write_text(yaml.safe_dump_all(request['configuration_documents'], sort_keys=False))
    imported = import_configuration(raw, engine)
    normalization = {
        'schema_version': 1, 'raw_request_sha256': file_hash(directory / 'request.json'),
        'configuration_documents_before': request['configuration_documents'],
        'configuration_documents_after': imported['documents'],
        'transformations': imported['transformations'], 'consumer_sources': imported['consumer_sources'],
        'source': imported['source'],
    }
    _save(directory / 'normalization.json', normalization)
    spec = {'schema_version': 1, 'name': Path(request['benchmark']).name,
            'benchmark': request['benchmark'], 'config': request['provenance']['source_config']['relative_path'],
            'configuration_documents': imported['documents'], 'system': request.get('system', {}),
            'parameters': request.get('parameters', {}), 'base_address': request['base_address'],
            'correctness': {'expected_passed_markers': 1,
                            'description': 'Real benchmark guest checker; numerical acceptance and configuration transport are assessed separately'}}
    validate_spec(spec)
    _save(directory / 'normalized-specification.json', spec)
    return spec, normalization


def apply_request(request, *, project=PROJECT, evidence_dir=None,
                  variant_parent=None, jobs=8, progress=None):
    project = Path(project).resolve(strict=True)
    directory = Path(evidence_dir).resolve() if evidence_dir else project / 'evidence' / (
        'gui-apply-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    receipt = {'schema_version': 1, 'kind': 'salam_gui_execution', 'state': 'running',
               'stage': 'request_validation', 'evidence_directory': str(directory),
               'started_at': _now(), 'errors': [], 'editor_form_applied': False,
               'simulation_requested': True, 'official_repositories_changed': False}

    def stage(name, **values):
        receipt['stage'] = name
        receipt.update(values)
        _save(directory / 'gui-execution.json', receipt)
        if progress:
            progress({'kind': 'gui_progress', 'stage': name, 'evidence_directory': str(directory)})

    stage('request_validation')
    try:
        _save(directory / 'request.json', request)
        base, configuration, source_path = validate_request(request, project)
        selected_variant_parent = (Path(variant_parent) if variant_parent is not None
                                   else base.parent / 'gui-variants')
        receipt['source_config'] = _record(source_path)
        receipt['workspace_manifest'] = _record(project / 'workspace.json')
        base_build = project / configuration['build_receipt']
        base_generation = project / configuration['generation_receipt']
        receipt['base_build'] = verify_engine(base, base_build)
        baseline_generation = json.loads(base_generation.read_text())
        _verify_generated_outputs(base, baseline_generation)
        stage('normalizing_live_widgets')
        spec, normalization = normalize_request(request, base, directory)
        stage('preflight_configuration')
        preflight = directory / 'preflight'
        staging = stage_configuration(base, preflight, spec)
        from .topology_adapter import adapt_staged_configpaths
        adapter = adapt_staged_configpaths(base, preflight, spec['benchmark'],
                 receipt_path=directory / 'preflight-configpaths.json', source_config_relative=spec['config'])
        contract = analyze_configuration(preflight / spec['benchmark'] / 'config.yml', preflight,
                       base_address=int(str(spec['base_address']), 0))
        _save(directory / 'preflight-contract.json', contract)
        if not contract['valid']:
            raise ValueError('Edited GUI configuration is not consumed: ' + repr(contract['issues']))
        receipt['regeneration_plan'] = {'topology_python_and_address_headers': True,
                                      'guest_elf_and_accelerator_ir': True,
                                      'simulator_rebuild': False}
        profile = request['hardware_profile']
        same_profile = (not profile.get('fu_overrides') and all(
            profile.get(key) == baseline_generation['selection'].get(key)
            for key in ('model', 'period', 'profile')) and
            baseline_generation['selection'].get('benchmark') == Path(spec['benchmark']).name)
        if same_profile:
            stage('reusing_verified_simulator')
            engine, build_path, generation_path = base, base_build, base_generation
            receipt['hardware'] = {'state': 'reused_base', 'engine_path': str(base),
                                  'build_receipt': str(build_path), 'generation_receipt': str(generation_path)}
        else:
            receipt['regeneration_plan']['simulator_rebuild'] = True
            stage('generating_and_building_hardware')
            from .hardware_variants import ensure_hardware_variant
            variant = ensure_hardware_variant(base, selected_variant_parent, project / 'evidence',
                       Path(spec['benchmark']).name, model=profile['model'], period=profile['period'],
                       profile=profile['profile'], fu_overrides=profile.get('fu_overrides', {}),
                       base_build_receipt=base_build, jobs=jobs)
            receipt['hardware'] = variant
            if variant.get('state') not in ('built', 'reused'):
                raise ValueError('Requested hardware could not be generated/built: ' + repr(variant.get('errors')))
            engine = Path(variant['engine_path'])
            build_path, generation_path = Path(variant['build_receipt']), Path(variant['generation_receipt'])
        receipt['selected_engine'] = str(engine)
        capacities = requested_fu_capacity(
            spec['configuration_documents'], profile.get('fu_overrides', {}))
        capability = inspect_fu_capability(engine, build_path)
        receipt['fu_scheduler_capability'] = capability
        if capacities and not capability['supported']:
            raise ValueError('Requested FU capacities lack a verified compiled scheduler: ' +
                             str(capability['reason']))
        validate_limit_parameters(engine, spec.get('parameters', {}), build_path)
        # Normalize against the actual selected compiled registry too; a model
        # profile must not silently alter the meaning of symbolic instruction IDs.
        target = import_configuration(directory / 'request-configuration.yml', engine)
        if target['documents'] != spec['configuration_documents']:
            raise ValueError('Selected compiled registry changes GUI symbol mappings')
        _save(directory / 'selected-registry-normalization.json', target)
        stage('regenerating_building_and_running')
        pipeline = run_configuration(engine, directory / 'normalized-specification.json',
                     directory / 'pipeline', simulate=True, configured_receipt=build_path)
        receipt['pipeline_receipt'] = _record(directory / 'pipeline/configuration.json')
        receipt['pipeline_state'] = pipeline['state']
        if pipeline['state'] != 'passed':
            raise ValueError('Edited GUI simulation did not pass: ' + repr(pipeline['errors']))
        telemetry = _summarize_fu_witness(pipeline.get('fu_scheduling_witness'))
        if telemetry is not None:
            receipt['fu_scheduling_summary'] = telemetry
        stage('verifying_live_gui_settings')
        from .gui_effective import witness_gui_effective
        witness = witness_gui_effective(request, spec, pipeline['staging']['workspace'],
                      directory / 'pipeline', Path(pipeline['run_directory']) / 'simulator/config.ini',
                      build_receipt=build_path, generation_receipt=generation_path,
                      normalization_receipt=directory / 'normalization.json', gui_evidence_dir=directory)
        _save(directory / 'gui-effective.json', witness)
        receipt['effective_witness'] = {'state': witness['state'], 'checks': len(witness['checks']),
                                        'issues': witness['issues']}
        if witness['state'] != 'passed':
            raise ValueError('GUI settings do not match the real simulation: ' + repr(witness['issues']))
        if file_hash(source_path) != receipt['source_config']['sha256']:
            raise ValueError('Original benchmark configuration changed during apply')
        receipt.update(state='passed', stage='complete', editor_form_applied=True,
                       run_directory=pipeline['run_directory'], metrics=pipeline.get('metrics'),
                       source_config_unchanged=True, finished_at=_now())
    except Exception as error:
        receipt.update(state='failed', finished_at=_now())
        receipt['errors'].append(type(error).__name__ + ': ' + str(error))
    _save(directory / 'gui-execution.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--request-stdin', action='store_true')
    group.add_argument('--request')
    parser.add_argument('--evidence-dir')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read(2 * 1024 * 1024 + 1) if args.request_stdin else Path(args.request).read_text(encoding='utf-8-sig')
        request = read_request(text)
        result = apply_request(request, evidence_dir=args.evidence_dir, jobs=args.jobs,
                               progress=lambda value: print(json.dumps(value), flush=True))
    except Exception as error:
        result = {'state': 'failed', 'errors': [type(error).__name__ + ': ' + str(error)],
                  'evidence_directory': args.evidence_dir}
    print(json.dumps({'kind': 'gui_execution_result', 'state': result['state'],
                      'evidence_directory': result.get('evidence_directory'),
                      'errors': result.get('errors', []), 'editor_form_applied': result.get('editor_form_applied', False),
                      'run_directory': result.get('run_directory')}), flush=True)
    return 0 if result['state'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
