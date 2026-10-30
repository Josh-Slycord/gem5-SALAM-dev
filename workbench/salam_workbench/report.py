"""Read-only analysis of recorded gem5 runs; no simulator execution."""
import argparse
import html
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

from .runner import (
    EXPECTED_EXIT_REASON,
    _read_correctness,
    _read_exit_events,
    _safe_relative_path,
    _safe_run_file,
    file_hash,
)

CORE_METRICS = ("simTicks", "simSeconds", "simInsts", "hostSeconds")
DETERMINISTIC_METRICS = ("simTicks", "simSeconds", "simInsts")
MEASUREMENT_SCOPE = (
    "Full-run measurement window: input generation, accelerator waiting, and CPU "
    "reference validation are included, along with execution through the final "
    "statistics dump. These figures do not isolate accelerator execution and "
    "do not establish an accelerator-only speedup."
)
BEGIN = re.compile(r"^-+\s*Begin Simulation Statistics\s*-+$")
END = re.compile(r"^-+\s*End Simulation Statistics\s*-+$")


def _metric(token, description, line):
    result = {
        "value": token,
        "description": description,
        "line": line,
        "status": "present",
    }
    try:
        if not Decimal(token).is_finite():
            result["status"] = "nonfinite"
    except InvalidOperation:
        result["status"] = "invalid"
    return result


def _empty_stats(path):
    return {
        "path": str(path),
        "present": False,
        "block_count": 0,
        "complete_block_count": 0,
        "incomplete_block_count": 0,
        "selection": "final_complete_block",
        "selected_block": None,
        "metrics": {},
        "missing_core_metrics": list(CORE_METRICS),
        "nonfinite_metrics": [],
        "invalid_metrics": [],
        "warnings": [],
        "issues": [],
    }


def parse_stats(path):
    """Select the final explicitly closed block, never an unfinished tail.

    Numeric tokens remain strings so comparison does not round large integer
    counters through a float. Distribution percentages are not scalar values.
    """
    path = Path(path)
    result = _empty_stats(path)
    result["present"] = path.is_file()
    if not path.is_file():
        result["issues"].append("Statistics file is missing")
        return result
    current = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, 1):
            line = raw.strip()
            if BEGIN.match(line):
                if current is not None:
                    result["incomplete_block_count"] += 1
                    result["issues"].append(
                        "A new statistics block began before its predecessor ended"
                    )
                result["block_count"] += 1
                current = {
                    "index": result["block_count"],
                    "start_line": number,
                    "metrics": {},
                }
            elif END.match(line):
                if current is None:
                    result["issues"].append(
                        "Statistics end marker without a matching begin marker"
                    )
                else:
                    result["complete_block_count"] += 1
                    result["selected_block"] = {
                        "index": current["index"],
                        "start_line": current["start_line"],
                        "end_line": number,
                    }
                    result["metrics"] = current["metrics"]
                    current = None
            elif current is not None and line and not line.startswith("#"):
                body, _, description = line.partition("#")
                fields = body.split()
                if len(fields) < 2:
                    result["issues"].append("Malformed statistics line " + str(number))
                    continue
                name, token = fields[:2]
                if name in current["metrics"]:
                    current["metrics"][name]["status"] = "duplicate"
                    result["warnings"].append(
                        "Duplicate metric in block "
                        + str(current["index"])
                        + ": "
                        + name
                    )
                else:
                    current["metrics"][name] = _metric(
                        token, description.strip(), number
                    )
    if current is not None:
        result["incomplete_block_count"] += 1
        result["issues"].append("Unfinished statistics block at end of file")
    if result["selected_block"] is None:
        result["issues"].append("No complete statistics block")
    result["missing_core_metrics"] = [
        name for name in CORE_METRICS if name not in result["metrics"]
    ]
    result["nonfinite_metrics"] = [
        name
        for name, value in result["metrics"].items()
        if value["status"] == "nonfinite"
    ]
    result["invalid_metrics"] = [
        name
        for name, value in result["metrics"].items()
        if value["status"] in ("invalid", "duplicate")
    ]
    return result


def _accelerator_metric(name):
    # These are actual object names in the recovered GEMM configuration, not
    # invented aliases for unrelated system-wide or power-state counters.
    return (
        "hwacc" in name.lower()
        or name.startswith(
            (
                "system.gemm_clstr.gemm.",
                "system.gemm_clstr.top.",
                "system.gemm_clstr.dma.",
            )
        )
    ) and ".power_state." not in name


def _load_json(path, issues):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value
    except (OSError, ValueError) as error:
        issues.append(str(path.name) + ": " + type(error).__name__)
        return {}


