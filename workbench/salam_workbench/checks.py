"""Layered local checks with durable evidence; expensive simulation is explicit."""
import argparse
import datetime
import hashlib
import importlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from .runner import ENV_ALLOWLIST, _terminate_owned_process, _write_json, file_hash
from .toolchain_profile import require_legacy_harness

PROJECT = Path(__file__).resolve().parents[1]
TIERS = ("fast", "config", "gui", "collector", "gemm")
FAST_MODULES = (
    "test_benchmark_oracles",
    "test_benchmark_inputs",
    "test_configurable_breadth",
    "test_benchmark_overlays",
    "test_builds",
    "test_checks",
    "test_doctor",
    "test_toolchain_profile",
    "test_legacy_harness_guards",
    "test_linker_selection",
    "test_numpy_outputs",
    "test_observability",
    "test_observability_report",
    "test_offline_viewer",
    "test_provenance",
    "test_regression",
    "test_regression_negative",
    "test_release",
    "test_report",
    "test_runner",
    "test_workbench_jobs",
    "test_workbench_results",
    "test_workbench_tier_coverage",
)
CONFIG_MODULES = (
    "test_benchmark_validation",
    "test_registerbank_adapter",
    "test_config",
    "test_facade",
    "test_model_data",
    "test_variant_report",
    "test_config_contract",
    "test_configurator",
    "test_modern_build_identity",
    "test_configurator_review",
    "test_hardware_codegen",
    "test_system_witness",
    "test_configuration_import",
    "test_topology_adapter",
    "test_systembuilder_template",
    "test_profile_witness",
    "test_configurator_gui_bridge",
    "test_build_inputs",
    "test_ir_toolchain",
    "test_output_transport_abi",
    "test_gui_execution",
    "test_gui_editor",
    "test_gui_effective",
    "test_hardware_variants",
    "test_fu_capability",
    "test_fu_experiments",
    "test_portability",
    "test_workbench_catalog",
    "test_workbench_completion",
)
GUI_MODULES = (
    "test_offline_viewer",
    "test_gui_editor_qt",
    "test_toolchain_gui",
    "test_workbench_window",
    "test_workbench_topology",
    "test_process_view",
)
GRAPH_TESTS = frozenset(
    (
        "test_actual_recovered_parser_contract_and_hash_gate",
        "test_non_instruction_dot_does_not_claim_available_cdfg",
    )
)


