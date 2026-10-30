"""Isolated simulator wrong-output witnesses for fixed regression workloads.

Each control starts from a newly staged, pinned source copy.  The hardware
control changes one output SPM element in top.c after its child accelerator
finishes and before the DMA copy-back.  The guest control changes one returned
element immediately before the existing guest oracle.  Neither touches the
recovered engine or prior positive evidence.
"""
import argparse
import datetime
import difflib
import json
import shutil
import uuid
from pathlib import Path

from . import regression as r
from .builds import verify_receipt
from .gemm import engine_source_digest, git
from .observability import assess_run_observability
from .report import parse_stats
from .runner import EXPECTED_EXIT_REASON, file_hash, run_experiment

PROJECT = Path(__file__).resolve().parents[1]
MODES = ("hw-spm", "guest")
WORKLOADS = ("bfs", "nw", "fft", "stencil3d")

# The hardware stores target the shared output SPM after the child accelerator
# completion poll.  The following DMA copy then carries the wrong result to the
# unchanged guest.  The sentinels differ from pinned reference element zero:
# BFS=1, NW='c', FFT is far below 1e6, stencil3d=0.
MUTATIONS = {
    "bfs": {
        "hw-spm": (
            "hw/top.c",
            "\twhile ((*BFSFlags & DEV_INTR) != DEV_INTR);\n",
            "\t*((volatile edge_index_t *)LEVELCOUNTS) = (edge_index_t)0xffffffffU;\n",
        ),
        "guest": (
            "sw/main.cpp",
            '    printf("Job complete\\n");\n',
            "    level_counts[0] = check[0] + 1;\n",
        ),
    },
    "nw": {
        "hw-spm": (
            "hw/top.c",
            "\twhile ((*NWFlags & DEV_INTR) != DEV_INTR);\n",
            "\t*((volatile char *)ALIGNEDA) = (char)1;\n",
        ),
        "guest": (
            "sw/main.cpp",
            '    printf("Job complete\\n");\n',
            "    alignedA[0] = (checkA[0] == 'X') ? 'Y' : 'X';\n",
        ),
    },
    "fft": {
        "hw-spm": (
            "hw/top.c",
            "\twhile ((*FFTFlags & DEV_INTR) != DEV_INTR);\n",
            "\t*((volatile double *)REAL) = 1000000.0;\n",
        ),
        "guest": (
            "sw/main.cpp",
            '    printf("Job complete\\n");\n',
            "    real[0] = real_check[0] + 1.0;\n",
        ),
    },
    "stencil3d": {
        "hw-spm": (
            "hw/top.c",
            "\twhile ((*STENCILFlags & DEV_INTR) != DEV_INTR);\n",
            "\t*((volatile TYPE *)SOL) = (TYPE)-1;\n",
        ),
        "guest": (
            "sw/main.cpp",
            '    printf("Job complete\\n");\n',
            "    sts.sol[0] = sts.check[0] + 1;\n",
        ),
    },
}


def _save(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def apply_mutation(workspace, entry, mode):
    """Patch exactly one staged source file; fail if the reviewed anchor moved."""
    if entry["name"] not in MUTATIONS or mode not in MODES:
        raise ValueError("Unsupported negative control")
    relative, anchor, injection = MUTATIONS[entry["name"]][mode]
    path = Path(workspace) / entry["relative_path"] / relative
    original = path.read_text(encoding="utf-8")
    if original.count(anchor) != 1 or injection in original:
        raise ValueError(
            "Negative control anchor is absent, duplicated or already injected"
        )
    changed = original.replace(anchor, anchor + injection, 1)
    before_sha256 = file_hash(path)
    path.write_text(changed, encoding="utf-8")
    after_sha256 = file_hash(path)
    return {
        "kind": "intentional_single_result_corruption",
        "mode": mode,
        "workload": entry["name"],
        "path": str(path),
        "relative_path": (Path(entry["relative_path"]) / relative).as_posix(),
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "anchor": anchor,
        "injection": injection,
        "unified_diff": "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                changed.splitlines(keepends=True),
                fromfile="prepared/" + relative,
                tofile="negative/" + relative,
            )
        ),
    }


