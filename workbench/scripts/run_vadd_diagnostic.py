# SPDX-License-Identifier: BSD-3-Clause
"""Prepare, or explicitly simulate, a bounded VADD numerical/activity study.

Preparation compiles staged guest/IR inputs but does not qualify a simulation.
Every simulation must pass independent output and direct SALAM activity checks.
The two negative controls must fail for their intended numerical reasons.
"""
import argparse
import configparser
import copy
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hash(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular evidence file: " + str(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save(path, value):
    # Only this invocation's fresh output directory contains mutable progress.
    Path(path).write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def _negative_errors(pipeline, run, oracle, numpy_check, count, forced):
    """Fail closed: a crash/timeout/absent result is never a successful control."""
    errors = []
    expected_stage = "independent_numerical_validation" if forced else "simulation"
    if pipeline.get("state") != "failed" or pipeline.get("stage") != expected_stage:
        errors.append("Pipeline failed outside the expected numerical gate")
    messages = pipeline.get("errors")
    expected_message = (
        "Independent full-output numerical oracle rejected the simulation"
        if forced
        else "Simulator/guest did not pass:"
    )
    if (
        not isinstance(messages, list)
        or len(messages) != 1
        or expected_message not in messages[0]
    ):
        errors.append("Pipeline has missing or unrelated failures")
    if run.get("return_code") != 0 or run.get("stage") != "assessment":
        errors.append("Simulator did not finish normally")
    if run.get("state") != ("passed" if forced else "failed"):
        errors.append("Unexpected runner state for this control")
    guest = run.get("correctness") or {}
    if (
        guest.get("passed_markers") != (1 if forced else 0)
        or guest.get("failed_markers") != (0 if forced else 1)
        or guest.get("outcome") != ("passed" if forced else "failed")
    ):
        errors.append("Guest checker markers do not match the requested control")
    expected_run_errors = (
        [] if forced else ["Nonzero process exit or explicit guest correctness failure"]
    )
    if run.get("errors") != expected_run_errors:
        errors.append("Runner contains an unrelated error")
    for name, result in (("CPU oracle", oracle), ("NumPy checker", numpy_check)):
        if (
            result.get("state") != "failed"
            or result.get("compared_count") != count
            or result.get("mismatch_count") != 1
        ):
            errors.append(name + " did not compare all words and find one mismatch")
    if oracle.get("issues") != ["Numerical output mismatch at index 0"]:
        errors.append(
            "CPU oracle did not identify exactly the injected first-word error"
        )
    mismatches = numpy_check.get("first_mismatches")
    if (
        not isinstance(mismatches, list)
        or len(mismatches) != 1
        or mismatches[0].get("index") != 0
    ):
        errors.append("NumPy did not independently locate the first-word error")
    return errors


def _cases(include_max):
    cases = [
        ("tiny8", {"dataset": "seeded", "seed": 1, "length": 8}),
        ("reseed8", {"dataset": "seeded", "seed": 29, "length": 8}),
        ("one1", {"dataset": "boundary", "seed": 1, "length": 1}),
        (
            "odd7_uart",
            {
                "dataset": "seeded",
                "seed": 3,
                "length": 7,
                "output_transport": "uart",
                "verbose": True,
            },
        ),
        ("zeros16", {"dataset": "zeros", "seed": 1, "length": 16}),
        (
            "custom3",
            {
                "dataset": "custom",
                "seed": 1,
                "length": 3,
                "inputs": {"a": [-2147483648, 2147483647, -7], "b": [1, -1, 12]},
            },
        ),
    ]
    if include_max:
        cases.append(("max256", {"dataset": "seeded", "seed": 7, "length": 256}))
    for name, forced in (("corrupt8", False), ("forced_pass_corrupt8", True)):
        cases.append(
            (
                name,
                {
                    "dataset": "seeded",
                    "seed": 1,
                    "length": 8,
                    "inject_mismatch": True,
                    "force_guest_pass": forced,
                },
            )
        )
    return cases


def _snapshot(engine, project, receipt, simulate):
    from salam_workbench.checks import source_identity
    from salam_workbench.configurator import compiled_identity, verify_engine

    git = subprocess.run(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "rev-parse",
            "HEAD",
        ],
        cwd=engine,
        capture_output=True,
        text=True,
        check=True,
    )
    binary = engine / "build/ARM/gem5.opt"
    result = {
        "git_head": git.stdout.strip(),
        "study_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": _hash(Path(__file__).resolve()),
        },
        "compiled_source_sha256": compiled_identity(engine)["sha256"],
        "tooling": source_identity(project),
        "runtime_configuration_and_benchmarks": {
            path.relative_to(engine).as_posix(): _hash(path)
            for directory in (
                engine / "configs",
                engine / "benchmarks/common",
                engine / "benchmarks/sys_validation/vadd",
            )
            for path in sorted(directory.rglob("*"))
            if path.is_file()
            and (
                path.suffix in (".py", ".c", ".cpp", ".h", ".yml", ".yaml", ".s", ".ld")
                or path.name == "Makefile"
            )
        },
        "build_receipt": {"path": str(receipt), "sha256": _hash(receipt)},
        "binary": {
            "path": str(binary),
            "sha256": _hash(binary) if binary.is_file() else None,
        },
    }
    if simulate:
        result["verified_engine"] = verify_engine(engine, receipt)
    else:
        result["qualification"] = "not_verified_prepare_only"
    return result


