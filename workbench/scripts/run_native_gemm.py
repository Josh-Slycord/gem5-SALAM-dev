#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Run an explicit retained/native GEMM comparison in separate evidence folders.

Without --simulate only a plan is saved. A reused simulator must have a valid
build receipt. No simulator source is changed, compiled, or pushed here.
"""
import argparse
import datetime
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workbench"))
from salam_workbench.benchmark_oracles import make_fixture, reference_outputs
from salam_workbench.configurator import (
    run_configuration,
    simulator_args,
    verify_engine,
)
from salam_workbench.regression import _environment
from salam_workbench.runner import EXPECTED_EXIT_REASON, file_hash, run_experiment

ACTORS = ("top", "gemm")
CLOCK_ACTORS = (
    "system.gemm_clstr.top",
    "system.gemm_clstr.top.llvm_interface",
    "system.gemm_clstr.gemm",
    "system.gemm_clstr.gemm.llvm_interface",
    "system.gemm_clstr.dma",
)


def save(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def checker_module():
    spec = importlib.util.spec_from_file_location(
        "native_gemm_differential", ROOT / "workbench/scripts/verify_native_gemm.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cases(selected=None):
    rows = selected or itertools.product((10, 3), (0, 1), (1, 16))
    result = []
    for period, limit, cycles in rows:
        if period not in (10, 3) or limit not in (0, 1) or cycles not in (1, 16):
            raise ValueError("Study cases require period10/3, limit0/1, cycles1/16")
        name = "p{}-cap{}-lat{}".format(period, limit, cycles)
        if name in [case["name"] for case in result]:
            raise ValueError("Duplicate study case")
        result.append(
            dict(name=name, period_ns=period, mul_limit=limit, mul_cycles=cycles)
        )
    return result


def command(argv, cwd, out, name, env):
    done = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180
    )
    (out / (name + ".stdout")).write_text(done.stdout)
    (out / (name + ".stderr")).write_text(done.stderr)
    record = dict(argv=list(map(str, argv)), cwd=str(cwd), returncode=done.returncode)
    save(out / (name + ".json"), record)
    if done.returncode:
        raise RuntimeError(name + " failed; see " + str(out))
    return record


def prepare(engine, receipt, directory, case, *, corrupt=False, builder="generated"):
    directory.mkdir(parents=True, exist_ok=False)
    fixtures = [make_fixture("gemm", "seeded", seed) for seed in (11, 29)]
    if reference_outputs(fixtures[0]) == reference_outputs(fixtures[1]):
        raise ValueError("Distinct launches must have distinct numerical outputs")
    fixture_paths = []
    for index, fixture in enumerate(fixtures, 1):
        path = directory / ("fixture-" + str(index) + ".json")
        save(path, fixture)
        fixture_paths.append(path)

    documents = list(
        yaml.safe_load_all(
            (engine / "benchmarks/sys_validation/gemm/config.yml").read_text()
        )
    )
    hardware = documents[0]["hw_config"]["gemm"]
    hardware["functional_units"] = {"integer_multiplier": {"limit": case["mul_limit"]}}
    hardware["instructions"]["mul"]["runtime_cycles"] = case["mul_cycles"]
    spec = {
        "schema_version": 1,
        "name": "native_gemm",
        "benchmark": "benchmarks/sys_validation/gemm",
        "base_address": case.get("base_address", "0x10020000"),
        "builder": builder,
        "configuration_documents": documents,
        "system": {"cpu-clock": "2GHz", "sys-clock": "1GHz", "cacheline_size": 64},
        "parameters": {
            section: {"clock_period": case["period_ns"]} for section in CLOCK_ACTORS
        },
        "correctness": {
            "expected_passed_markers": 2,
            "description": "Two distinct 8x8 int32 launches; raw output independently checked.",
        },
    }
    for actor in ACTORS:
        key = "system.gemm_clstr." + actor + ".llvm_interface"
        spec["parameters"][key]["fu_trace_event_limit"] = 1048576
    spec_path = directory / "specification.json"
    save(spec_path, spec)
    prepared = run_configuration(
        engine,
        spec_path,
        directory / "preparation",
        simulate=False,
        configured_receipt=receipt,
    )
    if prepared["state"] != "prepared":
        raise RuntimeError("Preparation failed: " + repr(prepared.get("errors")))
    workspace = Path(prepared["staging"]["workspace"])
    sw = workspace / spec["benchmark"] / "sw"
    source = ROOT / "workbench/experiments/native_gemm/main.cpp"
    driver = source.read_text()
    for key, token in (("a", "@INPUT_A@"), ("b", "@INPUT_B@")):
        arrays = ",".join(
            "{" + ",".join(map(str, fixture["inputs"][key])) + "}"
            for fixture in fixtures
        )
        if driver.count(token) != 1:
            raise ValueError("Guest template placeholder is not unique: " + token)
        driver = driver.replace(token, arrays)
    driver = driver.replace(
        "@HASHES@", ",".join(json.dumps(f["fixture_sha256"]) for f in fixtures)
    )
    if "@" in driver:
        raise ValueError("Unresolved guest template placeholder")
    (sw / "main-native.cpp").write_text(driver)
    env = _environment(workspace)
    argv = [
        "/usr/bin/arm-none-eabi-g++",
        "-g",
        "-O3",
        "-fcommon",
        "-lunistd",
        "-I",
        ".",
        "-fno-exceptions",
        "-c",
        "main-native.cpp",
        "-o",
        "main-native.o",
    ]
    if corrupt:
        argv[1:1] = ["-DRESET_INJECT_MISMATCH", "-DNATIVE_GEMM_FORCE_GUEST_PASS"]
    builds = [command(argv, sw, directory, "compile-guest", env)]
    builds.append(
        command(
            [
                "/usr/bin/arm-none-eabi-gcc",
                "-nostartfiles",
                "-Xlinker",
                "-Tboot.ld",
                "-o",
                "main-native.elf",
                "boot.o",
                "../../../common/syscalls.o",
                "main-native.o",
                "isr.o",
                "-nostartfiles",
            ],
            sw,
            directory,
            "link-guest",
            env,
        )
    )
    save(
        directory / "guest-build.json",
        {
            "source_template": str(source),
            "source_template_sha256": file_hash(source),
            "compiled_driver_sha256": file_hash(sw / "main-native.cpp"),
            "elf_sha256": file_hash(sw / "main-native.elf"),
            "compiler_sha256": file_hash(Path(argv[0]).resolve()),
            "linker_driver_sha256": file_hash(
                Path("/usr/bin/arm-none-eabi-gcc").resolve()
            ),
            "commands": builds,
            "transport": "direct UART; complete fixture-bound result frames",
            "corruption_and_false_guest_pass": corrupt,
        },
    )
    return workspace, spec, fixture_paths


def launch(engine, workspace, spec, directory, builder, *, required=True, kernel=None):
    selected = dict(spec, builder=builder)
    args = simulator_args(engine, workspace, selected)
    sw = workspace / spec["benchmark"] / "sw"
    kernel_path = Path(kernel) if kernel is not None else sw / "main-native.elf"
    args = [
        "--kernel=" + str(kernel_path) if item.startswith("--kernel=") else item
        for item in args
    ]
    env = _environment(workspace)
    inputs = [
        path
        for path in workspace.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    if kernel_path not in inputs:
        inputs.append(kernel_path)
    artifacts = [
        "simulator/config.ini",
        "simulator/stats.txt",
        "simulator/system.terminal",
    ] + [
        "simulator/observability/system.gemm_clstr."
        + actor
        + ".invocation-"
        + str(index)
        + ".json"
        for actor in ACTORS
        for index in (1, 2)
    ]
    if builder == "native":
        artifacts += [
            "simulator/native_factory.json",
            "simulator/native_configuration.json",
        ]
    return run_experiment(
        [str(engine / "build/ARM/gem5.opt")],
        args,
        cwd=workspace,
        runs_root=directory / "runs",
        run_id=builder,
        experiment={
            "schema_version": 1,
            "experiment_id": "native-gemm-" + builder,
            "correctness": {
                "required_guest_marker": "Check Passed",
                "rejected_guest_marker": "Check Failed",
                "required_simulator_exit": EXPECTED_EXIT_REASON,
            },
        },
        input_paths=inputs,
        env_overrides={"M5_PATH": str(workspace), "PATH": env["PATH"]},
        timeout_seconds=600,
        snapshot_inputs=True,
        required_artifacts=artifacts if required else [],
    )


def archive_generated_module(workspace, spec, directory):
    source = workspace / "configs/SALAM/generated" / (spec["name"] + ".py")
    archive = directory / "retained-generated-module"
    archive.mkdir()
    digest = file_hash(source)
    shutil.move(str(source), str(archive / source.name))
    # A stale pyc must not provide a hidden generated topology module.
    caches = source.parent / "__pycache__"
    if caches.exists():
        shutil.move(str(caches), str(archive / "__pycache__"))
    if source.exists():
        raise ValueError("Native route must run without generated topology module")
    save(
        directory / "generated-module-absence.json",
        {
            "original": str(source),
            "archived": str(archive / source.name),
            "sha256": digest,
            "absent_during_native_launch": True,
        },
    )


def native_receipt(run_directory):
    simulator = Path(run_directory) / "simulator"
    receipt = json.loads((simulator / "native_factory.json").read_text())
    model_path = simulator / "native_configuration.json"
    if receipt["model_file_sha256"] != file_hash(model_path):
        raise ValueError("Native normalized model changed")
    model = json.loads(model_path.read_text())
    payload = json.dumps(model, sort_keys=True, separators=(",", ":"))
    import hashlib

    if receipt["model_sha256"] != hashlib.sha256(payload.encode()).hexdigest():
        raise ValueError("Native canonical model identity differs")
    if (
        receipt.get("generated_python_executed") is not False
        or receipt.get("legacy_yaml_reload") is not False
        or receipt.get("cpp_interface") != "retained_typed_wrappers"
    ):
        raise ValueError("Native route did not preserve its construction contract")
    for source in receipt["source_files"].values():
        if file_hash(Path(source["path"])) != source["sha256"]:
            raise ValueError("Native construction source changed")
    return receipt


def positive_case(engine, receipt, output, case, checker):
    directory = output / "cases" / case["name"]
    workspace, spec, fixtures = prepare(engine, receipt, directory, case)
    retained = launch(engine, workspace, spec, directory, "generated")
    archive_generated_module(workspace, spec, directory)
    direct = launch(engine, workspace, spec, directory, "native")
    save(
        directory / "native-construction.json", native_receipt(direct["run_directory"])
    )
    report = checker.compare_runs(
        retained["run_directory"],
        direct["run_directory"],
        fixtures,
        expected_period_ns=case["period_ns"],
        expected_mul_limit=case["mul_limit"],
        expected_mul_cycles=case["mul_cycles"],
    )
    save(directory / "comparison.json", report)
    if report["state"] != "passed":
        raise RuntimeError(
            "Paired comparison failed: " + str(directory / "comparison.json")
        )
    witnesses = report["direct"]["multiplier_capacity_witnesses"]
    units = [item["units"][0] for item in witnesses]
    if any(
        unit["grants"] != 512 or unit["releases"] != 512 or unit["outstanding"] != 0
        for unit in units
    ):
        raise ValueError("Expected 512 balanced multiply leases per launch")
    if case["mul_limit"] == 0:
        if any(unit["denials"] != 0 for unit in units):
            raise ValueError("Unlimited FU denied work")
    elif any(unit["peak"] != 1 or unit["denials"] < 1 for unit in units):
        raise ValueError("Finite FU did not demonstrate active capacity restriction")
    return dict(
        case,
        state="passed",
        receipt=str(directory / "comparison.json"),
        output_values_checked=256,
        multiplier_witnesses=units,
        observations=report["direct"]["observations"],
    )


def is_engine_ir_rejection(diagnostic):
    """Match the retained engine's parseIRFile failure, not any failed run."""
    return bool(
        re.search(
            r"src/hwacc/llvm_interface\.cc:[0-9]+: panic: Error reading Module",
            diagnostic,
        )
        and "Program aborted at tick " in diagnostic
    )