def load_run(directory):
    """Reload evidence from disk and verify the runner's recorded hashes."""
    directory = Path(directory).resolve()
    issues = []
    record = (
        _load_json(directory / "run.json", issues)
        if _safe_run_file(directory, "run.json")
        else {}
    )
    experiment = (
        _load_json(directory / "experiment.json", issues)
        if _safe_run_file(directory, "experiment.json")
        else {}
    )
    stats_path = directory / "simulator" / "stats.txt"
    if _safe_run_file(directory, "simulator/stats.txt"):
        stats = parse_stats(stats_path)
    else:
        stats = _empty_stats(stats_path)
        stats["issues"].append("Statistics file is missing or unsafe")
    if record.get("state") != "passed":
        issues.append("Run state is not passed: " + str(record.get("state", "missing")))
    raw_correctness = None
    raw_exits = []
    if _safe_run_file(directory, "simulator/system.terminal"):
        raw_correctness = _read_correctness(directory / "simulator/system.terminal")
    if _safe_run_file(directory, "stdout.txt"):
        raw_exits = _read_exit_events(directory / "stdout.txt")
    raw_exit = raw_exits[-1] if raw_exits else None
    if (
        not raw_correctness
        or raw_correctness["outcome"] != "passed"
        or record.get("return_code") != 0
    ):
        issues.append(
            "Raw guest correctness evidence or recorded process exit does not satisfy the runner contract"
        )
    if not raw_exit or raw_exit["reason"] != EXPECTED_EXIT_REASON:
        issues.append("Final raw simulator exit is missing or unexpected")
    if record.get("correctness") != raw_correctness:
        issues.append("Recorded correctness summary differs from raw guest output")
    if (
        record.get("simulator_exit") != raw_exit
        or record.get("simulator_exit_events") != raw_exits
    ):
        issues.append("Recorded simulator exit summary differs from raw stdout")
    expected_spec = record.get("experiment_spec_sha256")
    spec_path = directory / "experiment.json"
    if (
        not expected_spec
        or not _safe_run_file(directory, "experiment.json")
        or file_hash(spec_path) != expected_spec
    ):
        issues.append("Experiment specification hash is missing or does not match")
    artifacts = record.get("artifacts", [])
    verified = {}
    for entry in artifacts:
        try:
            relative = _safe_relative_path(entry["path"])
            path = directory / relative
            if not _safe_run_file(directory, relative):
                raise ValueError("Nonlocal artifact")
            if file_hash(path) != entry["sha256"]:
                raise ValueError("Artifact hash mismatch")
            verified[relative] = entry["sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            issues.append(
                "Artifact verification failed: "
                + str(
                    entry.get("path", "unknown")
                    if isinstance(entry, dict)
                    else "malformed entry"
                )
            )
    required_artifacts = {
        "simulator/stats.txt",
        "simulator/system.terminal",
        "stdout.txt",
        "stderr.txt",
    }
    declared_required = record.get("required_artifacts", [])
    if not isinstance(declared_required, list):
        issues.append("required_artifacts must be a list")
        declared_required = []
    for required in declared_required:
        try:
            required_artifacts.add(_safe_relative_path(required))
        except (ValueError, TypeError):
            issues.append("Invalid required artifact path")
    for required in sorted(required_artifacts):
        if required not in verified:
            issues.append(
                "Required artifact is missing or not hash-verified: " + required
            )
    if not record.get("inputs"):
        issues.append("No declared input hashes")
    for entry in record.get("inputs", []):
        if (
            not entry.get("path")
            or not entry.get("sha256")
            or entry.get("unchanged_after_run") is not True
            or entry.get("sha256_after_run") != entry.get("sha256")
        ):
            issues.append("Input provenance is missing or changed during the run")
        snapshot = entry.get("snapshot")
        if record.get("snapshot_inputs") and not snapshot:
            issues.append(
                "Declared input snapshot is missing: " + str(entry.get("path"))
            )
        if snapshot is not None:
            try:
                relative = _safe_relative_path(snapshot["path"])
                if (
                    snapshot.get("unchanged_after_run") is not True
                    or snapshot.get("sha256_after_run") != snapshot.get("sha256")
                    or snapshot.get("sha256") != entry.get("sha256")
                    or verified.get(relative) != snapshot.get("sha256")
                ):
                    raise ValueError(
                        "Snapshot does not agree with input or artifact evidence"
                    )
            except (TypeError, KeyError, ValueError, AttributeError):
                issues.append(
                    "Input snapshot verification failed: " + str(entry.get("path"))
                )
    executable = record.get("executable") or {}
    if (
        not executable.get("sha256")
        or executable.get("unchanged_after_run") is not True
        or executable.get("sha256_after_run") != executable.get("sha256")
    ):
        issues.append(
            "Executable hash or recorded post-run integrity check is missing or inconsistent"
        )
    for name in CORE_METRICS:
        if stats["metrics"].get(name, {}).get("status") != "present":
            issues.append("Required metric is missing or invalid: " + name)
    issues.extend(stats["issues"])
    declared_metrics = (experiment.get("metrics") or {}).get("deterministic", {})
    declared_names = (
        list(declared_metrics) if isinstance(declared_metrics, dict) else []
    )
    selected_names = (
        list(CORE_METRICS)
        + declared_names
        + sorted(name for name in stats["metrics"] if _accelerator_metric(name))
    )
    selected_metrics = {
        name: stats["metrics"][name]
        for name in selected_names
        if name in stats["metrics"]
    }
    from .observability import assess_run_observability

    observability = assess_run_observability(directory, record, experiment)
    if observability["status"] == "invalid":
        issues.extend("Observability: " + issue for issue in observability["issues"])
    return {
        "directory": str(directory),
        "run_id": record.get("run_id", directory.name),
        "recorded_state": record.get("state"),
        "correctness_verified": not issues,
        "raw_correctness": raw_correctness,
        "raw_simulator_exit": raw_exit,
        "verified_required_artifacts": {
            name: name in verified for name in sorted(required_artifacts)
        },
        "issues": issues,
        "record": record,
        "experiment": experiment,
        "statistics": {k: v for k, v in stats.items() if k != "metrics"},
        "metrics": selected_metrics,
        "observability": observability,
        "accelerator_metrics_available": any(
            _accelerator_metric(name) for name in selected_metrics
        ),
    }


