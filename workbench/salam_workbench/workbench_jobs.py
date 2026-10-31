"""Run reviewed reference workloads for the desktop Workbench.

Reference mode uses the fixed sources and recorded engine selected by the
workspace manifest. It deliberately does not apply the configuration editor.
The established regression/GEMM harnesses remain responsible for simulation,
numerical contracts and build provenance; this adapter checks their durable
results again before reporting success to the GUI.
"""
import argparse
import contextlib
import datetime
import io
import json
import sys
import uuid
from pathlib import Path

from .runner import file_hash

PROJECT = Path(__file__).resolve().parents[1]
REFERENCE_BENCHMARKS = ("gemm", "bfs", "nw", "fft", "stencil3d")
MODE = "fixed_reference"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def normalize_reference_benchmark(value):
    """Accept only reviewed sys_validation names, never another suite's twin."""
    if not isinstance(value, str):
        raise ValueError("Choose a reviewed reference benchmark")
    name = (
        value[len("benchmarks/sys_validation/") :]
        if value.startswith("benchmarks/sys_validation/")
        else value
    )
    if name not in REFERENCE_BENCHMARKS:
        raise ValueError("No reviewed reference workload for " + value)
    return name


def _read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular local receipt: " + str(path))
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Reference receipt exceeds 8 MiB: " + str(path))
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON receipt object: " + str(path))
    return result


def _inside(path, root, *, directory=False):
    path, root = Path(path), Path(root).resolve(strict=True)
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    cursor = path.absolute()
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError("Symlinked reference evidence is unsupported")
        if cursor == cursor.parent:
            raise ValueError("Reference evidence must stay inside its root")
        cursor = cursor.parent
    if directory and not resolved.is_dir():
        raise ValueError("Expected a run directory")
    return resolved


