"""Reproduce the supported GEMM baseline inside the recorded Linux environment."""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from .builds import select_receipt, verify_receipt, write_receipt_new
from .config import validate_gemm_config
from .facade import validate_and_generate
from .provenance import assert_tooling_unchanged, snapshot_tooling
from .report import parse_stats, write_report
from .runner import ENV_ALLOWLIST, file_hash, run_experiment

BASELINE = "42539ecca54ff0fed455a7afe0bda0603554e360"
REL = Path("benchmarks/sys_validation/gemm")
GENERATED = [
    "configs/SALAM/generated/gemm.py",
    "configs/SALAM/generated/fs_gemm.py",
    str(REL / "gemm_clstr_hw_defines.h"),
]
INPUTS = (
    [
        str(REL / p)
        for p in [
            "config.yml",
            "defines.h",
            "sw/main.cpp",
            "sw/bench.h",
            "sw/isr.c",
            "sw/boot.s",
            "sw/boot.ld",
            "sw/Makefile",
            "hw/gemm.c",
            "hw/top.c",
            "hw/hw_defines.h",
            "hw/Makefile",
            "hw/gemm.ll",
            "hw/top.ll",
        ]
    ]
    + GENERATED
    + [
        "benchmarks/common/Makefile",
        "benchmarks/common/syscalls.c",
        "benchmarks/common/m5ops.h",
        "baremetal/common/fake.iso",
    ]
)
REQUIRED = [
    "simulator/system.terminal",
    "simulator/config.ini",
    "simulator/config.json",
    "simulator/stats.txt",
]
PROJECT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def git(engine, *args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
        cwd=str(engine),
    )


def environment(engine):
    result = {key: os.environ[key] for key in ENV_ALLOWLIST if key in os.environ}
    result["M5_PATH"] = str(engine)
    result["PATH"] = "/usr/lib/llvm-12/bin:" + result.get("PATH", "")
    return result