def assess_negative_run(record, run_dir):
    """An ordinary failed run is insufficient: require the raw wrong-output path."""
    terminal = (Path(run_dir) / "simulator/system.terminal").read_text(
        encoding="utf-8", errors="replace"
    )
    lines = [line.strip() for line in terminal.splitlines()]
    markers = [line for line in lines if line in ("Check Passed", "Check Failed")]
    completed_before_failure = (
        "Job complete" in lines
        and "Check Failed" in lines
        and lines.index("Job complete") < lines.index("Check Failed")
    )
    correctness = record.get("correctness") or {}
    required = record.get("required_artifact_checks") or []
    observability = record.get("observability") or {}
    passed = (
        record.get("state") == "failed"
        and record.get("return_code") == 0
        and markers.count("Check Passed") == 0
        and markers.count("Check Failed") >= 1
        and completed_before_failure
        and correctness.get("outcome") == "failed"
        and correctness.get("passed_markers") == 0
        and correctness.get("failed_markers") == markers.count("Check Failed")
        and (record.get("simulator_exit") or {}).get("reason") == EXPECTED_EXIT_REASON
        and len(record.get("simulator_exit_events") or []) == 1
        and required
        and all(item.get("available") is True for item in required)
        and record.get("executable", {}).get("unchanged_after_run") is True
        and all(
            item.get("unchanged_after_run")
            and item.get("snapshot", {}).get("unchanged_after_run")
            for item in record.get("inputs", [])
        )
        and observability.get("status") == "valid"
        and observability.get("valid") is True
        and not observability.get("issues")
    )
    return {
        "intentional_failure_detected": bool(passed),
        "raw_markers": markers,
        "job_complete_before_failure": completed_before_failure,
        "runner_state": record.get("state"),
        "process_return_code": record.get("return_code"),
        "simulator_exit": record.get("simulator_exit"),
        "required_artifact_count": len(required),
        "observability_status": observability.get("status"),
        "guest_output_sha256": file_hash(Path(run_dir) / "simulator/system.terminal"),
    }


def _run_one(engine, entry, mode, source, directory, runs_root):
    preparation = r.prepare_workload(engine, entry, directory / "preparation")
    workspace = Path(preparation["staging"]["workspace"])
    patch = apply_mutation(workspace, entry, mode)
    _save(directory / "patch.json", patch)
    rel = Path(entry["relative_path"])
    env = r._environment(workspace)
    if mode == "hw-spm":
        command = ["make", "-B", "-C", str(rel / "hw"), "build"]
        r._command(
            command,
            workspace,
            directory,
            "negative-build-ir",
            env,
            entry["build_timeout_seconds"],
        )
        ir = r.inspect_ir_targets(workspace, entry)
    else:
        command = ["make", "-B", "-C", str(rel / "sw"), "main.elf"]
        r._command(
            command,
            workspace,
            directory,
            "negative-build-guest",
            env,
            entry["build_timeout_seconds"],
        )
        ir = preparation["ir_target_validation"]
    inputs = [
        {"path": str(path), "sha256": file_hash(path)}
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
        and (
            path.name == "Makefile"
            or path.suffix in r.SOURCE_SUFFIXES | {".ll", ".elf"}
        )
    ]
    negative_prep = {
        "kind": "staged_negative_preparation",
        "workload": entry["name"],
        "mode": mode,
        "positive_preparation": str(directory / "preparation/preparation.json"),
        "positive_preparation_sha256": file_hash(
            directory / "preparation/preparation.json"
        ),
        "patch": patch,
        "ir_target_validation": ir,
        "inputs": inputs,
        "engine_sources_unchanged": all(
            file_hash(item["source"]) == item["sha256"]
            for item in preparation["staging"]["source_files"]
        ),
    }
    if not negative_prep["engine_sources_unchanged"]:
        raise ValueError(
            "Original engine source changed while preparing a negative control"
        )
    _save(directory / "negative-preparation.json", negative_prep)
    spec = r.experiment_spec(entry, source)
    spec["experiment_id"] = entry["name"] + "-" + mode + "-intentional-wrong-output-v1"
    spec["negative_witness"] = {
        "kind": mode,
        "patch_sha256": file_hash(directory / "patch.json"),
        "changed_source": patch["relative_path"],
        "before_sha256": patch["before_sha256"],
        "after_sha256": patch["after_sha256"],
        "expected_guest_marker": "Check Failed",
        "expected_runner_state": "failed",
        "expected_process_exit": 0,
        "expected_simulator_exit": EXPECTED_EXIT_REASON,
    }
    spec["timeout_seconds"] = min(entry["timeout_seconds"], 180)
    required = [
        "simulator/system.terminal",
        "simulator/config.ini",
        "simulator/config.json",
        "simulator/stats.txt",
    ]
    for accelerator in spec.get("observability", {}).get("expected_invocations", {}):
        required.append("simulator/observability/" + accelerator + ".invocation-1.json")
    for item in inputs:
        if file_hash(item["path"]) != item["sha256"]:
            raise ValueError("Negative input changed before simulator invocation")
    record = run_experiment(
        [str(engine / "build/ARM/gem5.opt")],
        r.simulator_args(engine, workspace, entry),
        cwd=workspace,
        runs_root=runs_root,
        experiment=spec,
        input_paths=[Path(item["path"]) for item in inputs]
        + [
            directory / "patch.json",
            directory / "negative-preparation.json",
            engine / "baremetal/common/fake.iso",
        ],
        env_overrides={"M5_PATH": str(workspace), "PATH": env["PATH"]},
        timeout_seconds=spec["timeout_seconds"],
        required_artifacts=required,
        snapshot_inputs=True,
    )
    run_dir = Path(record["run_directory"])
    record["metrics"] = parse_stats(run_dir / "simulator/stats.txt")
    record["observability"] = assess_run_observability(run_dir, record, spec)
    r._save(run_dir / "run.json", record)
    assessment = assess_negative_run(record, run_dir)
    _save(
        directory / "witness.json",
        {
            "schema_version": 1,
            "workload": entry["name"],
            "mode": mode,
            "run_directory": str(run_dir),
            "run_receipt_sha256": file_hash(run_dir / "run.json"),
            "experiment_spec_sha256": file_hash(run_dir / "experiment.json"),
            "patch_sha256": file_hash(directory / "patch.json"),
            **assessment,
        },
    )
    return {
        "state": "witnessed"
        if assessment["intentional_failure_detected"]
        else "not_witnessed",
        "directory": str(directory),
        "run_directory": str(run_dir),
        "witness": str(directory / "witness.json"),
    }


