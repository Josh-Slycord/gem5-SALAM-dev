"""Run the controlled local FU scheduling matrix and a real wrong-output control."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from salam_workbench.configurator import (run_configuration, verify_engine,
    simulator_args, SYSTEM_DEFAULTS, snapshot_pipeline_tooling)
from salam_workbench.fu_capability import inspect_fu_capability
from salam_workbench.bootstrap_existing import verify_build_inputs_receipt
from salam_workbench.fu_experiments import verify_fu_study
from salam_workbench.gemm import build_mismatch
from salam_workbench.provenance import assert_tooling_unchanged
from salam_workbench.regression import _environment, _save
from salam_workbench.runner import file_hash, run_experiment, EXPECTED_EXIT_REASON


def negative_control(engine, spec_path, directory, build_receipt):
    directory.mkdir(exist_ok=False)
    prepared = run_configuration(engine, spec_path, directory / 'preparation', simulate=False,
                                 configured_receipt=build_receipt)
    assert prepared['state'] == 'prepared', prepared['errors']
    workspace = Path(prepared['staging']['workspace'])
    spec = json.loads(spec_path.read_text())
    kernel = build_mismatch(workspace, directory / 'mismatch-build')
    args = simulator_args(engine, workspace, spec)
    kernel_options = [i for i, value in enumerate(args) if value.startswith('--kernel=')]
    assert len(kernel_options) == 1
    args[kernel_options[0]] = '--kernel=' + str(workspace / kernel)
    inputs = [path for path in workspace.rglob('*') if path.is_file() and '__pycache__' not in path.parts]
    inputs += [spec_path, engine / 'baremetal/common/fake.iso']
    required = ['simulator/system.terminal', 'simulator/config.ini', 'simulator/config.json', 'simulator/stats.txt']
    for accelerator in ('gemm', 'top'):
        prefix = 'simulator/observability/'
        name = 'system.gemm_clstr.' + accelerator + '.invocation-1.json'
        required.extend([prefix + name, prefix + 'fu-scheduling-' + name])
    record = run_experiment([str(engine / 'build/ARM/gem5.opt')], args, cwd=workspace,
        runs_root=directory / 'runs', experiment={
            'schema_version': 1, 'experiment_id': 'gemm-fu-intentional-wrong-output',
            'correctness': {'required_guest_marker': 'Check Passed',
                'rejected_guest_marker': 'Check Failed', 'required_simulator_exit': EXPECTED_EXIT_REASON},
            'negative_witness': {'compile_flag': '-DWORKBENCH_INJECT_MISMATCH',
                'effect': 'XOR accelerator output[0] after independent CPU reference calculation',
                'expected_runner_state': 'failed'}},
        input_paths=inputs, env_overrides={'M5_PATH': str(workspace), 'PATH': _environment(workspace)['PATH']},
        timeout_seconds=600, snapshot_inputs=True, required_artifacts=required)
    result = {'schema_version': 1, 'kind': 'configuration_fault_injection', 'state': record['state'],
              'run_directory': record['run_directory'], 'run_state': record['state'],
              'numerical_correctness': 'guest_checker_failed' if record['correctness']['outcome'] == 'failed' else 'unexpected',
              'engine': verify_engine(engine, build_receipt), 'preparation': str(directory / 'preparation/configuration.json'),
              'compiled_control': str(directory / 'mismatch-build/compile-mismatch.json'),
              'expected_outcome': 'failed', 'correctness': record['correctness']}
    _save(directory / 'configuration.json', result)
    assert result['state'] == 'failed' and result['numerical_correctness'] == 'guest_checker_failed', result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--build-receipt', required=True)
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--allow-simulation', action='store_true')
    args = parser.parse_args()
    if not args.allow_simulation:
        parser.error('Use --allow-simulation for eight controlled actual simulations and a negative control')
    engine = Path(args.engine).resolve(strict=True)
    build = Path(args.build_receipt).resolve(strict=True)
    # Refuse missing provenance before launching any of the nine simulations.
    verify_build_inputs_receipt(build)
    capability = inspect_fu_capability(engine, build)
    assert capability['supported'] and capability['build_verified'], capability
    directory = Path(args.evidence_dir).resolve()
    directory.relative_to(PROJECT / 'evidence')
    directory.mkdir(exist_ok=False)
    shutil.copyfile(__file__, directory / 'run-study.py')
    source = snapshot_pipeline_tooling(directory / 'tooling-snapshot')
    record = {'schema_version': 1, 'kind': 'fu_scheduling_study_session', 'state': 'running',
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'engine': str(engine), 'build_receipt': str(build), 'capability': capability,
              'driver_sha256': file_hash(directory / 'run-study.py'), 'cases': {}, 'issues': []}
    _save(directory / 'session.json', record)
    definitions = {'unlimited': 'gemm_mul_unlimited.json', 'cap1': 'gemm_mul_cap1.json',
                   'cap2': 'gemm_mul_cap2.json', 'unused': 'gemm_unused_fu_cap1.json'}
    cases = {}
    try:
        for case, filename in definitions.items():
            spec = PROJECT / 'experiments/fu_scheduling' / filename
            paths = [directory / (case + '-repeat-' + str(i)) for i in (1, 2)]
            with ThreadPoolExecutor(max_workers=2) as executor:
                pending = [executor.submit(run_configuration, engine, spec, path,
                           simulate=True, configured_receipt=build) for path in paths]
                results = [future.result() for future in pending]
            record['cases'][case] = [{'evidence_directory': str(path), 'state': result['state'],
                'errors': result['errors'], 'run_directory': result.get('run_directory')}
                for path, result in zip(paths, results)]
            _save(directory / 'session.json', record)
            print(json.dumps({'case': case, 'states': [result['state'] for result in results]}), flush=True)
            assert all(result['state'] == 'passed' for result in results), record['cases'][case]
            cases[case] = [str(path) for path in paths]
        negative = negative_control(engine, PROJECT / 'experiments/fu_scheduling/gemm_mul_cap1.json',
                                    directory / 'wrong-output', build)
        record['negative_control'] = negative
        assessment = verify_fu_study(cases, directory / 'wrong-output')
        _save(directory / 'assessment.json', assessment)
        record.update(state=assessment['state'], assessment=str(directory / 'assessment.json'))
        record['issues'].extend(str(issue) for issue in assessment.get('issues', []))
        record['issues'].extend('Inconclusive: ' + str(reason) for reason in assessment.get('inconclusive_reasons', []))
        assert_tooling_unchanged(PROJECT, source)
        verify_engine(engine, build)
    except Exception as error:
        record['state'] = 'failed'
        record['issues'].append(type(error).__name__ + ': ' + str(error))
    record['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save(directory / 'session.json', record)
    print(json.dumps({'state': record['state'], 'evidence_directory': str(directory), 'issues': record['issues']}))
    return 0 if record['state'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