def _save(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class _ReferenceOutput(io.TextIOBase):
    """Keep a local log and expose bounded progress, including session paths."""

    def __init__(self, log, emit):
        self.log = log
        self.emit = emit
        self.pending = ""
        self.sessions = []

    def write(self, text):
        self.log.write(text)
        self.log.flush()
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._line(line)
        if len(self.pending) > 8192:
            self._line(self.pending[:8192])
            self.pending = ""
        return len(text)

    def _line(self, line):
        for prefix in ("Selected regression evidence: ", "Session evidence: "):
            if line.startswith(prefix):
                self.sessions.append(line[len(prefix) :].strip())
        if line.strip():
            self.emit("reference_output", message=line[-2000:])

    def flush(self):
        if not self.log.closed:
            self.log.flush()

    def finish(self):
        if self.pending:
            self._line(self.pending)
            self.pending = ""


def _execute_reference(name, engine, runs_root):
    """Keep the established harnesses and their package-root constants intact."""
    if name == "gemm":
        from .gemm import reproduce

        return reproduce(engine, runs_root, build_engine=False)
    from .regression import run_regression

    return run_regression(engine, workloads=(name,), repeats=2, runs_root=runs_root)


def _verify_engine(project, engine):
    from .builds import verify_receipt
    from .gemm import engine_source_digest

    path, unused = verify_receipt(project, engine, engine_source_digest(engine))
    return {"path": str(path), "sha256": file_hash(path)}


def _validate_results(name, result, runs_root):
    if not isinstance(result, dict) or result.get("state") != "passed":
        error = result.get("error") if isinstance(result, dict) else None
        raise ValueError(error or "Reference harness did not return a passing session")
    if name == "gemm":
        runs = result.get("baseline_runs")
        comparison = result.get("comparison")
        negative = result.get("negative_witness")
        if not isinstance(negative, dict) or not (
            negative.get("state") == "failed"
            and negative.get("intentional_failure_detected") is True
        ):
            raise ValueError("GEMM intentional-failure witness is missing or rejected")
        negative_directory = _inside(
            negative.get("directory", ""), runs_root, directory=True
        )
        from .report import load_run
        from .runner import EXPECTED_EXIT_REASON

        rejected = load_run(negative_directory)
        raw = rejected.get("raw_correctness") or {}
        record = rejected.get("record") or {}
        expected_issues = {
            "Run state is not passed: failed",
            "Raw guest correctness evidence or recorded process exit does not satisfy the runner contract",
        }
        if (
            record.get("state") != "failed"
            or record.get("return_code") != 0
            or raw.get("outcome") != "failed"
            or raw.get("passed_markers") != 0
            or not isinstance(raw.get("failed_markers"), int)
            or raw["failed_markers"] < 1
            or (rejected.get("raw_simulator_exit") or {}).get("reason")
            != EXPECTED_EXIT_REASON
            or set(rejected.get("issues", [])) != expected_issues
        ):
            raise ValueError("GEMM negative control raw evidence is missing or changed")
    else:
        workload = result.get("workloads", {}).get(name)
        if not isinstance(workload, dict) or workload.get("state") != (
            "supported_fixed_dataset"
        ):
            raise ValueError("Reference workload did not complete two reviewed runs")
        runs, comparison = workload.get("runs"), workload.get("comparison")
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("Reference mode requires two fresh positive runs")
    if (
        not isinstance(comparison, dict)
        or comparison.get("repeatability_accepted") is not True
    ):
        raise ValueError("Reference deterministic comparison was not accepted")
    from .report import load_run

    directories, checks = [], []
    for run in runs:
        if not isinstance(run, dict) or run.get("state") != "passed":
            raise ValueError("A reference run failed or is incomplete")
        directory = _inside(run.get("directory", ""), runs_root, directory=True)
        if str(directory) in directories:
            raise ValueError("Reference mode requires two distinct run directories")
        analysis = load_run(directory)
        if analysis.get("correctness_verified") is not True:
            raise ValueError(
                "Saved reference run failed raw-evidence verification: "
                + "; ".join(analysis.get("issues", []))
            )
        directories.append(str(directory))
        checks.append(
            {
                "name": "Saved run raw evidence, artifacts and input snapshots",
                "status": "passed",
                "source": str(directory / "run.json"),
            }
        )
    return directories, checks


def launch_reference(benchmark, project=PROJECT, progress=None):
    """Execute a fixed reference workload and return a durable GUI receipt.

    ``project`` must be this installed Workbench's root: older harnesses bind
    their catalog, build receipts and source snapshots to that root. Refusing
    another root prevents a seemingly portable flag from executing elsewhere.
    Invalid benchmark/project arguments raise before allocating any evidence.
    Failures after allocation return a failed receipt and preserve all outputs.
    """
    name = normalize_reference_benchmark(benchmark)
    project = Path(project).resolve(strict=True)
    if project != PROJECT.resolve(strict=True):
        raise ValueError("Reference --project must match this installed Workbench")
    manifest = _read_json(project / "workspace.json")
    from .toolchain_profile import is_modern, load_toolchain

    if is_modern(load_toolchain(project, manifest=manifest)):
        raise ValueError(
            "Fixed-reference execution is not validated for gem5 26; "
            "use the configured benchmark mode with independent output checks"
        )
    raw_engine = Path(manifest.get("engine", {}).get("path", ""))
    if not raw_engine.is_absolute() or raw_engine.is_symlink():
        raise ValueError("Reference engine must be an existing absolute local path")
    engine = raw_engine.resolve(strict=True)
    if not engine.is_dir():
        raise ValueError("Reference engine must be a directory")
    try:
        engine.relative_to(project)
    except ValueError:
        pass
    else:
        raise ValueError("Reference runtime engine must be outside the Workbench")
    evidence = project / "evidence"
    if evidence.is_symlink():
        raise ValueError("Reference evidence root must not be a symlink")
    evidence.mkdir(exist_ok=True)
    directory = evidence / (
        "workbench-reference-"
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    directory.mkdir(exist_ok=False)
    runs_root = directory / "runs"
    runs_root.mkdir()
    receipt_path = directory / "reference-session.json"
    receipt = {
        "kind": "workbench_reference_session",
        "schema_version": 1,
        "mode": MODE,
        "state": "running",
        "benchmark": "benchmarks/sys_validation/" + name,
        "engine": str(engine),
        "evidence_directory": str(directory),
        "editor_settings_applied": False,
        "scope": (
            "Reviewed fixed reference dataset with two fresh runs. Editor settings "
            "are not applied. Metrics retain their direct SALAM or whole-guest scope."
        ),
        "started_at": _now(),
        "finished_at": None,
        "run_directory": None,
        "run_directories": [],
        "source_session": None,
        "checks": [],
        "errors": [],
    }
    progress_output = sys.stdout

    def emit(stage, **values):
        receipt["stage"] = stage
        _save(receipt_path, receipt)
        if progress is not None:
            # The established harnesses print while their stdout is captured.
            # A CLI progress callback may itself print; route it to the original
            # stream so it cannot recursively enter this capture adapter.
            with contextlib.redirect_stdout(progress_output):
                progress(
                    {
                        "kind": "gui_progress",
                        "stage": stage,
                        "evidence_directory": str(directory),
                        **values,
                    }
                )

    output = None
    result = None
    try:
        emit("reference_engine_verification")
        receipt["build_receipt"] = _verify_engine(project, engine)
        emit("running_fixed_reference", benchmark=name)
        with (directory / "backend.log").open("x", encoding="utf-8") as log:
            output = _ReferenceOutput(log, emit)
            try:
                with contextlib.redirect_stdout(output):
                    result = _execute_reference(name, engine, runs_root)
            finally:
                output.finish()
        candidates = list(output.sessions)
        if isinstance(result, dict) and result.get("session_directory"):
            candidates.append(result["session_directory"])
        candidates = sorted(set(candidates))
        if len(candidates) != 1:
            raise ValueError("Reference harness did not identify one durable session")
        source_session = (
            _inside(candidates[0], evidence, directory=True) / "session.json"
        )
        saved = _read_json(source_session)
        if saved != result:
            raise ValueError("Saved reference session differs from the harness result")
        receipt["source_session"] = str(source_session)
        receipt["source_session_sha256"] = file_hash(source_session)
        emit("verifying_reference_artifacts")
        runs, checks = _validate_results(name, result, runs_root)
        receipt.update(
            state="passed",
            stage="complete",
            run_directory=runs[-1],
            run_directories=runs,
            checks=checks,
        )
        if name == "gemm":
            receipt["negative_witness"] = result["negative_witness"]
    except Exception as error:
        receipt.update(state="failed", stage="failed")
        receipt["errors"].append(type(error).__name__ + ": " + str(error))
        if output is not None:
            receipt["reported_source_sessions"] = output.sessions
    finally:
        receipt["finished_at"] = _now()
        _save(receipt_path, receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--project", type=Path, default=PROJECT)
    args = parser.parse_args(argv)
    try:
        result = launch_reference(
            args.benchmark,
            project=args.project,
            progress=lambda value: print(json.dumps(value), flush=True),
        )
    except Exception as error:
        result = {
            "state": "failed",
            "errors": [type(error).__name__ + ": " + str(error)],
        }
    print(
        json.dumps(
            {
                "kind": "gui_execution_result",
                "mode": MODE,
                "state": result["state"],
                "evidence_directory": result.get("evidence_directory"),
                "run_directory": result.get("run_directory"),
                "errors": result.get("errors", []),
                "editor_form_applied": False,
            }
        ),
        flush=True,
    )
    return 0 if result["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