def _input_identity(record):
    return sorted(
        [entry.get("path", ""), entry.get("sha256", "")]
        for entry in record.get("inputs", [])
    )


def _normalized_argv(record):
    return [
        "--outdir=<run>/simulator" if str(arg).startswith("--outdir=") else arg
        for arg in record.get("argv", [])
    ]


def _observability_identity(run):
    observation = run.get("observability") or {}
    entries = []
    for item in observation.get("records", []):
        identity = item.get("identity") or {}
        for name, metric in sorted(item.get("metrics", {}).items()):
            entries.append(
                [
                    identity.get("accelerator"),
                    identity.get("invocation"),
                    name,
                    metric.get("value"),
                    metric.get("unit"),
                    metric.get("availability"),
                ]
            )
    return {
        "status": observation.get("status", "unavailable"),
        "measurements": entries,
    }


def compare_runs(run_a, run_b):
    """Compare two independent repeats with strict, predeclared zero tolerance."""
    runs = [load_run(run_a), load_run(run_b)]
    issues = []
    differences = []
    observations = []
    if Path(run_a).resolve() == Path(run_b).resolve():
        issues.append("Two different run directories are required")
    for run in runs:
        issues.extend(str(run["run_id"]) + ": " + issue for issue in run["issues"])
    contract = (runs[0]["experiment"].get("metrics") or {}).get("deterministic")
    if contract is None:
        contract = {name: {"absolute_tolerance": 0} for name in DETERMINISTIC_METRICS}
    if not isinstance(contract, dict) or not set(DETERMINISTIC_METRICS).issubset(
        contract
    ):
        issues.append(
            "Deterministic metric contract must include the three baseline simulated metrics"
        )
        contract = {name: {"absolute_tolerance": 0} for name in DETERMINISTIC_METRICS}
    for name, policy in contract.items():
        try:
            tolerance = Decimal(str(policy["absolute_tolerance"]))
            if not tolerance.is_finite() or tolerance != 0 or name == "hostSeconds":
                raise ValueError("Unsupported comparison policy")
        except (TypeError, KeyError, InvalidOperation, ValueError):
            issues.append(
                "Only predeclared zero tolerance on simulated metrics is supported: "
                + name
            )
    a, b = [run["record"] for run in runs]
    invariant_pairs = {
        "experiment_spec_sha256": (
            a.get("experiment_spec_sha256"),
            b.get("experiment_spec_sha256"),
        ),
        "input_hashes": (_input_identity(a), _input_identity(b)),
        "executable_sha256": (
            (a.get("executable") or {}).get("sha256"),
            (b.get("executable") or {}).get("sha256"),
        ),
        "command_except_output_directory": (
            _normalized_argv(a),
            _normalized_argv(b),
        ),
        "cwd": (a.get("cwd"), b.get("cwd")),
        "environment": (a.get("environment"), b.get("environment")),
        "observability_measurements": (
            _observability_identity(runs[0]),
            _observability_identity(runs[1]),
        ),
    }
    invariants = {
        name: {"match": pair[0] == pair[1], "a": pair[0], "b": pair[1]}
        for name, pair in invariant_pairs.items()
    }
    for name, comparison in invariants.items():
        if not comparison["match"]:
            differences.append("Invariant differs: " + name)
    metrics = []
    names = list(CORE_METRICS) + sorted(
        (set(runs[0]["metrics"]) | set(runs[1]["metrics"]) | set(contract))
        - set(CORE_METRICS)
    )
    for name in names:
        left = runs[0]["metrics"].get(name)
        right = runs[1]["metrics"].get(name)
        strict = name in contract and name != "hostSeconds"
        entry = {
            "name": name,
            "a": left,
            "b": right,
            "deterministic": strict,
            "absolute_tolerance": "0" if strict else None,
            "match": None,
            "difference": None,
            "observation": None,
        }
        if (
            left is None
            or right is None
            or left["status"] != "present"
            or right["status"] != "present"
        ):
            target = issues if strict or name in CORE_METRICS else observations
            target.append("Comparison metric is missing or invalid: " + name)
            entry["observation"] = "missing or invalid"
        else:
            delta = Decimal(right["value"]) - Decimal(left["value"])
            entry["difference"] = str(delta)
            if strict:
                entry["match"] = delta == 0
                if delta != 0:
                    differences.append("Deterministic metric differs: " + name)
            elif name != "hostSeconds":
                entry["observation"] = (
                    "different values" if delta != 0 else "same printed value"
                )
                if delta != 0:
                    observations.append(
                        "Optional counter differs outside the acceptance contract: "
                        + name
                    )
        metrics.append(entry)
    outcome = "incomplete" if issues else ("different" if differences else "matched")
    return {
        "schema_version": 1,
        "kind": "gem5_repeat_comparison",
        "outcome": outcome,
        "repeatability_accepted": outcome == "matched",
        "measurement_scope": runs[0]["experiment"]
        .get("metrics", {})
        .get("scope", MEASUREMENT_SCOPE),
        "statistics_selection": "final_complete_block",
        "deterministic_metrics": [
            item["name"] for item in metrics if item["deterministic"]
        ],
        "absolute_tolerance": "0",
        "host_seconds_note": "Host elapsed time is observational, not a deterministic simulated-performance metric.",
        "optional_metrics_policy": "Accelerator-object counters outside the predeclared deterministic metric contract are observations only; differences and undefined values do not change baseline acceptance.",
        "accelerator_metrics_note": "Additional accelerator-object counters are shown only when present; they are not interpreted as independently validated accelerator-only performance.",
        "issues": issues,
        "differences": differences,
        "observations": observations,
        "invariants": invariants,
        "metrics": metrics,
        "runs": runs,
    }


