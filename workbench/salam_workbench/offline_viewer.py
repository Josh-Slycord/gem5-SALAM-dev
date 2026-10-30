"""Offline saved-evidence viewer using the recovered SALAM CDFG widget.

No simulator, live connection or old GUI entrypoint is imported or launched.
Qt is optional for model inspection and is imported only when creating a window.
"""
import argparse
import json
from pathlib import Path
import sys

from . import report
from .runner import file_hash, _safe_relative_path, _safe_run_file

QT_BINDING = "PySide6"
MAX_CDFG_BYTES = 8 * 1024 * 1024
MAX_CDFG_NODES = 5000
CORE_UNITS = {"simTicks": "tick", "simSeconds": "second", "simInsts": "instruction",
              "hostSeconds": "host second"}


def _run_directory(path):
    path = Path(path).expanduser().resolve()
    return path.parent if path.name == "run.json" else path


def _read_comparison(path, issues):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected a comparison JSON object")
        return data
    except (OSError, ValueError) as error:
        issues.append("Saved comparison could not be read: " + str(error))
        return {}


def _metric_identity(rows):
    """Compare saved numeric claims against freshly computed metric rows."""
    if not isinstance(rows, list):
        raise ValueError("Comparison metrics must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("Malformed comparison metric")
        name = row["name"]
        if name in result:
            raise ValueError("Duplicate comparison metric: " + name)
        item = {}
        for side in ("a", "b"):
            value = row.get(side)
            if value is not None and not isinstance(value, dict):
                raise ValueError("Malformed comparison metric value")
            item[side] = None if value is None else {key: value.get(key) for key in ("value", "status")}
        for key in ("difference", "delta", "percent_change", "match", "deterministic", "domain"):
            if key in row:
                item[key] = row[key]
        result[name] = item
    return result


def _cdfg_entries(run):
    """Identify recorded accelerator CDFGs, never gem5's system config.dot."""
    entries = []
    directory = Path(run["directory"])
    for artifact in run["record"].get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        name = artifact.get("path", "")
        if not isinstance(name, str):
            continue
        basename = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if not basename.endswith(".dot") or "cdfg" not in basename:
            continue
        item = {"path": name, "status": "unverified", "nodes": None, "edges": None,
                "sha256": artifact.get("sha256"), "diagnostic": None}
        try:
            relative = _safe_relative_path(name)
            path = directory / relative
            if not _safe_run_file(directory, relative) or file_hash(path) != artifact.get("sha256"):
                raise ValueError("CDFG is not a local hash-matching recorded artifact")
            if path.stat().st_size > MAX_CDFG_BYTES:
                raise ValueError("CDFG exceeds the 8 MiB viewer limit")
            from .vendor.salam_gui.data.dot_parser import parse_cdfg_dot
            graph = parse_cdfg_dot(path)
            if not graph.nodes:
                item["status"] = "unsupported"
                raise ValueError("No instructions match the recovered SALAM CDFG format")
            if len(graph.nodes) > MAX_CDFG_NODES:
                item["status"] = "unsupported"
                raise ValueError("CDFG exceeds the 5000-node viewer limit")
            if any(edge.source not in graph.nodes or edge.target not in graph.nodes for edge in graph.edges):
                item["status"] = "unsupported"
                raise ValueError("CDFG contains edges without parsed endpoint instructions")
            item.update(status="available", nodes=len(graph.nodes), edges=len(graph.edges))
        except ImportError as error:
            item["status"] = "dependency_missing"
            item["diagnostic"] = str(error)
        except (OSError, ValueError, RuntimeError) as error:
            item["diagnostic"] = str(error)
        entries.append(item)
    return {"status": "available" if any(item["status"] == "available" for item in entries)
            else ("unavailable" if entries else "missing"), "artifacts": entries,
            "note": "Only recorded, hash-verified *cdfg*.dot instruction graphs are considered. "
                    "config.dot and its PDF/SVG copies describe system topology, not accelerator CDFG."}


def load_viewer_model(run_a, run_b, comparison_path):
    """Revalidate explicit saved runs and recompute the appropriate comparison.

    The comparison file selects a supported comparison kind, but its embedded
    run summaries, acceptance result and metric values are never trusted.
    """
    directories = [_run_directory(run_a), _run_directory(run_b)]
    issues = []
    saved = _read_comparison(comparison_path, issues)
    # Explicitly reload evidence even if the comparison is malformed/unsupported.
    runs = [report.load_run(directory) for directory in directories]
    kind = saved.get("kind")
    fresh = {}
    try:
        if kind == "gem5_repeat_comparison":
            fresh = report.compare_runs(*directories)
        elif kind == "gem5_parameter_comparison":
            from .variant_report import compare_variant_runs
            fresh = compare_variant_runs(*directories)
        else:
            issues.append("Unsupported comparison kind: " + str(kind))
    except (ImportError, OSError, ValueError, TypeError, KeyError) as error:
        issues.append("Comparison recomputation failed: " + str(error))
    if fresh:
        runs = fresh["runs"]
        acceptance_key = "accepted" if kind == "gem5_parameter_comparison" else "repeatability_accepted"
        for key in ("kind", "outcome", acceptance_key):
            if saved.get(key) != fresh.get(key):
                issues.append("Saved comparison differs from revalidated evidence: " + key)
        try:
            saved_ids = [run["run_id"] for run in saved["runs"]]
            if saved_ids != [run["run_id"] for run in runs]:
                raise ValueError("Run identities/order differ")
            if _metric_identity(saved.get("metrics")) != _metric_identity(fresh.get("metrics")):
                raise ValueError("Metric values or derived comparisons differ")
        except (KeyError, TypeError, ValueError) as error:
            issues.append("Saved comparison does not describe these revalidated runs: " + str(error))
    for run in runs:
        run["cdfg"] = _cdfg_entries(run)
    consistent = not issues
    run_issues = [str(run["run_id"]) + ": " + issue for run in runs for issue in run["issues"]]
    accepted = fresh.get("accepted", fresh.get("repeatability_accepted", False)) is True
    return {"schema_version": 1, "kind": "salam_offline_viewer", "qt_binding": QT_BINDING,
            "comparison_path": str(Path(comparison_path).resolve()),
            "saved_comparison_consistent": consistent,
            "evidence_verified": consistent and all(run["correctness_verified"] for run in runs),
            "accepted": consistent and accepted and all(run["correctness_verified"] for run in runs),
            "issues": issues + run_issues, "comparison": fresh, "runs": runs,
            "measurement_scope": fresh.get("measurement_scope", report.MEASUREMENT_SCOPE)}


def inspection_summary(model):
    """A bounded, JSON-serializable receipt suitable for a terminal check."""
    if model["kind"] == "salam_legacy_viewer":
        legacy = model["legacy"]
        return {"kind": model["kind"], "evidence_verified": False, "accepted": False,
                "status": legacy["status"], "legacy_format": legacy.get("legacy_format"),
                "observed_version": legacy.get("observed_version"), "provenance": legacy["provenance"],
                "issues": legacy["issues"], "measurement_count": len(legacy["metrics"]),
                "measurements_validated": False,
                "observations": [{"metric": name, "raw_value": entry.get("raw_value"),
                                  "validated_value": None, "availability": entry["availability"],
                                  "source_path": entry["source_path"]}
                                 for name, entry in legacy["metrics"].items()]}
    comparison = model["comparison"]
    return {"kind": model["kind"], "qt_binding": QT_BINDING,
            "evidence_verified": model["evidence_verified"], "accepted": model["accepted"],
            "saved_comparison_consistent": model["saved_comparison_consistent"],
            "comparison_kind": comparison.get("kind"), "comparison_outcome": comparison.get("outcome"),
            "measurement_scope": model["measurement_scope"], "issues": model["issues"],
            "comparison_findings": {key: comparison.get(key, []) for key in ("issues", "violations", "warnings")},
            "metric_count": len(comparison.get("metrics", [])),
            "runs": [{"run_id": run["run_id"], "correctness_verified": run["correctness_verified"],
                      "cdfg": run["cdfg"], "observability": observability_summary(run)} for run in model["runs"]]}


def _measurement_verified(run, parsed):
    observation = run.get("observability") or {}
    return (run.get("correctness_verified") is True and observation.get("status") == "valid"
            and observation.get("valid") is True and parsed.get("contract_valid") is True
            and (parsed.get("provenance") or {}).get("hash_verified") is True)


def observability_summary(run):
    """Bound the terminal receipt while retaining status, identities and counts."""
    observation = run.get("observability") or {}
    records = observation.get("records", [])
    identities = []
    for parsed in records[:20]:
        verified = _measurement_verified(run, parsed)
        metrics = parsed.get("metrics", {})
        def count(name):
            metric = metrics.get(name, {})
            return metric.get("value") if verified and metric.get("availability") == "observed" else None
        identities.append({"identity": parsed.get("identity"), "measurements_verified": verified,
                           "contract_status": parsed.get("status"),
                           "metric_count": len(metrics), "unsupported_count": len(parsed.get("unsupported", {})),
                           "logical_reads_completed": count("memory.reads.completed"),
                           "logical_writes_completed": count("memory.writes.completed"),
                           "queue_sample_count": count("queues.sample_count")})
    return {"status": observation.get("status", "unavailable"), "valid": observation.get("valid"),
            "record_count": len(records), "identities": identities,
            "omitted_identities": max(0, len(records) - len(identities)),
            "issue_count": len(observation.get("issues", []))}


def accelerator_measurement_rows(run):
    """Never expose unchecked values as verified runtime measurements."""
    observation = run.get("observability") or {}
    rows = []
    for parsed in observation.get("records", []):
        verified = _measurement_verified(run, parsed)
        identity = parsed.get("identity") or {}
        for name, entry in parsed.get("metrics", {}).items():
            rows.append({"accelerator": identity.get("accelerator"), "invocation": identity.get("invocation"),
                         "metric": name, "value": entry.get("value") if verified else None,
                         "unit": entry.get("unit"), "availability": entry.get("availability") if verified else "unverified",
                         "scope": entry.get("scope") or entry.get("reason") or "Declared collector field",
                         "source": entry.get("source_path") or ", ".join(entry.get("source_paths", [])),
                         "verified": verified})
        for name, entry in parsed.get("unsupported", {}).items():
            rows.append({"accelerator": identity.get("accelerator"), "invocation": identity.get("invocation"),
                         "metric": name, "value": None, "unit": None,
                         "availability": entry.get("availability", "unknown"),
                         "scope": entry.get("reason", "Measurement coverage unavailable"),
                         "source": "/unsupported/" + name, "verified": False})
    if not rows:
        rows.append({"accelerator": None, "invocation": None, "metric": "collector",
                     "value": None, "unit": None, "availability": observation.get("status", "unavailable"),
                     "scope": "; ".join(observation.get("issues", [])) or "No event-backed observability contract was declared for this run",
                     "source": None, "verified": False})
    return rows


def load_legacy_model(path, format_name):
    """A separate historical view; no run comparison or runtime claim is needed."""
    from .observability import load_observability
    legacy = load_observability(path, legacy_format=format_name)
    return {"kind": "salam_legacy_viewer", "qt_binding": QT_BINDING, "legacy": legacy,
            "evidence_verified": False, "accepted": False}


def _create_legacy_window(model):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel, QTabWidget, QPlainTextEdit,
                                  QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView)
    legacy = model["legacy"]
    window = QMainWindow()
    window.setWindowTitle("SALAM Research Workbench | Historical observations")
    window.resize(1280, 860)
    central = QWidget()
    layout = QVBoxLayout(central)
    heading = QLabel("Historical statistics — measurements unvalidated")
    heading.setObjectName("legacy-status")
    heading.setStyleSheet("font-size: 22px; font-weight: bold; color: #8c4a17;")
    layout.addWidget(heading)
    note = QLabel("Raw historical values are preserved below. Validated runtime values remain unknown. "
                  "This view does not establish measured cache behavior, latency units, FU utilization, power or area.")
    note.setWordWrap(True)
    note.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(note)
    tabs = QTabWidget()
    layout.addWidget(tabs)
    table = QTableWidget(len(legacy["metrics"]), 7)
    table.setObjectName("legacy-metric-table")
    table.setHorizontalHeaderLabels(["Metric", "Raw historical value", "Validated runtime value",
                                    "Claimed historical unit", "Availability", "Source field", "Reason"])
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    for row, (name, entry) in enumerate(legacy["metrics"].items()):
        raw = entry.get("raw_value")
        values = [name, "missing" if entry["availability"] == "missing" else json.dumps(raw, ensure_ascii=False),
                  "unknown", entry.get("claimed_unit", "unknown"), entry["availability"],
                  entry["source_path"], entry["reason"]]
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(str(value)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    tabs.addTab(table, "Raw observations")
    detail = QPlainTextEdit()
    detail.setReadOnly(True)
    detail.setPlainText(json.dumps({"format": legacy.get("legacy_format"), "observed_version": legacy.get("observed_version"),
                                   "status": legacy["status"], "contract_valid": False,
                                   "provenance": legacy["provenance"], "issues": legacy["issues"]}, indent=2))
    tabs.addTab(detail, "Provenance")
    window.setCentralWidget(central)
    window.statusBar().showMessage("Historical adapter • Raw source retained • No validated runtime measurements")
    return window


def _display_value(value):
    if not value:
        return "missing"
    token = str(value.get("value", "missing"))
    return token if value.get("status") == "present" else token + " [" + str(value.get("status")) + "]"


def create_window(model):
    """Create a PySide6 window; the caller owns QApplication and its event loop."""
    if model["kind"] == "salam_legacy_viewer":
        return _create_legacy_window(model)
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                  QLabel, QPushButton, QTabWidget, QPlainTextEdit,
                                  QTableWidget, QTableWidgetItem, QAbstractItemView,
                                  QHeaderView)

    window = QMainWindow()
    window.setWindowTitle("SALAM Research Workbench | Saved evidence")
    window.resize(1280, 860)
    window.setStyleSheet("QMainWindow { background: #eef2f5; } QLabel { color: #172b3a; } "
                        "QTabWidget::pane { background: white; border: 1px solid #ccd6de; } "
                        "QPlainTextEdit, QTableWidget { background: white; color: #172b3a; "
                        "font-size: 12px; border: 0; } QPushButton { padding: 7px 12px; }")
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(24, 20, 24, 20)
    title = QLabel("SALAM Research Workbench")
    title.setStyleSheet("font-size: 25px; font-weight: 600;")
    layout.addWidget(title)
    badge = QLabel("Saved evidence verified" if model["evidence_verified"] else "Evidence needs attention")
    badge.setObjectName("evidence-status")
    badge.setStyleSheet("font-size: 15px; font-weight: bold; color: "
                       + ("#14654b" if model["evidence_verified"] else "#9b3a20") + ";")
    layout.addWidget(badge)
    scope = QLabel(model["measurement_scope"])
    scope.setTextFormat(Qt.TextFormat.PlainText)
    scope.setWordWrap(True)
    layout.addWidget(scope)
    links = QHBoxLayout()
    for index, run in enumerate(model["runs"]):
        button = QPushButton("Open run " + ("A" if index == 0 else "B") + " record")
        path = str(Path(run["directory"]) / "run.json")
        button.clicked.connect(lambda checked=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
        links.addWidget(button)
    links.addStretch()
    layout.addLayout(links)
    tabs = QTabWidget()
    tabs.setObjectName("evidence-tabs")
    layout.addWidget(tabs)

    def text_tab(title_text, content):
        widget = QPlainTextEdit()
        widget.setReadOnly(True)
        widget.setPlainText(content)
        tabs.addTab(widget, title_text)
        return widget

    comparison = model["comparison"]
    overview = ["Comparison: " + str(comparison.get("kind", "unavailable")),
                "Recomputed outcome: " + str(comparison.get("outcome", "unavailable")),
                "Acceptance: " + ("accepted" if model["accepted"] else "not accepted"),
                "Saved comparison agrees: " + str(model["saved_comparison_consistent"]), ""]
    for index, run in enumerate(model["runs"]):
        overview.extend(["RUN " + ("A" if index == 0 else "B") + " — " + str(run["run_id"]),
                         "Raw guest correctness and evidence verified: " + str(run["correctness_verified"]),
                         "Recorded state: " + str(run["recorded_state"]),
                         "CDFG: " + run["cdfg"]["status"],
                         "Statistics: final complete block " + str(run["statistics"].get("selected_block")), ""])
    if comparison.get("parameter_change"):
        overview.extend(["DECLARED PARAMETER CHANGE", json.dumps(comparison["parameter_change"], indent=2), ""])
    overview.extend(["ISSUES"] + (model["issues"] or ["None in the revalidated evidence."]))
    for key in ("issues", "violations", "differences", "warnings", "observations"):
        if comparison.get(key):
            overview.extend(["", "COMPARISON " + key.upper(), json.dumps(comparison[key], indent=2)])
    text_tab("Overview", "\n".join(overview))

    metrics = comparison.get("metrics", [])
    table = QTableWidget(len(metrics), 6)
    table.setObjectName("metric-table")
    table.setHorizontalHeaderLabels(["Metric", "Run A", "Run B", "B minus A", "Unit", "Interpretation"])
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    for row, metric in enumerate(metrics):
        name = metric["name"]
        if comparison.get("kind") == "gem5_parameter_comparison":
            meaning = metric.get("domain", "unvalidated_optional") + "; " + str(metric.get("observation") or "observed delta")
        else:
            meaning = "Exact repeat check" if metric.get("deterministic") else "Observation only"
        if name == "hostSeconds":
            meaning = "Host elapsed time; not simulated performance"
        values = [name, _display_value(metric.get("a")), _display_value(metric.get("b")),
                  metric.get("delta", metric.get("difference")) or "—",
                  metric.get("unit") or CORE_UNITS.get(name, "not validated"), meaning]
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(str(value)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    tabs.addTab(table, "Full-window metrics")

    observation_page = QWidget()
    observation_layout = QVBoxLayout(observation_page)
    statuses = ["Run " + ("A" if index == 0 else "B") + ": " + observability_summary(run)["status"]
                for index, run in enumerate(model["runs"])]
    observation_note = QLabel("; ".join(statuses) + ". Values are shown only after run, schema and artifact-hash verification. "
                             "Unsupported measurements remain unknown; queue means use the declared interface-entry sampling scope.")
    observation_note.setObjectName("observability-status")
    observation_note.setWordWrap(True)
    observation_note.setTextFormat(Qt.TextFormat.PlainText)
    observation_layout.addWidget(observation_note)
    observation_rows = [(("A" if index == 0 else "B"), entry)
                        for index, run in enumerate(model["runs"]) for entry in accelerator_measurement_rows(run)]
    observation_table = QTableWidget(len(observation_rows), 9)
    observation_table.setObjectName("observability-table")
    observation_table.setHorizontalHeaderLabels(["Run", "Accelerator", "Invocation", "Metric", "Value", "Unit",
                                                "Availability", "Scope / reason", "Source field"])
    observation_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    observation_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    for row, (letter, entry) in enumerate(observation_rows):
        values = [letter, entry["accelerator"] or "not recorded",
                  entry["invocation"] if entry["invocation"] is not None else "—", entry["metric"],
                  entry["value"] if entry["value"] is not None else "unknown", entry["unit"] or "unknown",
                  entry["availability"], entry["scope"], entry["source"] or "—"]
        for column, value in enumerate(values):
            observation_table.setItem(row, column, QTableWidgetItem(str(value)))
    observation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    observation_table.horizontalHeader().setStretchLastSection(True)
    observation_layout.addWidget(observation_table)
    tabs.addTab(observation_page, "Accelerator measurements")

    provenance = []
    for run in model["runs"]:
        record = run["record"]
        provenance.append({"run_id": run["run_id"], "directory": run["directory"],
                           "source": run["experiment"].get("source"),
                           "executable": record.get("executable"),
                           "experiment_spec_sha256": record.get("experiment_spec_sha256"),
                           "inputs": record.get("inputs"),
                           "verified_required_artifacts": run.get("verified_required_artifacts"),
                           "raw_correctness": run.get("raw_correctness"),
                           "raw_simulator_exit": run.get("raw_simulator_exit"),
                           "statistics_warnings": run["statistics"].get("warnings", [])})
    text_tab("Provenance", json.dumps(provenance, indent=2, ensure_ascii=False))
    text_tab("Comparison checks", json.dumps({key: comparison.get(key) for key in
             ("invariants", "issues", "violations", "warnings", "differences", "observations", "parameter_change",
              "effective_config_differences")}, indent=2, ensure_ascii=False))

    for index, run in enumerate(model["runs"]):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        info = QLabel("CDFG: " + run["cdfg"]["status"] + ". " + run["cdfg"]["note"])
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.PlainText)
        page_layout.addWidget(info)
        available = [entry for entry in run["cdfg"]["artifacts"] if entry["status"] == "available"]
        if available:
            from .vendor.salam_gui.data.dot_parser import parse_cdfg_dot
            from .vendor.salam_gui.widgets.cdfg_viewer import CDFGViewer
            graphs = QTabWidget()
            for entry in available:
                path = Path(run["directory"]) / entry["path"]
                if not _safe_run_file(Path(run["directory"]), entry["path"]) or file_hash(path) != entry["sha256"]:
                    page_layout.addWidget(QLabel("CDFG changed since verification; reopen the evidence."))
                    continue
                viewer = CDFGViewer()
                viewer.set_graph(parse_cdfg_dot(path))
                graphs.addTab(viewer, Path(entry["path"]).name)
            page_layout.addWidget(graphs)
        else:
            placeholder = QLabel("No verified accelerator CDFG was captured in this saved run.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("font-size: 18px; color: #677c8c;")
            page_layout.addWidget(placeholder, 1)
            if run["cdfg"]["artifacts"]:
                detail = QPlainTextEdit(json.dumps(run["cdfg"]["artifacts"], indent=2))
                detail.setReadOnly(True)
                page_layout.addWidget(detail)
        tabs.addTab(page, "Run " + ("A" if index == 0 else "B") + " · CDFG")
    window.setCentralWidget(central)
    window.statusBar().showMessage("Offline • PySide6 • Recovered CDFG parser/widget • No simulator connection")
    return window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", nargs="?", help="Saved run directory or its run.json")
    parser.add_argument("run_b", nargs="?", help="Second saved run directory or its run.json")
    parser.add_argument("comparison", nargs="?", help="Saved comparison.json")
    parser.add_argument("--legacy-stats", help="View a historical statistics JSON independently of current runs")
    parser.add_argument("--legacy-format", choices=("legacy_nested_v3", "legacy_flat_v3"))
    parser.add_argument("--inspect", action="store_true", help="Verify and print a bounded receipt without Qt")
    parser.add_argument("--screenshot", help="Render once to a new PNG file, then exit")
    options = parser.parse_args(argv)
    if options.legacy_stats:
        if options.run_a or options.run_b or options.comparison or not options.legacy_format:
            parser.error("--legacy-stats requires --legacy-format and cannot be combined with run arguments")
    elif not all((options.run_a, options.run_b, options.comparison)) or options.legacy_format:
        parser.error("Supply two saved runs and comparison.json, or use the explicit legacy mode")
    try:
        model = (load_legacy_model(options.legacy_stats, options.legacy_format) if options.legacy_stats
                 else load_viewer_model(options.run_a, options.run_b, options.comparison))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        parser.exit(1, "Cannot load saved evidence: " + str(error) + "\n")
    if options.inspect:
        print(json.dumps(inspection_summary(model), indent=2))
        return 0 if model["evidence_verified"] or (options.legacy_stats and model["legacy"]["status"] == "legacy_unvalidated") else 1
    try:
        from PySide6.QtWidgets import QApplication
        application = QApplication.instance() or QApplication([sys.argv[0]])
        window = create_window(model)
    except ImportError as error:
        parser.exit(2, "PySide6 viewer dependency unavailable: " + str(error)
                    + ". Use the documented Ubuntu-20.04 environment or requirements-gui.txt.\n")
    window.show()
    application.processEvents()
    if options.screenshot:
        destination = Path(options.screenshot).expanduser().resolve()
        if destination.exists():
            parser.exit(1, "Screenshot destination already exists; choose a new path.\n")
        if not window.grab().save(str(destination), "PNG"):
            parser.exit(1, "Could not save screenshot.\n")
        window.close()
        print(json.dumps(inspection_summary(model), indent=2))
        return 0 if model["evidence_verified"] or (options.legacy_stats and model["legacy"]["status"] == "legacy_unvalidated") else 1
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