class DependencyUnavailable(RuntimeError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def source_identity(project, engine=None, tier="fast"):
    """Fingerprint actual local tooling files, without Git writes or shell state."""
    project = Path(project).resolve()
    sources = []
    for directory in ("salam_workbench", "tests"):
        sources.extend(
            path
            for path in (project / directory).rglob("*.py")
            if "__pycache__" not in path.parts
        )
    sources.extend(project.glob("requirements*.txt"))
    independent_checker = project / "scripts/verify_numpy_outputs.py"
    if independent_checker.is_file():
        sources.append(independent_checker)
    sources.extend(
        path
        for path in (project / "experiments/breadth/overlays").rglob("*")
        if path.is_file() and path.suffix in (".cpp", ".h")
    )
    sources.extend((project / ".github" / "workflows").glob("*.yml"))
    files = {}
    for path in sorted(set(sources)):
        if path.is_symlink():
            raise ValueError("Tooling source must not be a symlink: " + str(path))
        path.resolve().relative_to(project)
        files[path.relative_to(project).as_posix()] = file_hash(path)
    engine_files = {}
    if engine is not None and tier == "collector":
        for relative in (
            "src/hwacc/workbench_statistics.hh",
            "src/hwacc/tests/test_workbench_statistics.cc",
        ):
            path = Path(engine) / relative
            engine_files[relative] = file_hash(path)
    canonical = json.dumps(
        {"files": files, "engine_files": engine_files},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "files": files,
        "engine_files": engine_files,
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _snapshot_sources(identity, project, engine, evidence):
    """Copy bounded source files once; a hash list alone cannot restore old code."""
    for group, root in (
        ("files", Path(project)),
        ("engine_files", Path(engine) if engine else None),
    ):
        for relative, expected in identity[group].items():
            source = root / relative
            if source.stat().st_size > 16 * 1024 * 1024:
                raise ValueError(
                    "Check source exceeds 16 MiB snapshot limit: " + relative
                )
            destination = evidence / "source-snapshot" / group / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as incoming, destination.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            if file_hash(destination) != expected:
                raise RuntimeError(
                    "Check source changed while snapshotting: " + relative
                )


def build_plan(
    tier,
    project,
    evidence,
    engine=None,
    *,
    allow_simulation=False,
    build_engine=False,
    jobs=8,
):
    project, evidence = Path(project).resolve(), Path(evidence).resolve()
    # Preserve the venv invocation; _execute_step hashes the resolved file.
    python = str(Path(sys.executable).absolute())
    prefix = [python, "-B", "-m", "salam_workbench.checks"]
    if tier not in TIERS:
        raise ValueError("Unknown check tier")
    if tier == "gemm":
        require_legacy_harness(project, "checks --tier gemm")
    if build_engine and (tier != "gemm" or not allow_simulation):
        raise ValueError("--build-engine requires the gemm tier and --allow-simulation")
    if type(jobs) is not int or not 1 <= jobs <= 32:
        raise ValueError("jobs must be an integer from 1 to 32")
    if tier in ("fast", "config", "gui"):
        return [
            {
                "name": "unit-" + tier,
                "argv": prefix
                + [
                    "--internal-unit-tier",
                    tier,
                    "--unit-result",
                    str(evidence / "unit-results.json"),
                ],
                "cwd": str(project),
                "environment_overrides": {"QT_QPA_PLATFORM": "offscreen"}
                if tier == "gui"
                else {},
            }
        ]
    if engine is None:
        raise ValueError("--engine is required for this tier")
    engine = Path(engine).expanduser().resolve(strict=True)
    if not engine.is_dir():
        raise ValueError("engine must be a directory")
    if tier == "collector":
        compiler = shutil.which("g++")
        if not compiler:
            raise DependencyUnavailable(
                "g++ is unavailable; the collector tier was not run"
            )
        source = engine / "src/hwacc/tests/test_workbench_statistics.cc"
        header = engine / "src/hwacc/workbench_statistics.hh"
        if not source.is_file() or not header.is_file():
            raise DependencyUnavailable(
                "The standalone collector source/header are unavailable"
            )
        executable = evidence / (
            "collector-test.exe" if os.name == "nt" else "collector-test"
        )
        return [
            {
                "name": "compiler-version",
                "argv": [compiler, "--version"],
                "cwd": str(project),
                "environment_overrides": {},
            },
            {
                "name": "compile-collector",
                "argv": [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I" + str(engine / "src"),
                    str(source),
                    "-o",
                    str(executable),
                ],
                "cwd": str(project),
                "environment_overrides": {},
            },
            {
                "name": "collector-events",
                "argv": [str(executable)],
                "cwd": str(project),
                "environment_overrides": {},
            },
            {
                "name": "verify-collector-json",
                "argv": prefix
                + [
                    "--internal-collector-output",
                    str(evidence / "02-collector-events.stdout"),
                    "--unit-result",
                    str(evidence / "collector-validation.json"),
                ],
                "cwd": str(project),
                "environment_overrides": {},
            },
        ]
    if not allow_simulation:
        raise ValueError(
            "The gemm tier requires --allow-simulation; no simulator was launched"
        )
    command = [
        python,
        "-B",
        "-m",
        "salam_workbench.gemm",
        "reproduce",
        "--engine",
        str(engine),
        "--runs-root",
        str(evidence / "runs"),
        "--jobs",
        str(jobs),
    ]
    if build_engine:
        command.append("--build-engine")
    return [
        {
            "name": "gemm-reproduction",
            "argv": command,
            "cwd": str(project),
            "environment_overrides": {},
        },
        {
            "name": "verify-gemm-session",
            "argv": prefix
            + [
                "--internal-gemm-output",
                str(evidence / "00-gemm-reproduction.stdout"),
                "--unit-result",
                str(evidence / "gemm-validation.json"),
            ],
            "cwd": str(project),
            "environment_overrides": {},
        },
    ]


def _execute_step(step, index, evidence, timeout):
    result = dict(step)
    result.update(started_at=_now(), return_code=None)
    stem = "{:02d}-{}".format(index, step["name"])
    stdout_path, stderr_path = evidence / (stem + ".stdout"), evidence / (
        stem + ".stderr"
    )
    result.update(stdout=stdout_path.name, stderr=stderr_path.name)
    executable = Path(step["argv"][0]).resolve(strict=True)
    result["executable_sha256"] = file_hash(executable)
    environment = {
        key: value for key, value in os.environ.items() if key in ENV_ALLOWLIST
    }
    environment.update(step.get("environment_overrides", {}))
    options = {"cwd": step["cwd"], "env": environment, "shell": False}
    if os.name == "posix":
        options["start_new_session"] = True
    elif os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            step["argv"], stdout=stdout, stderr=stderr, **options
        )
        result["process_id"] = process.pid
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            _terminate_owned_process(process)
        except (KeyboardInterrupt, SystemExit):
            _terminate_owned_process(process)
            raise
        result["return_code"] = process.returncode
    result["finished_at"] = _now()
    result["executable_unchanged_after_run"] = (
        file_hash(executable) == result["executable_sha256"]
    )
    return result


def run_checks(
    tier,
    *,
    project_root=PROJECT,
    engine=None,
    evidence_root=None,
    allow_simulation=False,
    build_engine=False,
    jobs=8,
    timeout_seconds=900,
    check_id=None,
    plan_only=False,
):
    """Keep a unique receipt even for refusal, unavailable tools or command failure."""
    project = Path(project_root).resolve()
    root = (
        Path(evidence_root).resolve()
        if evidence_root
        else project / "evidence" / "checks"
    )
    identifier = check_id or (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + tier
        + "-"
        + uuid.uuid4().hex[:10]
    )
    if not isinstance(identifier, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}", identifier
    ):
        raise ValueError("check_id must be a safe directory name")
    root.mkdir(parents=True, exist_ok=True)
    directory = root / identifier
    directory.mkdir(exist_ok=False)
    record = {
        "schema_version": 1,
        "kind": "workbench_check",
        "tier": tier,
        "check_id": identifier,
        "state": "planned",
        "started_at": _now(),
        "evidence_directory": str(directory),
        "project": str(project),
        "engine": str(engine) if engine else None,
        "allow_simulation": allow_simulation,
        "build_engine": build_engine,
        "plan_only": plan_only,
        "timeout_seconds_per_step": timeout_seconds,
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "steps": [],
        "issues": [],
        "artifacts": [],
    }
    _write_json(directory / "check.json", record)
    try:
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        plan = build_plan(
            tier,
            project,
            directory,
            engine,
            allow_simulation=allow_simulation,
            build_engine=build_engine,
            jobs=jobs,
        )
        _write_json(directory / "plan.json", {"tier": tier, "steps": plan})
        record["tooling_before"] = source_identity(project, engine, tier)
        _snapshot_sources(record["tooling_before"], project, engine, directory)
        if not plan_only:
            record["state"] = "running"
            _write_json(directory / "check.json", record)
            for index, step in enumerate(plan):
                completed = _execute_step(step, index, directory, timeout_seconds)
                record["steps"].append(completed)
                _write_json(directory / "check.json", record)
                if completed.get("timed_out"):
                    record["state"] = "timed_out"
                    record["issues"].append(
                        "Check step exceeded its timeout: " + step["name"]
                    )
                    break
                if not completed["executable_unchanged_after_run"]:
                    record["state"] = "incomplete"
                    record["issues"].append(
                        "Check executable changed while running: " + step["name"]
                    )
                    break
                if completed["return_code"] != 0:
                    record["state"] = "failed"
                    record["issues"].append("Check command failed: " + step["name"])
                    break
            else:
                result_name = (
                    "unit-results.json"
                    if tier in ("fast", "config", "gui")
                    else "collector-validation.json"
                    if tier == "collector"
                    else "gemm-validation.json"
                )
                result = json.loads(
                    (directory / result_name).read_text(encoding="utf-8")
                )
                record["validation_result"] = result
                record["state"] = (
                    "passed" if result.get("success") is True else "failed"
                )
                if record["state"] == "failed":
                    record["issues"].append(
                        "The tier's required validation result did not pass"
                    )
            if (
                tier in ("fast", "config", "gui")
                and (directory / "unit-results.json").is_file()
            ):
                unit_result = json.loads((directory / "unit-results.json").read_text())
                record["validation_result"] = unit_result
                if unit_result.get("available") is False:
                    record["state"] = "unavailable"
    except DependencyUnavailable as error:
        record.update(state="unavailable")
        record["issues"].append(str(error))
    except (KeyboardInterrupt, SystemExit):
        record["state"] = "incomplete"
        record["issues"].append("Check invocation interrupted")
        raise
    except Exception as error:
        record["state"] = "failed"
        record["issues"].append(type(error).__name__ + ": " + str(error))
    finally:
        if "tooling_before" in record:
            try:
                record["tooling_after"] = source_identity(project, engine, tier)
                record["tooling_unchanged"] = (
                    record["tooling_before"] == record["tooling_after"]
                )
                if not record["tooling_unchanged"]:
                    record["issues"].append(
                        "Tooling sources changed during this check; rerun the final source state"
                    )
                    if record["state"] == "passed":
                        record["state"] = "incomplete"
            except (OSError, ValueError) as error:
                record["tooling_unchanged"] = False
                record["issues"].append(
                    "Post-check source identity failed: " + str(error)
                )
                if record["state"] == "passed":
                    record["state"] = "incomplete"
        for path in sorted(directory.rglob("*")):
            if path.name in ("check.json", "check.json.writing") or not path.is_file():
                continue
            try:
                path.resolve().relative_to(directory)
                if path.is_symlink():
                    raise ValueError("Symlink")
                record["artifacts"].append(
                    {
                        "path": path.relative_to(directory).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": file_hash(path),
                    }
                )
            except (OSError, ValueError) as error:
                record["issues"].append(
                    "Unsafe/unreadable evidence artifact: " + str(error)
                )
                if record["state"] == "passed":
                    record["state"] = "incomplete"
        record["finished_at"] = _now()
        _write_json(directory / "check.json", record)
    return record