def run_controls(engine, positive_session, workloads, modes=MODES, evidence_root=None):
    engine = Path(engine).resolve(strict=True)
    positive_session = Path(positive_session).resolve(strict=True)
    if (
        tuple(workloads) == ()
        or len(set(workloads)) != len(workloads)
        or any(name not in WORKLOADS for name in workloads)
    ):
        raise ValueError("Choose distinct supported workloads")
    if (
        tuple(modes) == ()
        or len(set(modes)) != len(modes)
        or any(mode not in MODES for mode in modes)
    ):
        raise ValueError("Choose distinct supported control modes")
    positive = json.loads((positive_session / "session.json").read_text())
    source = json.loads((positive_session / "source.json").read_text())
    if (
        positive.get("state") != "passed"
        or positive.get("repeats") != 2
        or any(
            positive["workloads"].get(name, {}).get("state")
            != "supported_fixed_dataset"
            for name in workloads
        )
    ):
        raise ValueError(
            "A two-run accepted positive session is required for each workload"
        )
    current_digest = engine_source_digest(engine)
    if (
        current_digest != source["engine_source_sha256"]
        or git(engine, "rev-parse", "HEAD").decode().strip() != source["revision"]
    ):
        raise ValueError(
            "Recovered engine no longer matches the accepted positive session"
        )
    verify_receipt(PROJECT, engine, current_digest)
    catalog = r.load_catalog()
    evidence_root = Path(evidence_root or PROJECT / "evidence").resolve()
    session = evidence_root / (
        "regression-negative-"
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    session.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, session / "regression_negative.py")
    shutil.copyfile(r.CATALOG, session / "catalog.json")
    summary = {
        "schema_version": 1,
        "kind": "regression_negative_controls",
        "state": "running",
        "started_at": r._now(),
        "positive_session": str(positive_session),
        "positive_session_source_sha256": file_hash(positive_session / "source.json"),
        "engine_revision": source["revision"],
        "engine_source_sha256": current_digest,
        "harness_sha256": file_hash(session / "regression_negative.py"),
        "catalog_sha256": file_hash(session / "catalog.json"),
        "workloads": list(workloads),
        "modes": list(modes),
        "controls": {},
    }
    _save(session / "session.json", summary)
    try:
        for name in workloads:
            for mode in modes:
                key = name + "/" + mode
                directory = session / name / mode
                directory.mkdir(parents=True, exist_ok=False)
                try:
                    summary["controls"][key] = _run_one(
                        engine,
                        catalog["workloads"][name],
                        mode,
                        source,
                        directory,
                        session / "runs",
                    )
                except Exception as error:
                    summary["controls"][key] = {
                        "state": "failed",
                        "directory": str(directory),
                        "error": type(error).__name__ + ": " + str(error),
                    }
                _save(session / "session.json", summary)
                print(key + ": " + summary["controls"][key]["state"], flush=True)
        summary["engine_source_unchanged_after"] = (
            engine_source_digest(engine) == current_digest
        )
        summary["state"] = (
            "passed"
            if (
                summary["engine_source_unchanged_after"]
                and all(
                    item["state"] == "witnessed"
                    for item in summary["controls"].values()
                )
            )
            else "failed"
        )
    finally:
        summary["finished_at"] = r._now()
        _save(session / "session.json", summary)
        print("Negative-control evidence: " + str(session), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--positive-session", required=True, type=Path)
    parser.add_argument("--workloads", nargs="+", choices=WORKLOADS, required=True)
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    result = run_controls(
        args.engine,
        args.positive_session,
        args.workloads,
        args.modes,
        args.evidence_root,
    )
    return 0 if result["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
