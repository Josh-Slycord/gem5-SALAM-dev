"""Run explicit, independently checked configurable SALAM experiments.

This is a real-simulator acceptance study, never part of fast/unit checks.
Without --simulate it writes a planned matrix only. Existing run directories
are never reused. Results describe fixed workload sizes with varied inputs;
they do not establish arbitrary sizes, memory topologies or hardware timing.
"""
import argparse
import configparser
import copy
import datetime
import hashlib
import json
import sys
import uuid
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

WORKLOADS = ("gemm", "fft", "stencil3d")
LATENCIES = {"gemm": "mul", "fft": "fmul", "stencil3d": "add"}
OUTPUT_COUNTS = {"gemm": 64, "fft": 1024, "stencil3d": 16384}
STENCIL_TRACE_EVENT_LIMIT = 1048576


def _save(path, data):
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_content_sha256(fixture):
    """Hash actual numeric inputs and shape, excluding seed/dataset labels."""
    content = {key: fixture[key] for key in ("benchmark", "shape", "inputs")}
    payload = json.dumps(content, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def matrix_cases(workloads=WORKLOADS, seeds=(1, 2), repeats=1, negatives=True):
    """Return explicit rows; a planned row never means that a run passed."""
    if not workloads or len(set(workloads)) != len(workloads):
        raise ValueError("Choose unique workloads")
    if any(name not in WORKLOADS for name in workloads):
        raise ValueError("Only GEMM, FFT and stencil3d have breadth contracts")
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(type(seed) is not int or seed < 0 or seed > 2147483647 for seed in seeds)
        or type(repeats) is not int
        or not 1 <= repeats <= 10
    ):
        raise ValueError("Unique seeds in 0..2147483647 and 1..10 repeats are required")
    rows = []
    for workload in workloads:
        for seed in seeds:
            for variant, latency in (("baseline", 1), ("latency4", 4)):
                for repeat in range(1, repeats + 1):
                    rows.append({
                        "id": "{}_s{}_{}_r{}".format(workload, seed, variant, repeat),
                        "workload": workload,
                        "seed": seed,
                        "variant": variant,
                        "repeat": repeat,
                        "latency_field": LATENCIES[workload],
                        "latency": latency,
                        "expected_outcome": "passed",
                    })
        if negatives:
            rows.append({
                "id": "{}_s{}_wrong_output".format(workload, seeds[0]),
                "workload": workload,
                "seed": seeds[0],
                "variant": "wrong_output",
                "repeat": 1,
                "latency_field": LATENCIES[workload],
                "latency": 1,
                "expected_outcome": "independent_rejection_with_guest_pass",
            })
    return rows


