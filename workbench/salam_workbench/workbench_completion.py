"""Read-only completion gates for the desktop Workbench.

A process exit and a saved ``passed`` flag are insufficient. This module
reopens the local raw results and replays the relevant reference or effective
configuration checks before the GUI can mark an operation complete.
"""
import json
import os
import re
from pathlib import Path

from .runner import file_hash
from .workbench_results import load_run

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
BENCHMARK = re.compile(
    r"benchmarks/(?:sys_validation|legacy|lenet5-nounroll|mobilenetv2)/[A-Za-z0-9_-]+"
)


def _safe(path, roots, *, directory=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Completion evidence must use an absolute bounded path")
    for root in roots:
        try:
            root = Path(root).resolve(strict=True)
            path.relative_to(root)
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            cursor = path
            while cursor != root:
                if cursor.is_symlink():
                    raise ValueError("Symlinked completion evidence is unsupported")
                cursor = cursor.parent
            if resolved.is_dir() if directory else resolved.is_file():
                return resolved
        except (OSError, ValueError, RuntimeError):
            continue
    raise ValueError("Completion evidence is missing, symlinked or outside its root")


def _json(path):
    if path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("Completion receipt exceeds the 8 MiB limit")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate completion JSON key: " + key)
            result[key] = value
        return result

    value = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("Nonfinite completion JSON: " + value)
        ),
    )
    if not isinstance(value, dict):
        raise ValueError("Expected a completion receipt object")
    return value


def _equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _equal(first, second) for first, second in zip(left, right)
        )
    return left == right


def _linked(item, roots):
    if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
        raise ValueError("Completion receipt lacks a source hash")
    path = _safe(item.get("path", ""), roots)
    if file_hash(path) != item["sha256"]:
        raise ValueError("Completion source hash differs: " + str(path))
    return path


def _project_receipt(project, relative, evidence_root):
    if not isinstance(relative, str):
        raise ValueError("Selected manifest receipt path is missing")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or "\\" in relative or ":" in relative:
        raise ValueError("Manifest receipt must stay inside project evidence")
    return _safe(project / raw, [evidence_root])


def _check_staged_tree(workspace):
    """A generated workspace must not redirect semantic reads through links."""
    count = 0
    for folder, directories, filenames in os.walk(str(workspace), followlinks=False):
        for name in directories + filenames:
            count += 1
            if count > 20000:
                raise ValueError("Staged completion workspace exceeds 20,000 entries")
            if (Path(folder) / name).is_symlink():
                raise ValueError("Symlinked staged completion input is unsupported")


def _verify_reference(record, directory, project, benchmark, evidence_root):
    from .workbench_jobs import _validate_results, normalize_reference_benchmark

    name = normalize_reference_benchmark(benchmark)
    if (
        record.get("kind") != "workbench_reference_session"
        or record.get("schema_version") != 1
        or record.get("mode") != "fixed_reference"
        or record.get("benchmark") != benchmark
        or record.get("editor_settings_applied") is not False
        or record.get("evidence_directory") != str(directory)
    ):
        raise ValueError("Reference completion identity or mode differs")
    manifest_path = _safe(project / "workspace.json", [project])
    manifest = _json(manifest_path)
    expected_engine = Path(manifest["engine"]["path"]).resolve(strict=True)
    if Path(record.get("engine", "")).resolve(strict=True) != expected_engine:
        raise ValueError("Reference completion uses another engine")
    source = _linked(
        {
            "path": record.get("source_session"),
            "sha256": record.get("source_session_sha256"),
        },
        [evidence_root],
    )
    if source.name != "session.json":
        raise ValueError("Reference completion must link its original session")
    saved = _json(source)
    if name != "gemm" and saved.get("scope") != [name]:
        raise ValueError("Reference session did not select this single workload")
    runs_root = _safe(directory / "runs", [directory], directory=True)
    runs, unused_checks = _validate_results(name, saved, runs_root)
    if record.get("run_directories") != runs or record.get("run_directory") != runs[-1]:
        raise ValueError("Reference wrapper run list differs from validated runs")
    if name == "gemm" and not _equal(
        record.get("negative_witness"), saved.get("negative_witness")
    ):
        raise ValueError("Reference wrapper negative control differs from raw session")
    if file_hash(source) != record["source_session_sha256"]:
        raise ValueError("Reference session changed during completion verification")