def _escape(value):
    return html.escape(str(value), quote=True)


def _link(path, report_dir, label):
    path = Path(path).resolve()
    try:
        href = quote(
            os.path.relpath(str(path), str(report_dir)).replace(os.sep, "/"),
            safe="/:",
        )
    except ValueError:
        href = path.as_uri()
    return '<a href="' + _escape(href) + '">' + _escape(label) + "</a>"


def render_html(comparison, report_dir):
    """Self-contained, escaped HTML; no scripts, remote resources, or inferred speedup."""
    from .observability_report import render_observability

    report_dir = Path(report_dir).resolve()
    rows = []
    for metric in comparison["metrics"]:
        a, b = metric["a"], metric["b"]
        policy = (
            "Exact match required; tolerance 0"
            if metric["deterministic"]
            else "Observation only"
        )
        result = (
            ("match" if metric["match"] else "different")
            if metric["match"] is not None
            else (metric["observation"] or "not assessed")
        )
        rows.append(
            "<tr><th>"
            + _escape(metric["name"])
            + "</th><td>"
            + _escape(a["value"] if a else "missing")
            + "</td><td>"
            + _escape(b["value"] if b else "missing")
            + "</td><td>"
            + policy
            + "</td><td>"
            + _escape(result)
            + "</td></tr>"
        )
    sections = []
    for run in comparison["runs"]:
        directory = Path(run["directory"])
        statistics = run["statistics"]
        links = " · ".join(
            _link(directory / path, report_dir, label)
            for path, label in (
                ("run.json", "Run record"),
                ("experiment.json", "Experiment specification"),
                ("stdout.txt", "Simulator stdout"),
                ("stderr.txt", "Simulator stderr"),
                ("simulator/system.terminal", "Guest correctness output"),
                ("simulator/stats.txt", "Raw statistics"),
            )
        )
        selected = statistics["selected_block"]
        block_text = str(selected["index"]) if selected else "none"
        sections.append(
            "<section><h2>"
            + _escape(run["run_id"])
            + "</h2><p>Recorded run state: <strong>"
            + _escape(run["recorded_state"])
            + "</strong>. Evidence verified: "
            + ("yes" if run["correctness_verified"] else "no")
            + ".</p><p>Selected complete statistics block "
            + block_text
            + " of "
            + str(statistics["block_count"])
            + " started blocks; "
            + str(statistics["complete_block_count"])
            + " complete, "
            + str(statistics["incomplete_block_count"])
            + " incomplete.</p><p>"
            + links
            + "</p>"
            + render_observability(run, report_dir)
            + "<details><summary>Statistics diagnostics, including unselected fields</summary><pre>"
            + _escape(json.dumps(statistics, indent=2))
            + "</pre></details><details><summary>Experiment and recorded command</summary><pre>"
            + _escape(
                json.dumps(
                    {
                        "experiment": run["experiment"],
                        "argv": run["record"].get("argv"),
                        "cwd": run["record"].get("cwd"),
                    },
                    indent=2,
                )
            )
            + "</pre></details></section>"
        )
    findings = comparison["issues"] + comparison["differences"]
    findings_html = (
        "<ul>"
        + "".join("<li>" + _escape(item) + "</li>" for item in findings)
        + "</ul>"
        if findings
        else "<p>Declared invariants and deterministic metrics match across these two runs.</p>"
    )
    if comparison["observations"]:
        findings_html += (
            "<h3>Observations outside the acceptance contract</h3><ul>"
            + "".join(
                "<li>" + _escape(item) + "</li>" for item in comparison["observations"]
            )
            + "</ul>"
        )
    accelerator_note = (
        "The selected gem5 stats.txt blocks contain no validated accelerator-only performance metric; direct SALAM event measurements are shown below."
        if not any(run["accelerator_metrics_available"] for run in comparison["runs"])
        else comparison["accelerator_metrics_note"]
    )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SALAM Research Workbench — Repeat comparison</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:3rem auto;padding:0 1.5rem;color:#1b2634;background:#f4f6f8}h1,h2{line-height:1.2}header,section{background:white;padding:1.7rem;margin:1.2rem 0;border:1px solid #dce2e9;border-radius:10px}h1{font-size:2.1rem}h2{font-size:1.3rem}a{color:#155c9a}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;padding:.7rem;border-bottom:1px solid #dce2e9;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f5;padding:1rem}.scope{border-left:4px solid #a46a16;padding-left:1rem}.scroll{overflow-x:auto}.eyebrow{letter-spacing:.1em;text-transform:uppercase;font-size:.8rem;color:#526172}