def specification_from_documents(documents, case):
    """Bind a runtime override to the actual named accelerator in source YAML."""
    from salam_workbench.gui_editor import extract_components

    if not isinstance(documents, list) or len(documents) != 1:
        raise ValueError("This study requires one source YAML mapping document")
    # Compiled RegisterBank currently exposes one scalar response port. Keep the
    # recovered YAML intact and make this study's supported choice explicit.
    documents = copy.deepcopy(documents)
    register_bank_notes = []
    if case["workload"] == "stencil3d":
        for entry in documents[0].get("acc_cluster", []):
            for field in entry.get("Accelerator", []):
                for memory in field.get("Var", []):
                    if memory.get("Type") != "RegisterBank":
                        continue
                    requested = memory.get("Ports")
                    if type(requested) is not int or requested <= 0:
                        raise ValueError("Stencil study requires an explicit positive source RegisterBank Ports value")
                    register_bank_notes.append("{} source Ports={} explicitly configured Ports=1".format(
                        memory.get("Name", "unnamed RegisterBank"), requested
                    ))
                    memory["Ports"] = 1
    cluster, components = extract_components(documents[0])
    matches = [
        item for item in components
        if item["type"] == "accelerator"
        and Path(item["ir_path"]).stem.lower() == case["workload"]
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one workload accelerator bound to its IR")
    accelerator = matches[0]["name"].lower()
    target = "system.{}.{}".format(cluster, accelerator)
    benchmark_input = {"dataset": "seeded", "seed": case["seed"]}
    if case["expected_outcome"] != "passed":
        benchmark_input.update(inject_mismatch=True, force_guest_pass=True)
    description = "All actual hardware outputs independently recomputed on host"
    if register_bank_notes:
        description += "; single-port compiled RegisterBank study: " + "; ".join(register_bank_notes)
        description += "; original source YAML is preserved; multiport RegisterBank is outside this study"
    specification = {
        "schema_version": 1,
        "name": "breadth_" + case["id"],
        "benchmark": "benchmarks/sys_validation/" + case["workload"],
        "configuration_documents": documents,
        "base_address": "0x10020000",
        "system": {"cpu-clock": "2GHz", "sys-clock": "1GHz", "cacheline_size": 64},
        "parameters": {
            target + ".hw_interface.cycle_counts": {
                case["latency_field"]: case["latency"]
            }
        },
        "benchmark_input": benchmark_input,
        "correctness": {
            "expected_passed_markers": 1,
            "description": description,
        },
        "timeout_seconds": 1200,
    }
    if case["workload"] == "stencil3d":
        specification["parameters"][target + ".llvm_interface"] = {
            "fu_trace_event_limit": STENCIL_TRACE_EVENT_LIMIT
        }
        specification["correctness"]["description"] += (
            "; explicitly request bounded FU trace budget={} events; complete independent replay remains required".format(STENCIL_TRACE_EVENT_LIMIT)
        )
    return specification, target


def witness_trace_event_limit(parser, specification, target):
    """Read back an explicitly requested producer limit from the actual SimObject."""
    if specification.get("benchmark") != "benchmarks/sys_validation/stencil3d":
        return None
    section = target + ".llvm_interface"
    requested = specification.get("parameters", {}).get(section, {}).get("fu_trace_event_limit")
    if type(requested) is not int or requested != STENCIL_TRACE_EVENT_LIMIT:
        raise ValueError("Stencil study must explicitly request its bounded full-trace event limit")
    observed = parser.getint(section, "fu_trace_event_limit")
    if observed != requested:
        raise ValueError("Requested FU trace event limit did not reach the LLVMInterface")
    return {"state": "passed", "requested": requested, "observed": observed,
            "source": "config.ini:" + section + ".fu_trace_event_limit",
            "scope": "Producer storage bound only; independent complete trace replay is still required"}


def _verified_artifact(run, relative):
    """Require a unique, hash-bound local artifact before replaying it."""
    root = Path(run["run_directory"]).resolve(strict=True)
    entries = [item for item in run.get("artifacts", []) if item.get("path") == relative]
    if len(entries) != 1:
        raise ValueError("Missing or duplicated recorded artifact: " + relative)
    candidate = root / relative
    candidate.resolve(strict=True).relative_to(root)
    cursor = candidate
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError("Symlinked study artifact is unsupported")
        cursor = cursor.parent
    if not candidate.is_file() or _sha(candidate) != entries[0].get("sha256"):
        raise ValueError("Study artifact hash mismatch: " + relative)
    return candidate


def study_system_witness(witness, explicit_system):
    """Accept only mapped study settings, retaining the known bare-metal gap.

    The simulator pipeline currently has no independent bare-metal witness.
    A partial result for precisely that inherited option is compatible with
    this study's explicit clock/cache-line claims. No other unknown setting,
    failed check or diagnostic is accepted by this bounded exception.
    """
    if not isinstance(witness, dict) or not isinstance(explicit_system, dict):
        raise ValueError("System witness and explicit study settings are required")
    if witness.get("issues") != []:
        raise ValueError("System witness has issues or missing diagnostics")
    checks = witness.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError("System witness has no per-option checks")
    normalized = {}
    for key, check in checks.items():
        if not isinstance(key, str):
            raise ValueError("Malformed system option name")
        name = key.replace("_", "-")
        if name in normalized or not isinstance(check, dict):
            raise ValueError("Ambiguous or malformed system option check")
        normalized[name] = check
    unmapped = witness.get("unmapped_options")
    state = witness.get("state")
    if state == "passed":
        if unmapped != [] or any(check.get("status") != "passed" for check in checks.values()):
            raise ValueError("Passed system witness contains unknown or failed settings")
        limitations = []
    elif state == "partial":
        if unmapped != ["bare-metal"]:
            raise ValueError("Only the inherited bare-metal witness gap is accepted")
        if normalized.get("bare-metal", {}).get("status") != "unwitnessed":
            raise ValueError("Partial witness does not identify the bare-metal gap")
        if any(check.get("status") != "passed"
               for name, check in normalized.items() if name != "bare-metal"):
            raise ValueError("A mapped system option did not pass")
        limitations = ["Bare-metal mode is not independently witnessed; acceptance applies to the explicitly requested clock and cache-line settings."]
    else:
        raise ValueError("System witness state is not passed or the bounded known partial")
    explicit = {key.replace("_", "-"): value for key, value in explicit_system.items()}
    if not {"cpu-clock", "sys-clock", "cacheline-size"} <= set(explicit):
        raise ValueError("Study requires explicit CPU clock, system clock and cache-line settings")
    for name, requested in explicit.items():
        check = normalized.get(name, {})
        if check.get("status") != "passed" or type(check.get("requested")) is not type(requested) or check.get("requested") != requested:
            raise ValueError("Explicit study setting lacks its matching passed witness: " + name)
    return {
        "state": state,
        "explicit_study_settings": "passed",
        "unmapped_options": list(unmapped),
        "checks": checks,
        "limitations": limitations,
    }


def numerical_output_artifact(run, pipeline):
    """Select one declared hash-bound transport; never guess another file."""
    inputs = pipeline.get("benchmark_inputs", {})
    if not isinstance(inputs, dict):
        raise ValueError("Malformed benchmark input transport receipt")
    transport = inputs.get("output_transport")
    if transport == "gem5_semihosting_writefile_text_v1":
        relative = "simulator/salam-results.txt"
        if inputs.get("output_relative", relative) != relative:
            raise ValueError("Declared numerical output file differs from transport contract")
    elif transport is None and "output_transport" not in inputs:
        # Preserved earlier evidence emitted the complete protocol over UART.
        relative, transport = "simulator/system.terminal", "legacy_uart_text_v1"
    else:
        raise ValueError("Unsupported numerical output transport")
    path = _verified_artifact(run, relative)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Numerical output exceeds the bounded 16 MiB reader limit")
    return path, transport


def inspect_case(case, pipeline, specification, target):
    """Replay actual numerical output and effective settings independently."""
    from salam_workbench.benchmark_oracles import assess_output, make_fixture
    from salam_workbench.observability import validate_observability
    from salam_workbench.runner import _read_correctness

    result = {"case": case, "state": "failed", "issues": []}
    result["configuration_scope"] = specification.get("correctness", {}).get("description")
    try:
        directory = Path(pipeline["run_directory"]).resolve(strict=True)
        raw = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        if Path(raw.get("run_directory", "")).resolve(strict=True) != directory:
            raise ValueError("Raw run identity differs")
        terminal = _verified_artifact(raw, "simulator/system.terminal")
        output_path, transport = numerical_output_artifact(raw, pipeline)
        config_path = _verified_artifact(raw, "simulator/config.ini")
        fixture = make_fixture(case["workload"], dataset="seeded", seed=case["seed"])
        oracle = assess_output(output_path.read_text(encoding="utf-8"), fixture)
        result["oracle_replay"] = oracle
        result["fixture_sha256"] = fixture["fixture_sha256"]
        result["input_content_sha256"] = input_content_sha256(fixture)
        result["output_sha256"] = oracle.get("output_sha256")
        result["terminal_sha256"] = _sha(terminal)
        result["numerical_output_source"] = str(output_path)
        result["numerical_output_source_sha256"] = _sha(output_path)
        result["output_transport"] = transport
        result["run_directory"] = str(directory)
        result["guest_checker"] = _read_correctness(terminal)
        if oracle["expected_count"] != OUTPUT_COUNTS[case["workload"]]:
            raise ValueError("Oracle size differs from declared fixed-size study")
        if case["expected_outcome"] == "passed":
            if pipeline.get("state") != "passed":
                raise ValueError("Configuration pipeline did not pass")
            if pipeline.get("numerical_correctness") != "independent_full_output_passed":
                raise ValueError("Pipeline did not enforce independent all-output acceptance")
            if oracle.get("state") != "passed":
                raise ValueError("Independent raw-output replay did not pass")
        else:
            if pipeline.get("state") != "failed" or oracle.get("state") != "failed":
                raise ValueError("Wrong-output run was not independently rejected")
            if oracle.get("mismatch_count", 0) < 1:
                raise ValueError("Wrong-output rejection was not a numerical mismatch")
            if pipeline.get("independent_oracle", {}).get("state") != "failed":
                raise ValueError("Pipeline failed without recording its numerical rejection")
        guest = result["guest_checker"]
        if guest.get("passed_markers") != 1 or guest.get("failed_markers") != 0:
            raise ValueError("Expected exactly one guest pass even for host-rejected control")
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        parser.read_string(config_path.read_text(encoding="utf-8"))
        section = target + ".hw_interface.cycle_counts"
        actual = parser.getint(section, case["latency_field"])
        if actual != case["latency"]:
            raise ValueError("Latency edit did not reach the effective SimObject")
        result["effective_latency"] = actual
        result["effective_parameter"] = section + "." + case["latency_field"]
        trace_limit = witness_trace_event_limit(parser, specification, target)
        if trace_limit is not None:
            result["trace_event_limit_witness"] = trace_limit
        for key in ("parameter_witness", "profile_witness"):
            if case["expected_outcome"] == "passed" and pipeline.get(key, {}).get("state") != "passed":
                raise ValueError("Missing accepted pipeline witness: " + key)
        if case["expected_outcome"] == "passed":
            fu_witness = pipeline.get("fu_scheduling_witness", {})
            if fu_witness.get("state") != "passed" or not fu_witness.get("invocations"):
                raise ValueError("Complete independent FU trace replay is required")
            if any(item.get("state") != "passed"
                   or item.get("trace", {}).get("state") != "passed"
                   or item.get("trace", {}).get("trace_complete") is not True
                   for item in fu_witness["invocations"]):
                raise ValueError("FU trace replay is incomplete or failed")
            result["system_witness_scope"] = study_system_witness(
                pipeline.get("system_witness"), specification.get("system")
            )
        relative = "simulator/observability/{}.invocation-1.json".format(target)
        observation = _verified_artifact(raw, relative)
        data = json.loads(observation.read_text(encoding="utf-8"))
        if data.get("accelerator") != target or data.get("invocation") != 1:
            raise ValueError("Accelerator timing identity differs")
        if validate_observability(data).get("status") != "valid":
            raise ValueError("Accelerator lifecycle/queue/memory contract is invalid")
        life = data["lifecycle"]
        if life.get("completed") is not True or type(life.get("elapsed_ticks")) is not int:
            raise ValueError("Accelerator lifecycle is incomplete")
        result["accelerator_elapsed_ticks"] = life["elapsed_ticks"]
        result["interface_tick_calls"] = life["interface_tick_calls"]
        result["state"] = "passed"
    except (OSError, ValueError, KeyError, TypeError, configparser.Error) as error:
        result["issues"].append(type(error).__name__ + ": " + str(error))
    return result


def compare_cases(rows):
    """Require changed inputs and observed timing sensitivity for each pair."""
    pairs = []
    grouped = {}
    fixture_digests = {}
    input_digests = {}
    for row in rows:
        case = row["case"]
        if case["expected_outcome"] != "passed":
            continue
        key = (case["workload"], case["seed"], case["repeat"])
        grouped.setdefault(key, {})[case["variant"]] = row
        if row.get("state") == "passed":
            fixture_digests.setdefault(case["workload"], {})[case["seed"]] = row["fixture_sha256"]
            input_digests.setdefault(case["workload"], {})[case["seed"]] = row.get("input_content_sha256")
    for key, variants in sorted(grouped.items()):
        comparison = {"workload": key[0], "seed": key[1], "repeat": key[2], "state": "failed", "issues": []}
        baseline, changed = variants.get("baseline"), variants.get("latency4")
        if not baseline or not changed or baseline.get("state") != "passed" or changed.get("state") != "passed":
            comparison["issues"].append("Both settings require accepted real runs")
        elif baseline["fixture_sha256"] != changed["fixture_sha256"]:
            comparison["issues"].append("Settings comparison changed the workload inputs")
        elif not baseline.get("input_content_sha256") or baseline["input_content_sha256"] != changed.get("input_content_sha256"):
            comparison["issues"].append("Settings comparison lacks identical actual numeric input content")
        elif not baseline.get("output_sha256") or baseline["output_sha256"] != changed.get("output_sha256"):
            comparison["issues"].append("Settings comparison changed observed output bits; numerical tolerance alone does not establish this study's exact-output invariant")
        else:
            first, second = baseline["accelerator_elapsed_ticks"], changed["accelerator_elapsed_ticks"]
            comparison.update(baseline_ticks=first, changed_ticks=second, delta_ticks=second - first)
            if second <= first:
                comparison["issues"].append("Chosen latency change has no positive accelerator timing response; investigate before claiming sensitivity")
            else:
                comparison["state"] = "passed"
        pairs.append(comparison)
    input_checks = []
    for workload, seeds in sorted(fixture_digests.items()):
        numeric_inputs = input_digests.get(workload, {})
        distinct = (len(set(seeds.values())) == len(seeds)
                    and None not in numeric_inputs.values()
                    and len(set(numeric_inputs.values())) == len(seeds))
        input_checks.append({"workload": workload, "seeds": sorted(seeds),
                             "distinct_fixture_count": len(set(seeds.values())),
                             "distinct_numeric_input_count": len(set(numeric_inputs.values()) - {None}),
                             "state": "passed" if distinct else "failed"})
    return pairs, input_checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--workloads", default=",".join(WORKLOADS))
    parser.add_argument("--seeds", default="1,2")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--no-negative-controls", action="store_true")
    args = parser.parse_args(argv)
    cases = matrix_cases(tuple(args.workloads.split(",")), tuple(int(s) for s in args.seeds.split(",")), args.repeats, not args.no_negative_controls)
    directory = args.evidence_dir or PROJECT / "evidence" / ("configurable-breadth-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    receipt = {"schema_version": 1, "kind": "salam_configurable_breadth_study", "state": "planned", "simulation_requested": args.simulate, "source_sha256": _sha(Path(__file__)), "scope": "Fixed 8x8 int32 GEMM, 1024-point double FFT, 16x32x32 int32 stencil; varied deterministic inputs and scalar instruction latency; no arbitrary sizes or hardware calibration", "cases": cases, "runs": [], "comparisons": []}
    _save(directory / "study.json", receipt)
    if not args.simulate:
        print(json.dumps({"state": "planned", "cases": len(cases), "evidence_directory": str(directory)}))
        return 0
    if args.build_receipt is None:
        parser.error("--simulate requires an explicit --build-receipt")
    from salam_workbench.configuration_import import import_configuration
    from salam_workbench.configurator import run_configuration

    receipt["state"] = "running"
    for case in cases:
        try:
            source = args.engine / "benchmarks/sys_validation" / case["workload"] / "config.yml"
            imported = import_configuration(source, args.engine)
            specification, target = specification_from_documents(imported["documents"], case)
            spec_path = directory / (case["id"] + ".json")
            _save(spec_path, specification)
            print(json.dumps({"state": "running", "case": case["id"]}), flush=True)
            pipeline = run_configuration(args.engine, spec_path, directory / case["id"], simulate=True, configured_receipt=args.build_receipt)
            replay = inspect_case(case, pipeline, specification, target)
            replay["pipeline_state"] = pipeline["state"]
            replay["pipeline_receipt"] = str(directory / case["id"] / "configuration.json")
            receipt["runs"].append(replay)
        except Exception as error:
            receipt["runs"].append({"case": case, "state": "failed", "issues": [type(error).__name__ + ": " + str(error)]})
        _save(directory / "study.json", receipt)
        print(json.dumps({"case": case["id"], "state": receipt["runs"][-1]["state"], "issues": receipt["runs"][-1].get("issues", [])}), flush=True)
    receipt["comparisons"], receipt["input_checks"] = compare_cases(receipt["runs"])
    checks = receipt["runs"] + receipt["comparisons"] + receipt["input_checks"]
    receipt["state"] = "passed" if checks and all(row["state"] == "passed" for row in checks) else "failed"
    _save(directory / "study.json", receipt)
    print(json.dumps({"state": receipt["state"], "evidence_directory": str(directory)}))
    return 0 if receipt["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