def _flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _flatten(test)
        else:
            yield test


def _gui_test(test):
    method = test.id().rsplit(".", 1)[-1]
    gui_only = set(GUI_MODULES) - set(FAST_MODULES) - set(CONFIG_MODULES)
    return (
        test.__class__.__module__ in gui_only
        or method.startswith("test_offscreen_")
        or method in GRAPH_TESTS
    )


def _unit_test_owner(module, test):
    """Assign every discovered method once using its registered module.

    Dedicated modules run whole. Only modules explicitly shared with the GUI
    tier split methods by the recovered viewer's dependency convention.
    Ambiguous ownership is an error, rather than a reason to drop a method.
    """
    owners = {
        tier
        for tier, modules in (
            ("fast", FAST_MODULES),
            ("config", CONFIG_MODULES),
            ("gui", GUI_MODULES),
        )
        if module in modules
    }
    if len(owners) == 1:
        return owners.pop()
    if "gui" in owners:
        if _gui_test(test):
            return "gui"
        owners.remove("gui")
    if len(owners) == 1:
        return owners.pop()
    raise ValueError("Test has no unique tier owner: {} ({})".format(test.id(), module))


def run_unit_tier(tier, destination):
    """A subprocess entrypoint, with explicit coverage and dependency outcomes."""
    result = {
        "kind": "unit_tier",
        "tier": tier,
        "available": True,
        "success": False,
        "selected_tests": [],
        "discovered_tests": [],
        "excluded_tests": [],
        "unassigned_tests": [],
        "tests_run": 0,
        "skipped": [],
        "failures": [],
        "errors": [],
    }
    try:
        dependencies = (
            ("yaml",)
            if tier == "config"
            else ("PySide6.QtWidgets", "networkx", "numpy")
            if tier == "gui"
            else ()
        )
        for name in dependencies:
            importlib.import_module(name)
        tests_directory = PROJECT / "tests"
        sys.path.insert(0, str(tests_directory))
        modules = (
            CONFIG_MODULES
            if tier == "config"
            else GUI_MODULES
            if tier == "gui"
            else FAST_MODULES
        )
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for module in modules:
            for test in _flatten(loader.loadTestsFromName(module)):
                result["discovered_tests"].append(test.id())
                try:
                    owner = (
                        tier
                        if isinstance(test, unittest.loader._FailedTest)
                        else _unit_test_owner(module, test)
                    )
                except ValueError as error:
                    result["unassigned_tests"].append(
                        {"test": test.id(), "module": module, "reason": str(error)}
                    )
                    continue
                if owner == tier:
                    suite.addTest(test)
                    result["selected_tests"].append(test.id())
                else:
                    result["excluded_tests"].append(
                        {"test": test.id(), "module": module, "owner": owner}
                    )
        known_modules = set(FAST_MODULES) | set(CONFIG_MODULES) | set(GUI_MODULES)
        result["unassigned_test_files"] = sorted(
            path.name
            for path in tests_directory.glob("test_*.py")
            if path.stem not in known_modules
        )
        executed = unittest.TextTestRunner(verbosity=2).run(suite)
        result.update(
            tests_run=executed.testsRun,
            skipped=[
                {"test": item.id(), "reason": reason}
                for item, reason in executed.skipped
            ],
            failures=[test.id() for test, _ in executed.failures],
            errors=[test.id() for test, _ in executed.errors],
            success=(
                executed.wasSuccessful()
                and executed.testsRun > 0
                and not result["unassigned_tests"]
                and not result["unassigned_test_files"]
            ),
        )
    except ImportError as error:
        result.update(available=False, diagnostic=str(error))
    finally:
        _write_json(Path(destination), result)
    return 0 if result["success"] else 2 if not result["available"] else 1