</style><main><header><p class="eyebrow">SALAM Research Workbench · recorded evidence</p><h1>Two-run experiment comparison</h1><p>Repeatability result: <strong>"""
        + _escape(comparison["outcome"])
        + '</strong></p><p class="scope">'
        + _escape(comparison["measurement_scope"])
        + "</p></header><section><h2>Assessment</h2>"
        + findings_html
        + "<p>"
        + _escape(comparison["host_seconds_note"])
        + "</p><p>"
        + _escape(accelerator_note)
        + '</p></section><section><h2>gem5 statistics: final complete blocks</h2><div class="scroll"><table><thead><tr><th>Metric</th><th>Run A</th><th>Run B</th><th>Comparison policy</th><th>Result</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div><p>Values retain gem5's printed precision. simTicks: ticks; simSeconds: simulated seconds; simInsts: simulated instructions; hostSeconds: elapsed host seconds.</p></section>"
        + "".join(sections)
        + "<section><h2>Machine-readable evidence</h2><p>"
        + _link(
            report_dir / "comparison.json",
            report_dir,
            "Complete comparison, invariants, hashes, and source locations",
        )
        + "</p></section></main></html>"
    )


def write_report(run_a, run_b, output_dir):
    comparison = compare_runs(run_a, run_b)
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Never silently replace a previously published comparison.
    for name in ("comparison.json", "index.html"):
        if (directory / name).exists():
            raise FileExistsError(str(directory / name))
    (directory / "comparison.json").write_text(
        json.dumps(comparison, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (directory / "index.html").write_text(
        render_html(comparison, directory), encoding="utf-8"
    )
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a")
    parser.add_argument("run_b")
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    result = write_report(options.run_a, options.run_b, options.output)
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "output": str(Path(options.output).resolve()),
            }
        )
    )
    return 0 if result["repeatability_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
