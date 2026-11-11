# SPDX-License-Identifier: BSD-3-Clause
"""Run an explicit saved request through the checked Workbench pipeline."""
import argparse
import json
from pathlib import Path

from .gui_execution import apply_request, read_request
from .timeline_export import eligible_traces, export_selected_trace
from .workbench_results import load_run

PROJECT = Path(__file__).resolve().parents[1]


def run_saved_request(request_path, *, benchmark, evidence_dir=None, jobs=8):
    source = Path(request_path).resolve(strict=True)
    if not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Expected a request file no larger than 2 MiB")
    request = read_request(source.read_text(encoding="utf-8-sig"))
    if request.get("benchmark") != "benchmarks/sys_validation/" + benchmark:
        raise ValueError("Saved request is not for the selected benchmark")
    if not isinstance(request.get("benchmark_input"), dict):
        raise ValueError(
            "Select generated inputs with complete independent output checks"
        )
    result = apply_request(
        request,
        evidence_dir=evidence_dir,
        jobs=jobs,
        progress=lambda item: print(json.dumps(item), flush=True),
    )
    summary = {
        "kind": "configured_run_with_timelines",
        "state": result["state"],
        "simulation": result,
        "timelines": [],
    }
    if result["state"] != "passed":
        return summary
    receipt = Path(result["evidence_directory"]) / "gui-execution.json"
    inspected = load_run(receipt, PROJECT)
    summary["current_evidence_assessment"] = inspected.get("validation_state")
    if (
        inspected.get("validation_state") != "checked_recorded_evidence"
        or inspected.get("independent_oracle", {}).get("state") != "passed"
    ):
        summary.update(
            state="failed",
            errors=[
                "Current result-reader evidence or independent numerical check did not pass"
            ],
        )
        return summary
    choices = eligible_traces(inspected)
    if not choices:
        raise ValueError("Simulation passed but no hash-verified FU trace is available")
    for item in choices:
        summary["timelines"].append(
            export_selected_trace(inspected, item["path"], PROJECT)
        )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument(
        "--benchmark", choices=("gemm", "fft", "stencil3d", "vadd"), default="gemm"
    )
    parser.add_argument("--evidence-dir")
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 32:
        parser.error("--jobs must be between 1 and 32")
    try:
        result = run_saved_request(
            args.request,
            benchmark=args.benchmark,
            evidence_dir=args.evidence_dir,
            jobs=args.jobs,
        )
    except Exception as error:
        result = {
            "state": "failed",
            "errors": [type(error).__name__ + ": " + str(error)],
        }
    print(json.dumps(result), flush=True)
    return 0 if result["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