def _checked_artifact(run_directory, run, relative):
    path = run_directory / relative
    if path.resolve(strict=True) != path or path.is_symlink():
        raise ValueError("Linked or escaped run artifact: " + relative)
    records = [
        item for item in run.get("artifacts", []) if item.get("path") == relative
    ]
    if len(records) != 1 or records[0].get("sha256") != _hash(path):
        raise ValueError("Missing or stale recorded artifact: " + relative)
    return path


def _witness_study_system(pipeline, directory, run):
    """Supplement the generic witness's single unmapped bare-metal option."""
    witness = pipeline["system_witness"]
    effective = pipeline["system_configuration"]["effective"]
    checks = witness["checks"]
    if witness.get("issues") != [] or set(checks) != set(effective):
        raise ValueError("System witness has issues or omits an effective option")
    if any(checks[key].get("requested") != value for key, value in effective.items()):
        raise ValueError("System witness options differ from the effective request")
    unmapped = witness.get("unmapped_options")
    if witness.get("state") == "passed" and unmapped == []:
        if not all(row.get("status") == "passed" for row in checks.values()):
            raise ValueError("An effective system option did not pass")
        return {"state": "passed", "pipeline_state": "passed"}

    bare = checks.get("bare-metal", {})
    if (
        witness.get("state") != "partial"
        or unmapped != ["bare-metal"]
        or effective.get("bare-metal") is not True
        or bare.get("status") != "unwitnessed"
        or bare.get("requested") is not True
        or bare.get("observed") is not None
        or any(
            row.get("status") != "passed"
            for key, row in checks.items()
            if key != "bare-metal"
        )
    ):
        raise ValueError("System witness has a gap outside the bare-metal mapping")

    elf = directory / "workspace/benchmarks/sys_validation/vadd/sw/main.elf"
    build = pipeline["vadd_build_witness"]["guest_elf"]
    digest = _hash(elf)
    if build.get("path") != str(elf) or build.get("sha256") != digest:
        raise ValueError("Staged ARM ELF differs from the build witness")
    with elf.open("rb") as stream:
        header = stream.read(20)
    if (
        header[:7] != b"\x7fELF\x01\x01\x01"
        or int.from_bytes(header[16:18], "little") != 2  # ET_EXEC
        or int.from_bytes(header[18:20], "little") != 40  # EM_ARM
    ):
        raise ValueError("Staged guest is not a little-endian ARM32 ELF executable")

    argv = run["argv"]
    for option, expected in (
        ("--bare-metal", "--bare-metal"),
        ("--kernel", "--kernel=" + str(elf)),
    ):
        if [arg for arg in argv if arg.split("=", 1)[0] == option] != [expected]:
            raise ValueError("Simulator argv lacks the expected " + option)
    run_directory = Path(pipeline["run_directory"]).resolve(strict=True)
    run_directory.relative_to(directory)
    config = _checked_artifact(run_directory, run, "simulator/config.ini")
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(config.read_text(encoding="utf-8"))
    workload = ini["system.workload"]
    if (
        ini["system"].get("workload") != "system.workload"
        or workload.get("type") != "ArmFsWorkload"
        or workload.get("object_file") != str(elf)
        or any(
            workload.get(field) != ""
            for field in ("boot_loader", "dtb_filename", "initrd_filename")
        )
    ):
        raise ValueError("Effective ARM workload does not boot the staged ELF directly")

    entries = [item for item in run["inputs"] if item.get("path") == str(elf)]
    if len(entries) != 1:
        raise ValueError("Run receipt lacks one staged guest ELF input")
    record = entries[0]
    snapshot = record.get("snapshot", {})
    relative = snapshot.get("path", "")
    if (
        record.get("sha256") != digest
        or record.get("sha256_after_run") != digest
        or record.get("unchanged_after_run") is not True
        or snapshot.get("sha256") != digest
        or snapshot.get("sha256_after_run") != digest
        or snapshot.get("unchanged_after_run") is not True
        or Path(relative).parent != Path("inputs")
        or _hash(_checked_artifact(run_directory, run, relative)) != digest
    ):
        raise ValueError("Recorded guest ELF or its archived snapshot changed")
    return {
        "state": "passed",
        "pipeline_state": "partial",
        "mapped_options": sorted(set(checks) - {"bare-metal"}),
        "bare_metal": {
            "argv_flag": "--bare-metal",
            "workload_type": workload["type"],
            "guest_elf": {"path": str(elf), "sha256": digest},
            "archived_elf": {"path": relative, "sha256": digest},
            "config": {"path": str(config), "sha256": _hash(config)},
        },
    }