def _select_hardware(record, request, project, evidence_root, base, configuration):
    """Bind receipts either to the selected base or its fingerprinted GUI cache."""
    base_build = _project_receipt(
        project, configuration["build_receipt"], evidence_root
    )
    base_generation = _project_receipt(
        project, configuration["generation_receipt"], evidence_root
    )
    selected = Path(record.get("selected_engine", ""))
    if not selected.is_absolute():
        raise ValueError("Configured completion has no selected engine")
    hardware = record.get("hardware")
    if not isinstance(hardware, dict):
        raise ValueError("Configured completion has no hardware binding")
    if selected.resolve(strict=True) == base:
        if hardware.get("state") != "reused_base":
            raise ValueError("Configured completion did not bind the selected base")
        build, generation = base_build, base_generation
        selected = base
    else:
        from .hardware_variants import (
            _fingerprint,
            _fingerprint_inputs,
            _verify_variant,
        )

        profile = request["hardware_profile"]
        inputs = _fingerprint_inputs(
            base,
            Path(request["benchmark"]).name,
            profile["model"],
            profile["period"],
            profile["profile"],
            profile.get("fu_overrides", {}),
            base_build,
        )
        fingerprint = _fingerprint(inputs)
        expected = base.parent / "gui-variants" / fingerprint
        selected = _safe(selected, [expected], directory=True)
        if selected != expected.resolve(strict=True):
            raise ValueError("Configured completion selected another cached engine")
        marker = _safe(selected / ".workbench-variant.json", [selected])
        cached = _json(marker)
        if cached.get("fingerprint_inputs") != inputs:
            raise ValueError("Cached variant source identity differs from this request")
        build = _safe(cached.get("build_receipt", ""), [evidence_root])
        generation = _safe(cached.get("generation_receipt", ""), [evidence_root])
        _verify_variant(
            selected, cached, fingerprint, inputs["selected_profile_inputs"]
        )
        if hardware.get("state") not in ("built", "reused"):
            raise ValueError("Configured completion variant did not finish building")
        for field in (
            "fingerprint",
            "engine_path",
            "build_receipt",
            "generation_receipt",
        ):
            if hardware.get(field) != cached.get(field):
                raise ValueError("Configured variant receipt differs: " + field)
    for field, expected in (
        ("build_receipt", build),
        ("generation_receipt", generation),
    ):
        bound = _safe(hardware.get(field, ""), [evidence_root])
        if bound != expected:
            raise ValueError("Configured hardware receipt is not the selected binding")
    if Path(hardware.get("engine_path", "")).resolve(strict=True) != selected:
        raise ValueError("Hardware binding selected engine differs")
    return selected, build, generation