def negative_cases(engine, receipt, output, checker):
    controls = []
    case = dict(period_ns=3, mul_limit=1, mul_cycles=16)
    directory = output / "controls/false-guest-pass"
    workspace, spec, fixtures = prepare(engine, receipt, directory, case, corrupt=True)
    archive_generated_module(workspace, spec, directory)
    record = launch(engine, workspace, spec, directory, "native")
    numerical = checker.verify_run(
        record["run_directory"],
        fixtures,
        expected_period_ns=3,
        expected_mul_limit=1,
        expected_mul_cycles=16,
    )
    save(directory / "independent-rejection.json", numerical)
    if (
        record["state"] != "passed"
        or numerical.get("structural_state") != "passed"
        or numerical.get("numerical_state") != "failed"
    ):
        raise ValueError(
            "False-green guest control did not isolate numerical rejection"
        )
    controls.append(
        dict(
            name="false_guest_pass",
            state="passed",
            expected="green guest/runner; independent numerical rejection",
            receipt=str(directory / "independent-rejection.json"),
        )
    )

    for name in ("instruction-cap", "malformed-ir"):
        directory = output / ("controls/" + name)
        workspace, spec, fixtures = prepare(engine, receipt, directory, case)
        archive_generated_module(workspace, spec, directory)
        if name == "instruction-cap":
            path = workspace / spec["benchmark"] / "config.yml"
            shutil.copy2(path, directory / "valid-config.yml")
            docs = list(yaml.safe_load_all(path.read_text()))
            docs[0]["hw_config"]["gemm"]["instructions"]["mul"][
                "functional_unit_limit"
            ] = 1
            path.write_text(yaml.safe_dump_all(docs, sort_keys=False))
        else:
            path = workspace / spec["benchmark"] / "hw/gemm.ll"
            shutil.copy2(path, directory / "valid-gemm.ll")
            path.write_text("not valid LLVM IR for the deliberate negative control\n")
        mutation = dict(path=str(path), sha256=file_hash(path), control=name)
        save(directory / "controlled-input-mutation.json", mutation)
        record = launch(engine, workspace, spec, directory, "native", required=False)
        run = Path(record["run_directory"])
        stderr = (
            (run / "stderr.txt").read_text() if (run / "stderr.txt").exists() else ""
        )
        # Runner names are recorded in run.json; keep complete diagnostic artifacts.
        texts = []
        for filename in ("stdout.txt", "stderr.txt", "simulator/system.terminal"):
            file = run / filename
            if file.exists():
                texts.append(file.read_text(errors="replace"))
        diagnostic = "\n".join(texts)
        if record["state"] != "failed":
            raise ValueError("Negative input unexpectedly ran successfully: " + name)
        if name == "instruction-cap" and "functional_unit_limit" not in diagnostic:
            raise ValueError("Instruction-cap rejection lacked source diagnostic")
        if name == "malformed-ir" and not is_engine_ir_rejection(diagnostic):
            raise ValueError("Malformed-IR rejection lacked an actual LLVM diagnostic")
        result = dict(
            name=name,
            state="passed",
            expected="preflight rejection"
            if name == "instruction-cap"
            else "actual engine IR rejection",
            run_directory=str(run),
            mutation=mutation,
        )
        save(directory / "expected-rejection.json", result)
        controls.append(result)
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument(
        "--case",
        type=int,
        nargs=3,
        action="append",
        metavar=("PERIOD_NS", "FU_LIMIT", "MUL_CYCLES"),
    )
    parser.add_argument("--skip-negatives", action="store_true")
    args = parser.parse_args()
    selected = cases(args.case)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = dict(
        kind="native_gemm_differential_plan",
        state="planned",
        cases=selected,
        launches_per_run=2,
        inputs=(11, 29),
        negatives=not args.skip_negatives,
    )
    save(out / "plan.json", plan)
    if not args.simulate:
        print(json.dumps(plan))
        return 0
    # Preserve diagnostics without creating multi-gigabyte native core dumps.
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = dict(
        kind="native_gemm_differential_study",
        state="failed",
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        engine=str(args.engine.resolve()),
        cases=[],
        negative_controls=[],
        errors=[],
        runner_sha256=file_hash(Path(__file__)),
        driver_sha256=file_hash(ROOT / "workbench/experiments/native_gemm/main.cpp"),
        scope="Fixed8x8int32GEMM; same binary/guest/IR paired builders; native retained typed ABI",
    )
    try:
        report["engine_before"] = verify_engine(args.engine, args.build_receipt)
        checker = checker_module()
        for case in selected:
            print("Running " + case["name"], flush=True)
            row = positive_case(args.engine, args.build_receipt, out, case, checker)
            report["cases"].append(row)
            save(out / "study.json", report)
        if not args.skip_negatives:
            report["negative_controls"] = negative_cases(
                args.engine, args.build_receipt, out, checker
            )
        report["engine_after"] = verify_engine(args.engine, args.build_receipt)
        report["state"] = "passed"
    except Exception as error:
        report["errors"].append(type(error).__name__ + ": " + str(error))
    report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(out / "study.json", report)
    print(
        json.dumps(
            dict(
                state=report["state"],
                completed_cases=len(report["cases"]),
                errors=report["errors"],
                receipt=str(out / "study.json"),
            )
        )
    )
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