def _run_evidence(pipeline, directory, spec):
    from salam_workbench.benchmark_validation import (
        assess_configured_output,
        numerical_output_relative,
    )
    from salam_workbench.fu_experiments import inspect_fu_invocation
    from salam_workbench.vadd_diagnostic import witness_vadd_execution

    run_directory = Path(pipeline["run_directory"]).resolve(strict=True)
    run_directory.relative_to(directory.resolve(strict=True))
    run_path = run_directory / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    required = run.get("required_artifact_checks")
    if not required or any(item.get("available") is not True for item in required):
        raise ValueError("Missing required simulator artifacts")
    from salam_workbench.runner import EXPECTED_EXIT_REASON

    if (run.get("simulator_exit") or {}).get("reason") != EXPECTED_EXIT_REASON:
        raise ValueError("Simulator exit does not establish guest completion")
    raw = _checked_artifact(run_directory, run, numerical_output_relative(pipeline))
    fixture = directory / "benchmark-fixture.json"
    oracle = assess_configured_output(spec, raw, fixture)
    _save(directory / "study-oracle-replay.json", oracle)
    config = _checked_artifact(run_directory, run, "simulator/config.ini")
    traces = [
        name
        for name in run.get("required_artifacts", [])
        if name.startswith("simulator/observability/fu-scheduling-")
        and name.endswith(".invocation-1.json")
    ]
    if not traces:
        raise ValueError("No required direct SALAM functional-unit traces")
    invocations = [
        inspect_fu_invocation(_checked_artifact(run_directory, run, name), config)
        for name in traces
    ]
    fu = {
        "state": "passed"
        if all(row.get("state") == "passed" for row in invocations)
        else "failed",
        "invocations": invocations,
    }
    if fu["state"] != "passed":
        raise ValueError("Direct SALAM functional-unit replay did not pass")
    _save(directory / "study-fu-replay.json", fu)
    case = spec["benchmark_input"]
    # A completed guest may deliberately reject its corrupted output. This
    # opt-in attests hardware activity only; both numerical checks must fail
    # at the expected index before the study accepts that negative control.
    allow_failed_guest = (
        case.get("inject_mismatch") is True
        and case.get("force_guest_pass", False) is False
    )
    activity = witness_vadd_execution(
        run_directory, spec, fu, allow_failed_guest=allow_failed_guest
    )
    if activity.get("state") != "passed":
        raise ValueError("Fresh VADD runtime activity replay did not pass")
    _save(directory / "study-vadd-runtime-replay.json", activity)
    return run, raw, fixture, oracle, activity