def command(argv, engine, out, name, env, timeout=600):
    log = out / (name + ".log")
    record = {
        "argv": [str(a) for a in argv],
        "cwd": str(engine),
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "log": log.name,
        "state": "running",
        "environment": {
            key: env[key] for key in ("PATH", "M5_PATH", "LANG") if key in env
        },
        "toolchain_sha256": file_hash(PROJECT / "evidence/toolchain.json"),
    }
    save(out / (name + ".json"), record)
    with log.open("wb") as handle:
        try:
            p = subprocess.run(
                record["argv"],
                cwd=str(engine),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            record.update(
                return_code=p.returncode,
                state="completed" if p.returncode == 0 else "failed",
            )
        except subprocess.TimeoutExpired:
            record.update(return_code=None, state="timed_out")
    record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(out / (name + ".json"), record)
    if record["state"] != "completed":
        raise RuntimeError("Command failed; inspect " + str(log))
    return log


def prepare(engine, out):
    out.mkdir(exist_ok=False)
    env = environment(engine)
    validation = validate_gemm_config(
        engine / REL / "config.yml", engine, require_ir=False
    )
    save(out / "config-prebuild.json", validation)
    facade_result = validate_and_generate(engine, out / "facade")
    if not facade_result["valid"]:
        raise RuntimeError(
            "Configuration facade rejected generation: " + str(facade_result["errors"])
        )
    generated = {p: file_hash(engine / p) for p in GENERATED}
    command(
        ["make", "-B", "-C", str(REL / "hw"), "build"],
        engine,
        out,
        "build-ir",
        env,
    )
    command(
        ["make", "-B", "-C", str(REL / "sw"), "main.elf"],
        engine,
        out,
        "build-guest",
        env,
    )
    macro_log = command(
        [
            "/usr/bin/arm-none-eabi-g++",
            "-dM",
            "-E",
            "-I",
            str(REL / "sw"),
            str(REL / "sw/main.cpp"),
        ],
        engine,
        out,
        "checker-macros",
        env,
    )
    macro_lines = set(macro_log.read_text().splitlines())
    for required in [
        "#define CHECK ",
        "#define ROW 8",
        "#define COL 8",
        "#define TYPE int",
    ]:
        if required.rstrip() not in {line.rstrip() for line in macro_lines}:
            raise RuntimeError("Guest contract macro missing or changed: " + required)
    save(
        out / "config-postbuild.json",
        validate_gemm_config(engine / REL / "config.yml", engine),
    )
    if generated != {p: file_hash(engine / p) for p in GENERATED}:
        raise RuntimeError("Build changed generated configuration unexpectedly")
    save(out / "generated-inputs.json", generated)
    save(
        out / "built-artifacts.json",
        [
            {
                "path": p,
                "sha256": file_hash(engine / p),
                "bytes": (engine / p).stat().st_size,
            }
            for p in [
                "build/ARM/gem5.opt",
                str(REL / "sw/main.elf"),
                str(REL / "hw/gemm.ll"),
                str(REL / "hw/top.ll"),
                "baremetal/common/fake.iso",
            ]
        ],
    )
    return generated


def engine_source_digest(engine):
    # Stage new source files before hashing: git diff must cover their bytes.
    untracked = (
        git(
            engine,
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "src",
            "ext",
            "configs",
            "util",
            "build_opts",
            "SConstruct",
            "SConscript",
        )
        .decode()
        .splitlines()
    )
    if untracked:
        raise ValueError(
            "Stage new engine source before binding a build: " + ", ".join(untracked)
        )
    # Guest workloads are separately rebuilt and hashed; they do not build the simulator.
    return hashlib.sha256(
        git(
            engine,
            "diff",
            "--binary",
            BASELINE,
            "--",
            ".",
            ":(exclude)benchmarks",
        )
    ).hexdigest()


def bind_engine(engine, build_record, receipt_path, *, features=()):
    build = json.loads(build_record.read_text())
    code = build.get("return_code", build.get("returncode"))
    if build["state"] not in {"completed", "passed"} or code != 0:
        raise ValueError("Simulator build record does not establish a completed build")
    binary = engine / "build/ARM/gem5.opt"
    log = build_record.parent / build["log"]
    receipt = {
        "schema_version": 1,
        "state": "completed",
        "binary_path": str(binary),
        "binary_sha256": file_hash(binary),
        "build_record": str(build_record),
        "build_record_sha256": file_hash(build_record),
        "build_log_sha256": file_hash(log),
        "engine_source_sha256": engine_source_digest(engine),
        "recovered_baseline": BASELINE,
        "toolchain_sha256": file_hash(PROJECT / "evidence/toolchain.json"),
        "features": list(features),
    }
    write_receipt_new(receipt_path, receipt)
    return receipt


def spec(engine, source, mismatch=False):
    data = json.loads(
        (PROJECT / "experiments/gemm/baseline.json").read_text(encoding="utf-8-sig")
    )
    data["source"] = source
    data["environment"] = {
        "id": "ubuntu20-llvm12-python38-armgcc9",
        "toolchain_sha256": file_hash(PROJECT / "evidence/toolchain.json"),
    }
    if "salam_observability_v1" in source.get("engine_features", []):
        data["observability"] = {
            "kind": "salam_observability",
            "schema_version": 1,
            "feature": "salam_observability_v1",
            "expected_invocations": {
                "system.gemm_clstr.gemm": [1],
                "system.gemm_clstr.top": [1],
            },
            "oracles": {
                "system.gemm_clstr.gemm": {
                    "memory.reads.completed": 1024,
                    "memory.reads.completed_bytes": 4096,
                    "memory.writes.completed": 64,
                    "memory.writes.completed_bytes": 256,
                }
            },
        }
    if mismatch:
        data["experiment_id"] = "gemm-int8x8-intentional-mismatch-v1"
        data["negative_witness"] = {
            "compile_flag": "-DWORKBENCH_INJECT_MISMATCH",
            "effect": "After CPU reference calculation, XOR accelerator output element zero with 1",
            "expected_runner_state": "failed",
        }
    return data


def execute(engine, runs, experiment, kernel):
    args = [
        "configs/SALAM/generated/fs_gemm.py",
        "--mem-size=4GB",
        "--mem-type=DDR4_2400_8x8",
        "--kernel=" + kernel,
        "--disk-image=baremetal/common/fake.iso",
        "--machine-type=VExpress_GEM5_V1",
        "--dtb-file=none",
        "--bare-metal",
        "--cpu-type=DerivO3CPU",
        "--accpath=benchmarks/sys_validation",
        "--accbench=gemm",
        "--caches",
        "--l2cache",
    ]
    required = list(REQUIRED)
    for accelerator, invocations in (
        experiment.get("observability", {}).get("expected_invocations", {}).items()
    ):
        for invocation in invocations:
            required.append(
                "simulator/observability/%s.invocation-%d.json"
                % (accelerator, invocation)
            )
    record = run_experiment(
        [str(engine / "build/ARM/gem5.opt")],
        args,
        cwd=engine,
        runs_root=runs,
        experiment=experiment,
        input_paths=[engine / p for p in INPUTS + [kernel]],
        env_overrides={
            "M5_PATH": str(engine),
            "PATH": environment(engine)["PATH"],
        },
        timeout_seconds=experiment["timeout_seconds"],
        required_artifacts=required,
        snapshot_inputs=True,
    )
    metrics = parse_stats(Path(record["run_directory"]) / "simulator/stats.txt")
    record["metrics"] = metrics
    record["metrics_scope"] = experiment["metrics"]["scope"]
    core = ["simTicks", "simSeconds", "simInsts", "hostSeconds"]
    complete_metrics = not metrics["issues"] and all(
        metrics["metrics"].get(name, {}).get("status") == "present" for name in core
    )
    if record["state"] == "passed" and not complete_metrics:
        record["state"] = "incomplete"
        record["errors"].append("Required whole-run statistics are missing or invalid")
    from .observability import assess_run_observability

    record["observability"] = assess_run_observability(
        record["run_directory"], record, experiment
    )
    if record["state"] == "passed" and record["observability"]["status"] == "invalid":
        record["state"] = "incomplete"
        record["errors"].extend(
            "Observability: " + issue for issue in record["observability"]["issues"]
        )
    save(Path(record["run_directory"]) / "run.json", record)
    return record


def build_mismatch(engine, out):
    out.mkdir(exist_ok=False)
    env = environment(engine)
    sw = engine / REL / "sw"
    command(
        [
            "/usr/bin/arm-none-eabi-g++",
            "-g",
            "-O3",
            "-fcommon",
            "-lunistd",
            "-I",
            ".",
            "-fno-exceptions",
            "-DWORKBENCH_INJECT_MISMATCH",
            "-c",
            "main.cpp",
            "-o",
            "main-workbench-mismatch.o",
        ],
        sw,
        out,
        "compile-mismatch",
        env,
    )
    command(
        [
            "/usr/bin/arm-none-eabi-gcc",
            "-nostartfiles",
            "-Xlinker",
            "-Tboot.ld",
            "-o",
            "main-workbench-mismatch.elf",
            "boot.o",
            "../../../common/syscalls.o",
            "main-workbench-mismatch.o",
            "isr.o",
            "-nostartfiles",
        ],
        sw,
        out,
        "link-mismatch",
        env,
    )
    return str(REL / "sw/main-workbench-mismatch.elf")


def reproduce(engine, runs_root, build_engine=False, jobs=8):
    engine, runs_root = engine.resolve(strict=True), runs_root.resolve()
    identifier = (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    session = PROJECT / "evidence" / ("gemm-" + identifier)
    session.mkdir(exist_ok=False)
    summary = {
        "schema_version": 1,
        "state": "running",
        "session_directory": str(session),
        "baseline_runs": [],
        "negative_witness": None,
    }
    save(session / "session.json", summary)
    try:
        tooling_hashes = snapshot_tooling(PROJECT, session / "tooling-snapshot")
        revision = git(engine, "rev-parse", "HEAD").decode().strip()
        git(engine, "merge-base", "--is-ancestor", BASELINE, "HEAD")
        patch = git(engine, "diff", "--binary", BASELINE)
        (session / "engine.patch").write_bytes(patch)
        source = {
            "recovered_baseline": BASELINE,
            "revision": revision,
            "tree": git(engine, "rev-parse", "HEAD^{tree}").decode().strip(),
            "patch_sha256": hashlib.sha256(patch).hexdigest(),
        }
        save(
            session / "source.json",
            dict(
                source,
                worktree_status=git(engine, "status", "--porcelain").decode(),
            ),
        )
        if build_engine:
            command(
                [
                    "/usr/bin/python3.8",
                    "/usr/bin/scons",
                    "build/ARM/gem5.opt",
                    "-j" + str(jobs),
                    "CXX=/usr/bin/g++",
                    "PYTHON_CONFIG=/usr/bin/python3.8-config",
                    "USE_KVM=0",
                    "PROTOCOL=CHI",
                ],
                engine,
                session,
                "engine-build",
                environment(engine),
                timeout=7200,
            )
            receipt_path = session / "engine-artifact.json"
            planned_features = (
                json.loads((PROJECT / "workspace.json").read_text())
                .get("engine", {})
                .get("build_features", [])
            )
            receipt = bind_engine(
                engine,
                session / "engine-build.json",
                receipt_path,
                features=planned_features,
            )
            select_receipt(PROJECT, receipt_path)
        else:
            receipt_path, receipt = verify_receipt(
                PROJECT, engine, engine_source_digest(engine)
            )
        source["engine_build_receipt_sha256"] = file_hash(receipt_path)
        source["engine_features"] = receipt.get("features", [])
        assert_tooling_unchanged(PROJECT, tooling_hashes)
        source["tooling_sha256"] = tooling_hashes
        source["tooling_snapshot_directory"] = str(session / "tooling-snapshot")
        save(
            session / "source.json",
            dict(
                source,
                worktree_status=git(engine, "status", "--porcelain").decode(),
            ),
        )
        save(session / "engine-build-receipt.json", receipt)
        generated = None
        for label in ["baseline-a", "baseline-b"]:
            latest = prepare(engine, session / label)
            if generated is not None and generated != latest:
                raise RuntimeError(
                    "Regeneration was not deterministic in this checkout"
                )
            generated = latest
            if git(engine, "diff", "--binary", BASELINE) != patch:
                raise RuntimeError("Tracked engine source changed during preparation")
            assert_tooling_unchanged(PROJECT, tooling_hashes)
            record = execute(
                engine,
                runs_root,
                spec(engine, source),
                str(REL / "sw/main.elf"),
            )
            summary["baseline_runs"].append(
                {
                    "state": record["state"],
                    "directory": record["run_directory"],
                }
            )
            save(session / "session.json", summary)
            print(
                label + ": " + record["state"] + " " + record["run_directory"],
                flush=True,
            )
            if record["state"] != "passed":
                raise RuntimeError(
                    label + " did not pass; inspect its preserved run.json"
                )
        comparison = write_report(
            summary["baseline_runs"][0]["directory"],
            summary["baseline_runs"][1]["directory"],
            session / "report",
        )
        summary["comparison"] = comparison
        mismatch = build_mismatch(engine, session / "negative-build")
        record = execute(
            engine, runs_root, spec(engine, source, mismatch=True), mismatch
        )
        witnessed = (
            record["state"] == "failed"
            and record["return_code"] == 0
            and record.get("correctness", {}).get("outcome") == "failed"
            and record["correctness"]["passed_markers"] == 0
            and record["correctness"]["failed_markers"] >= 1
            and (record.get("simulator_exit") or {}).get("reason")
            == "m5_exit instruction encountered"
            and all(item["available"] for item in record["required_artifact_checks"])
            and record["executable"].get("unchanged_after_run") is True
            and record.get("observability", {}).get("status")
            in ("valid", "unavailable")
            and all(
                item.get("unchanged_after_run")
                and item.get("snapshot", {}).get("unchanged_after_run")
                for item in record["inputs"]
            )
        )
        summary["negative_witness"] = {
            "state": record["state"],
            "directory": record["run_directory"],
            "intentional_failure_detected": witnessed,
        }
        assert_tooling_unchanged(PROJECT, tooling_hashes)
        # Report owns exact repeatability classification; keep it explicit, never infer from process status.
        summary["state"] = (
            "passed" if witnessed and comparison["repeatability_accepted"] else "failed"
        )
        if not comparison["repeatability_accepted"]:
            raise RuntimeError(
                "Baseline comparison did not meet declared repeatability criteria"
            )
        if not witnessed:
            raise RuntimeError(
                "Intentional guest mismatch did not produce the expected failure evidence"
            )
    except Exception as error:
        summary["state"] = "failed"
        summary["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        summary["finished_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        save(session / "session.json", summary)
        print("Session evidence: " + str(session), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["reproduce"])
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=PROJECT / "runs")
    parser.add_argument("--build-engine", action="store_true")
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error("--jobs must be between 1 and 32")
    reproduce(args.engine, args.runs_root, args.build_engine, args.jobs)


if __name__ == "__main__":
    main()