def _verify_collector(output, destination):
    from .observability import load_observability

    parsed = load_observability(output, expected_sha256=file_hash(output))
    result = {
        "kind": "collector_unit_validation",
        "success": parsed["contract_valid"],
        "simulation_evidence": False,
        "meaning": "Synthetic collector events, not a gem5 run",
        "observability": parsed,
    }
    _write_json(Path(destination), result)
    return 0 if result["success"] else 1


def _verify_gemm(output, destination):
    from .report import compare_runs, load_run

    lines = Path(output).read_text(encoding="utf-8", errors="replace").splitlines()
    locations = [
        line[len("Session evidence: ") :]
        for line in lines
        if line.startswith("Session evidence: ")
    ]
    if len(locations) != 1:
        raise ValueError("GEMM command did not identify exactly one new session")
    session_path = Path(locations[0]).resolve()
    session_path.relative_to(PROJECT / "evidence")
    session = json.loads((session_path / "session.json").read_text())
    runs = session.get("baseline_runs", [])
    if session.get("state") != "passed" or len(runs) != 2:
        raise ValueError(
            "GEMM session did not finish with two successful baseline runs"
        )
    evidence_runs = Path(output).resolve().parent / "runs"
    baseline_paths = [Path(item["directory"]).resolve() for item in runs]
    for path in baseline_paths:
        path.relative_to(evidence_runs)
    if len(set(baseline_paths)) != 2:
        raise ValueError("Repeatability requires two distinct baseline run directories")
    comparison = compare_runs(*baseline_paths)
    negative_path = Path(session["negative_witness"]["directory"]).resolve()
    negative_path.relative_to(evidence_runs)
    if negative_path in baseline_paths:
        raise ValueError("The negative witness must have its own run directory")
    negative = load_run(negative_path)
    permitted_issues = {
        "Run state is not passed: failed",
        "Raw guest correctness evidence or recorded process exit does not satisfy the runner contract",
    }
    negative_ok = (
        negative["recorded_state"] == "failed"
        and (negative.get("raw_correctness") or {}).get("outcome") == "failed"
        and bool(negative["verified_required_artifacts"])
        and all(negative["verified_required_artifacts"].values())
        and all(issue in permitted_issues for issue in negative["issues"])
    )
    result = {
        "kind": "gemm_check_validation",
        "success": comparison["repeatability_accepted"] and negative_ok,
        "session_directory": str(session_path),
        "session_sha256": file_hash(session_path / "session.json"),
        "repeatability_accepted": comparison["repeatability_accepted"],
        "negative_witness_verified": negative_ok,
        "baseline_runs": [str(path) for path in baseline_paths],
        "issues": comparison["issues"],
        "negative_issues": negative["issues"],
    }
    _write_json(Path(destination), result)
    return 0 if result["success"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=TIERS)
    parser.add_argument("--engine")
    parser.add_argument("--evidence-root")
    parser.add_argument("--check-id")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--allow-simulation", action="store_true")
    parser.add_argument("--build-engine", action="store_true")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument(
        "--internal-unit-tier",
        choices=("fast", "config", "gui"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--internal-collector-output", help=argparse.SUPPRESS)
    parser.add_argument("--internal-gemm-output", help=argparse.SUPPRESS)
    parser.add_argument("--unit-result", help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if (
        options.internal_unit_tier
        or options.internal_collector_output
        or options.internal_gemm_output
    ):
        if not options.unit_result:
            parser.error("Internal validation requires a result destination")
        if options.internal_unit_tier:
            return run_unit_tier(options.internal_unit_tier, options.unit_result)
        if options.internal_collector_output:
            return _verify_collector(
                options.internal_collector_output, options.unit_result
            )
        return _verify_gemm(options.internal_gemm_output, options.unit_result)
    if not options.tier:
        parser.error("--tier is required")
    result = run_checks(
        options.tier,
        engine=options.engine,
        evidence_root=options.evidence_root,
        allow_simulation=options.allow_simulation,
        build_engine=options.build_engine,
        timeout_seconds=options.timeout,
        jobs=options.jobs,
        check_id=options.check_id,
        plan_only=options.plan_only,
    )
    print(
        json.dumps(
            {
                "state": result["state"],
                "tier": result["tier"],
                "evidence_directory": result["evidence_directory"],
                "issues": result["issues"],
            }
        )
    )
    return (
        0
        if result["state"] in ("passed", "planned")
        else 2
        if result["state"] == "unavailable"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