def _numpy_check(project, directory, raw, fixture, transport):
    receipt = directory / "study-numpy.json"
    command = [
        sys.executable,
        "-B",
        str(project / "scripts/verify_numpy_outputs.py"),
        "--fixture",
        str(fixture),
        "--raw-output",
        str(raw),
        "--output-transport",
        transport,
        "--expected-fixture-file-sha256",
        _hash(fixture),
        "--expected-output-sha256",
        _hash(raw),
        "--receipt",
        str(receipt),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (directory / "study-numpy.stdout.txt").write_text(
        completed.stdout, encoding="utf-8"
    )
    (directory / "study-numpy.stderr.txt").write_text(
        completed.stderr, encoding="utf-8"
    )
    if not receipt.is_file():
        raise ValueError("Standalone NumPy checker did not produce its receipt")
    result = json.loads(receipt.read_text(encoding="utf-8"))
    if result.get("state") not in ("passed", "failed"):
        raise ValueError(
            "NumPy checker rejected the evidence: " + str(result.get("error"))
        )
    if completed.returncode != (0 if result["state"] == "passed" else 1):
        raise ValueError("NumPy process exit disagrees with its assessment")
    return result


def run_study(engine, receipt, output, *, simulate=False, include_max=False):
    engine = Path(engine).resolve(strict=True)
    receipt = Path(receipt).resolve(strict=True)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite an existing study: " + str(output))
    output = output.resolve()
    # The installed script belongs to the same Workbench that imports the API.
    project = Path(__file__).resolve().parents[1]
    if not (project / "salam_workbench").is_dir():
        project = engine / "workbench"  # Standalone local draft only.
    sys.path.insert(0, str(project))
    from salam_workbench.configurator import PROJECT, run_configuration, validate_spec

    if Path(PROJECT).resolve() != project.resolve():
        raise ValueError("Imported configuration API belongs to another Workbench")
    planned = _cases(include_max)
    output.mkdir(parents=True, exist_ok=False)
    study = {
        "schema_version": 1,
        "kind": "vadd_diagnostic_study",
        "state": "incomplete",
        "simulation_requested": simulate,
        "scope": "Actual staged preparation"
        + (
            ", numerical simulations, independent NumPy, and direct SALAM activity"
            if simulate
            else "; simulation and runtime controls are not executed"
        ),
        "started_utc": _now(),
        "engine": str(engine),
        "project": str(project),
        "requested_case_names": [name for name, _ in planned],
        "requested_case_count": len(planned),
        "cases": [],
        "errors": [],
        "negative_controls": "pending" if simulate else "not_run_prepare_only",
    }
    _save(output / "study.json", study)
    before = None
    try:
        before = _snapshot(engine, project, receipt, simulate)
        _save(output / "provenance-before.json", before)
        for name, case in planned:
            spec = validate_spec(
                {
                    "schema_version": 1,
                    "name": "vadd_" + name,
                    "benchmark": "benchmarks/sys_validation/vadd",
                    "builder": "native",
                    "benchmark_input": dict(
                        {"output_transport": "file", "verbose": False}, **case
                    ),
                    "system": {
                        "mem-size": "64MB",
                        "cpu-clock": "2GHz",
                        "sys-clock": "1GHz",
                        "cacheline_size": 64,
                    },
                    "correctness": {"expected_passed_markers": 1},
                    "timeout_seconds": 60,
                }
            )
            entry = {
                "name": name,
                "kind": "negative_control"
                if case.get("inject_mismatch")
                else "positive",
                "state": "pending",
                "input": copy.deepcopy(case),
            }
            study["cases"].append(entry)
            spec_path = output / (name + ".specification.json")
            _save(spec_path, spec)
            _save(output / "study.json", study)
            directory = output / name
            pipeline = run_configuration(
                engine,
                spec_path,
                directory,
                simulate=simulate,
                configured_receipt=receipt,
            )
            for source in pipeline.get("staging", {}).get("inputs", []):
                if _hash(source["path"]) != source.get("sha256"):
                    raise ValueError(
                        name + ": original source changed during configuration"
                    )
            entry.update(
                pipeline_state=pipeline.get("state"),
                pipeline_stage=pipeline.get("stage"),
                evidence_directory=str(directory),
            )
            if not simulate:
                if (pipeline.get("state"), pipeline.get("stage")) != (
                    "prepared",
                    "complete",
                ):
                    raise ValueError(
                        name
                        + ": preparation did not complete: "
                        + repr(pipeline.get("errors"))
                    )
                if pipeline.get("vadd_build_witness", {}).get("state") != "passed":
                    raise ValueError(name + ": actual VADD build witness is missing")
                entry["state"] = "prepared"
            else:
                run, raw, fixture, oracle, activity = _run_evidence(
                    pipeline, directory, spec
                )
                numpy_check = _numpy_check(
                    project,
                    directory,
                    raw,
                    fixture,
                    case.get("output_transport", "file"),
                )
                if entry["kind"] == "negative_control":
                    errors = _negative_errors(
                        pipeline,
                        run,
                        oracle,
                        numpy_check,
                        case["length"],
                        case.get("force_guest_pass", False),
                    )
                    if errors:
                        raise ValueError(name + ": " + "; ".join(errors))
                    entry["state"] = "expected_numerical_failure"
                else:
                    if (pipeline.get("state"), pipeline.get("stage")) != (
                        "passed",
                        "complete",
                    ):
                        raise ValueError(name + ": checked simulation did not pass")
                    for key in (
                        "build_input_witness",
                        "vadd_build_witness",
                        "vadd_execution_witness",
                        "fu_scheduling_witness",
                        "parameter_witness",
                        "profile_witness",
                        "output_transport_witness",
                    ):
                        if pipeline.get(key, {}).get("state") != "passed":
                            raise ValueError(
                                name + ": required pipeline witness failed: " + key
                            )
                    system = _witness_study_system(pipeline, directory, run)
                    _save(directory / "study-system-replay.json", system)
                    entry["system_witness"] = system
                    if (
                        oracle.get("state") != "passed"
                        or numpy_check.get("state") != "passed"
                    ):
                        raise ValueError(
                            name + ": complete independent numerical checks failed"
                        )
                    entry["state"] = "passed"
                entry.update(
                    output_sha256=_hash(raw),
                    observed_output_sha256=oracle.get("output_sha256"),
                    oracle_state=oracle.get("state"),
                    numpy_state=numpy_check.get("state"),
                    runtime_activity=activity,
                )
            _save(output / "study.json", study)
        if simulate:
            by_name = {row["name"]: row for row in study["cases"]}
            if (
                by_name["tiny8"]["observed_output_sha256"]
                == by_name["reseed8"]["observed_output_sha256"]
            ):
                raise ValueError(
                    "Changing the input seed did not change actual observed output words"
                )
            study["negative_controls"] = "both_expected_numerical_failures_verified"
        after = _snapshot(engine, project, receipt, simulate)
        _save(output / "provenance-after.json", after)
        if after != before:
            raise ValueError(
                "Engine, binary, build receipt or Workbench source changed during study"
            )
        study["provenance_unchanged"] = True
        study["state"] = "passed" if simulate else "prepared"
    except Exception as error:
        study["state"] = "failed"
        study["errors"].append(type(error).__name__ + ": " + str(error))
        if study["cases"] and study["cases"][-1]["state"] == "pending":
            study["cases"][-1]["state"] = "failed"
        try:
            after = _snapshot(engine, project, receipt, simulate)
            _save(output / "provenance-after.json", after)
            study["provenance_unchanged"] = before is not None and before == after
        except Exception as provenance_error:
            study["errors"].append("After snapshot: " + str(provenance_error))
    study["unattempted_cases"] = [
        name
        for name, _ in planned
        if name not in {row["name"] for row in study["cases"]}
    ]
    study["finished_utc"] = _now()
    _save(output / "study.json", study)
    return study


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--build-receipt", required=True, type=Path)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Fresh study directory; existing paths are refused",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Explicitly run all simulations and both negative controls",
    )
    parser.add_argument(
        "--include-max",
        action="store_true",
        help="Also test the bounded 256-element case",
    )
    options = parser.parse_args(argv)
    try:
        result = run_study(
            options.engine,
            options.build_receipt,
            options.output,
            simulate=options.simulate,
            include_max=options.include_max,
        )
    except Exception as error:
        result = {
            "state": "failed",
            "errors": [type(error).__name__ + ": " + str(error)],
        }
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["state"] in ("passed", "prepared") else 1


if __name__ == "__main__":
    raise SystemExit(main())