def _verify_configured(record, directory, project, benchmark, expected_request):
    import yaml

    from .config_contract import _Loader
    from .configuration_import import import_configuration
    from .configurator import validate_spec
    from .gui_effective import witness_gui_effective
    from .gui_execution import validate_request

    if not isinstance(expected_request, dict):
        raise ValueError("Configured completion requires the dispatched live request")
    if (
        record.get("kind") != "salam_gui_execution"
        or record.get("schema_version") != 1
        or record.get("editor_form_applied") is not True
        or record.get("simulation_requested") is not True
        or record.get("pipeline_state") != "passed"
        or record.get("source_config_unchanged") is not True
    ):
        raise ValueError("Configured completion lacks a finished simulation binding")
    if record.get("evidence_directory") != str(directory):
        raise ValueError("Configured completion evidence identity differs")
    evidence_root = _safe(project / "evidence", [project], directory=True)
    request_path = _safe(directory / "request.json", [directory])
    request = _json(request_path)
    if not _equal(request, expected_request) or request.get("benchmark") != benchmark:
        raise ValueError("Saved request differs from the dispatched live GUI request")
    request_hash = file_hash(request_path)
    base, configuration, source = validate_request(request, project=project)
    source = _safe(source, [base])
    if record.get("source_config", {}).get("sha256") != file_hash(source):
        raise ValueError("Original configured benchmark source changed")
    if (
        _linked(record.get("workspace_manifest"), [project])
        != project / "workspace.json"
    ):
        raise ValueError("Configured completion linked another workspace manifest")
    selected, build, generation = _select_hardware(
        record, request, project, evidence_root, base, configuration
    )
    raw_yaml = _safe(directory / "request-configuration.yml", [directory])
    if raw_yaml.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("Saved configuration YAML exceeds reader limit")
    raw_documents = list(yaml.load_all(raw_yaml.read_text(), Loader=_Loader))
    if not _equal(raw_documents, request.get("configuration_documents")):
        raise ValueError("Saved source YAML differs from live GUI request")
    imported = import_configuration(raw_yaml, selected)
    spec_path = _safe(directory / "normalized-specification.json", [directory])
    spec = validate_spec(_json(spec_path))
    expected_spec = {
        "schema_version": 1,
        "name": Path(benchmark).name,
        "benchmark": benchmark,
        "config": request["provenance"]["source_config"]["relative_path"],
        "configuration_documents": imported["documents"],
        "system": request.get("system", {}),
        "parameters": request.get("parameters", {}),
        "base_address": request["base_address"],
        "correctness": {
            "expected_passed_markers": 1,
            "description": "Real benchmark guest checker; numerical acceptance and configuration transport are assessed separately",
        },
    }
    if "benchmark_input" in request:
        expected_spec["benchmark_input"] = request["benchmark_input"]
    if not _equal(spec, expected_spec):
        raise ValueError("Saved normalized specification differs from the live request")
    pipeline_dir = _safe(directory / "pipeline", [directory], directory=True)
    pipeline_path = _linked(record.get("pipeline_receipt"), [directory])
    if pipeline_path != pipeline_dir / "configuration.json":
        raise ValueError("Configured completion linked another pipeline")
    pipeline = _json(pipeline_path)
    if (
        pipeline.get("state") != "passed"
        or pipeline.get("simulation_requested") is not True
        or pipeline.get("run_state") != "passed"
    ):
        raise ValueError("Configured pipeline did not finish its real simulation")
    if _linked(pipeline.get("specification"), [directory]) != spec_path:
        raise ValueError("Configured pipeline used another specification")
    workspace = _safe(pipeline_dir / "workspace", [pipeline_dir], directory=True)
    if Path(pipeline.get("staging", {}).get("workspace", "")) != workspace:
        raise ValueError("Configured pipeline staged another workspace")
    _check_staged_tree(workspace)
    run = _safe(pipeline.get("run_directory", ""), [directory], directory=True)
    if record.get("run_directory") != str(run):
        raise ValueError("Configured wrapper linked another simulation run")
    ini = _safe(run / "simulator/config.ini", [run])
    normalization = _safe(directory / "normalization.json", [directory])
    witness = witness_gui_effective(
        request,
        spec,
        workspace,
        pipeline_dir,
        ini,
        build_receipt=build,
        generation_receipt=generation,
        normalization_receipt=normalization,
        gui_evidence_dir=directory,
    )
    checks = witness.get("checks")
    if (
        witness.get("state") != "passed"
        or witness.get("issues")
        or not isinstance(checks, list)
        or not checks
        or any(
            not isinstance(check, dict) or check.get("status") != "passed"
            for check in checks
        )
    ):
        raise ValueError(
            "Current effective settings witness failed: " + str(witness.get("issues"))
        )
    if file_hash(request_path) != request_hash:
        raise ValueError("Live GUI request changed during completion verification")


def verify_completion(
    evidence_directory, project, benchmark, mode, expected_request=None
):
    """Return a current pass only after replaying this operation's real evidence."""
    response = {"state": "failed", "result": None, "errors": []}
    try:
        if not isinstance(benchmark, str) or BENCHMARK.fullmatch(benchmark) is None:
            raise ValueError("Completion requires one selected benchmark key")
        if mode not in ("configured", "reference", "fixed_reference"):
            raise ValueError("Unsupported Workbench completion mode")
        project = Path(project).resolve(strict=True)
        evidence_root = _safe(project / "evidence", [project], directory=True)
        directory = _safe(evidence_directory, [evidence_root], directory=True)
        filename = (
            "gui-execution.json" if mode == "configured" else "reference-session.json"
        )
        path = _safe(directory / filename, [directory])
        record = _json(path)
        original_hash = file_hash(path)
        result = load_run(path, project)
        response["result"] = result
        if (
            record.get("state") != "passed"
            or result.get("state") != "passed"
            or result.get("benchmark") != benchmark
            or result.get("validation_state") != "checked_recorded_evidence"
            or result.get("errors")
        ):
            raise ValueError("Current raw evidence does not establish a passing run")
        if mode == "configured":
            _verify_configured(record, directory, project, benchmark, expected_request)
            if "benchmark_input" in expected_request and result.get("independent_oracle", {}).get("state") != "passed":
                raise ValueError("Configured generated inputs require a current independent full-output pass")
        else:
            _verify_reference(record, directory, project, benchmark, evidence_root)
        if file_hash(path) != original_hash:
            raise ValueError("Completion receipt changed while it was being checked")
        result["completion_verification"] = "replayed_current_evidence"
        response["state"] = "passed"
    except Exception as error:
        response["errors"].append(type(error).__name__ + ": " + str(error))
    return response
