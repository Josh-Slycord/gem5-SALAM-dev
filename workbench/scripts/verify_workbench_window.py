"""Exercise the production desktop window, real QProcess jobs and result reader.

This is explicit integration work, never a unit test. Qt renders offscreen;
the configured simulator and reference harnesses still run for real. It saves
requests, raw result-reader output, screenshots and source identity so the
application's displayed success can be inspected after the run.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
os.environ["SALAM_WORKBENCH_ROOT"] = str(PROJECT)

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication

from salam_workbench.checks import _snapshot_sources, source_identity
from salam_workbench.runner import file_hash
from salam_workbench.workbench_catalog import discover_benchmarks
from salam_workbench.workbench_results import load_run
from salam_workbench.workbench_window import WorkbenchWindow

_BENCHMARK = re.compile(
    r"benchmarks/(?:sys_validation|legacy|lenet5-nounroll|mobilenetv2)/[A-Za-z0-9_-]+$"
)


def _save(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _cases(text):
    cases = []
    for entry in text.split(","):
        mode, separator, benchmark = entry.strip().partition(":")
        if not separator or mode not in ("configured", "reference"):
            raise argparse.ArgumentTypeError(
                "Use configured:gemm,reference:bfs or full benchmark paths"
            )
        if "/" not in benchmark:
            benchmark = "benchmarks/sys_validation/" + benchmark
        if not _BENCHMARK.fullmatch(benchmark):
            raise argparse.ArgumentTypeError(
                "Unsafe or unsupported benchmark path: " + benchmark
            )
        cases.append((mode, benchmark))
    if not cases:
        raise argparse.ArgumentTypeError(
            "Choose at least one explicit integration case"
        )
    return cases


def _tree_rows(tree):
    return [
        [tree.topLevelItem(index).text(column) for column in range(tree.columnCount())]
        for index in range(tree.topLevelItemCount())
    ]


def _quiet(window):
    return (
        not window._busy
        and not window._tasks
        and not getattr(window, "_task_queue", {})
    )


def _wait(app, window, predicate, deadline, label):
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise TimeoutError(label + " did not finish within the integration timeout")
        time.sleep(0.02)
    app.processEvents()


def _find_benchmark(window, benchmark):
    matches = []
    for group_index in range(window.benchmark_tree.topLevelItemCount()):
        group = window.benchmark_tree.topLevelItem(group_index)
        for index in range(group.childCount()):
            item = group.child(index)
            if item.data(0, Qt.UserRole).get("key") == benchmark:
                matches.append(item)
    if len(matches) != 1:
        raise ValueError(
            "Actual library did not contain one requested benchmark: " + benchmark
        )
    return matches[0]


def _configure_gemm(editor):
    """Change live controls whose transport and scheduling must be witnessed."""
    editor.mem_size_edit.setText("2GB")
    if editor.trace_budget_check.isEnabled():
        editor.trace_budget_check.setChecked(True)
        editor.trace_budget_spin.setValue(1048576)
    if editor.hardware_target_combo.findText("gemm") >= 0:
        editor.hardware_target_combo.setCurrentText("gemm")
    units = [
        editor.fu_tree.topLevelItem(index)
        for index in range(editor.fu_tree.topLevelItemCount())
        if editor.fu_tree.topLevelItem(index).text(0) == "integer_multiplier"
    ]
    instructions = [
        editor.inst_tree.topLevelItem(index)
        for index in range(editor.inst_tree.topLevelItemCount())
        if editor.inst_tree.topLevelItem(index).text(0) == "mul"
    ]
    if len(units) != 1 or len(instructions) != 1:
        raise ValueError(
            "GEMM editor did not expose its multiplier and mul instruction controls"
        )
    units[0].setText(1, "1")
    units[0].setText(2, "2")
    instructions[0].setText(1, "16")
    return {
        "mem-size": "2GB",
        "integer_multiplier.cycles": 1,
        "integer_multiplier.limit": 2,
        "mul.runtime_cycles": 16,
        "fu_trace_event_limit": 1048576 if editor.trace_budget_check.isChecked() else None,
    }


def _screenshot(window, path):
    if not window.grab().save(str(path)):
        raise RuntimeError("Qt could not save its integration rendering")


def _assert_gemm_scheduling(result):
    units = {}
    for metric in result.get("metrics", []):
        name = metric.get("name", "")
        if (
            ".integer_multiplier." in name
            and metric.get("status") == "validated_direct_trace"
        ):
            prefix, field = name.rsplit(".", 1)
            units.setdefault(prefix, {})[field] = metric.get("value")
    for name, values in units.items():
        if (
            values.get("limit") == 2
            and type(values.get("peak")) is int
            and 0 < values["peak"] <= 2
            and values.get("grants", 0) > 0
            and values.get("denials", 0) > 0
            and values.get("releases") == values.get("grants")
            and values.get("outstanding") == 0
        ):
            return {"name": name, **values}
    raise ValueError(
        "Direct SALAM replay did not witness the edited multiplier capacity of two"
    )


def _run_case(app, window, mode, benchmark, directory, timeout, input_seed=None):
    started = time.monotonic()
    deadline = started + timeout
    directory.mkdir()
    case = {
        "mode": mode,
        "benchmark": benchmark,
        "state": "running",
        "errors": [],
        "backend_results_mocked": False,
        "actual_run_button_clicked": False,
        "configuration_changes": {},
    }
    _save(directory / "case.json", case)
    try:
        _wait(
            app,
            window,
            lambda: _quiet(window),
            deadline,
            "Previous background evidence reads",
        )
        item = _find_benchmark(window, benchmark)
        window.benchmark_tree.setCurrentItem(item)
        window.mode_combo.setCurrentIndex(window.mode_combo.findData(mode))
        app.processEvents()
        if window.selected_benchmark.get("key") != benchmark:
            raise ValueError(
                "The visible library selection did not reach the production window"
            )
        if not window.run_btn.isEnabled():
            raise ValueError(
                "Actual Run button is disabled: " + window.mode_note.text()
            )
        if mode == "configured":
            if input_seed is not None:
                window.editor.input_case_combo.setCurrentIndex(1)
                window.editor.input_seed_spin.setValue(input_seed)
            if benchmark == "benchmarks/sys_validation/gemm":
                case["configuration_changes"] = _configure_gemm(window.editor)
            request = window.editor._make_request()
            if request.get("benchmark") != benchmark:
                raise ValueError("Editor request differs from the visible benchmark")
            _save(directory / "request-before-transport.json", request)
            case["request_source"] = request.get("provenance", {}).get("source_config")
        case["mode_note"] = window.mode_note.text()
        case["editor_enabled_before_run"] = window.editor.isEnabled()
        window.pages.setCurrentIndex(0)
        _screenshot(window, directory / "configuration.png")
        case["actual_run_button_clicked"] = True
        window.run_btn.click()
        app.processEvents()
        case["run_locked_after_start"] = window._busy and not window.run_btn.isEnabled()
        if not case["run_locked_after_start"]:
            raise ValueError(
                "Production window did not lock the active request after launch"
            )
        _screenshot(window, directory / "running.png")
        _wait(
            app,
            window,
            lambda: _quiet(window),
            deadline,
            "Simulation and raw-result verification",
        )
        case["window_completed_state"] = getattr(window, "_last_completed_state", None)
        case["window_status"] = window.run_status.text()
        case["evidence_directory"] = window._run_target
        case["summary"] = (
            window.editor._gui_summary
            if mode == "configured"
            else window._reference_summary
        )
        transported = (
            getattr(window.editor, "_gui_request", None)
            if mode == "configured"
            else None
        )
        if transported is not None:
            _save(directory / "transported-request.json", transported)
        if not window._run_target:
            raise ValueError("Production window returned no durable evidence directory")
        result = load_run(window._run_target, PROJECT)
        _save(directory / "raw-reader-result.json", result)
        window._show_run(result)
        case["reader_receipt"] = result.get("path")
        case["recorded_state"] = result.get("state")
        case["validation_state"] = result.get("validation_state")
        case["checks"] = result.get("checks", [])
        case["metrics_count"] = len(result.get("metrics", []))
        case["missing_metrics"] = [
            {
                key: metric.get(key)
                for key in ("name", "value", "scope", "status", "source")
            }
            for metric in result.get("metrics", [])
            if metric.get("value") is None
        ]
        case["sources"] = sorted(
            {str(m.get("source")) for m in result.get("metrics", []) if m.get("source")}
        )
        case["artifact_paths"] = result.get("artifacts", [])
        topology = window.topology.loaded or {}
        case["topology"] = {
            key: topology.get(key)
            for key in (
                "state",
                "source",
                "sha256",
                "scope",
                "sanitized_for_display",
                "dot",
                "pdf",
                "issues",
            )
        }
        if topology.get("state") != "ready":
            raise ValueError(
                "The actual topology panel could not load the recorded graph: "
                + str(topology.get("issues", []))
            )
        case["topology"]["qt_renderer_valid"] = bool(
            window.topology.renderer and window.topology.renderer.isValid()
        )
        if (
            not case["topology"]["qt_renderer_valid"]
            or window.topology.graph_item is None
        ):
            raise ValueError(
                "The original topology SVG did not reach a valid Qt graph renderer"
            )
        if case["window_completed_state"] != "passed":
            raise ValueError(
                "Production completion gate did not pass: "
                + str(case["window_completed_state"])
            )
        if (
            result.get("state") != "passed"
            or result.get("validation_state") != "checked_recorded_evidence"
        ):
            raise ValueError("Raw evidence reader did not accept recorded evidence")
        if result.get("benchmark") != benchmark:
            raise ValueError(
                "Raw evidence benchmark differs from the selected benchmark"
            )
        direct = [
            m
            for m in result.get("metrics", [])
            if str(m.get("scope", "")).startswith("Direct SALAM")
            and m.get("value") is not None
        ]
        case["direct_salam_metric_count"] = len(direct)
        if not direct:
            raise ValueError("The results view has no actual direct SALAM metrics")
        required = {"Guest numerical checker", "Simulator exit"}
        passed = {
            check.get("name")
            for check in result.get("checks", [])
            if check.get("status") == "passed"
        }
        if not required <= passed:
            raise ValueError("Raw guest correctness or simulator exit was not checked")
        if mode == "configured" and benchmark == "benchmarks/sys_validation/gemm":
            if transported.get("system", {}).get("mem-size") != "2GB":
                raise ValueError("Edited memory size was not transported")
            case["multiplier_scheduling"] = _assert_gemm_scheduling(result)
        if mode == "configured" and input_seed is not None:
            if transported.get("benchmark_input") != {"dataset": "seeded", "seed": input_seed}:
                raise ValueError("Selected generated inputs did not reach the backend")
            oracle = result.get("independent_oracle", {})
            if oracle.get("state") != "passed":
                raise ValueError("Results reader did not independently validate every accelerator output")
            case["independent_oracle"] = oracle
            if benchmark.endswith("/gemm") and window.editor.trace_budget_check.isChecked():
                for name in ("top", "gemm"):
                    if transported.get("parameters", {}).get("system.gemm_clstr." + name + ".llvm_interface") != {"fu_trace_event_limit": 1048576}:
                        raise ValueError("GUI trace-budget override did not reach the checked backend")
        case["rendered_metrics"] = _tree_rows(window.metrics)
        case["rendered_checks"] = _tree_rows(window.checks)
        window.pages.setCurrentIndex(2)
        window.result_tabs.setCurrentIndex(0)
        app.processEvents()
        _screenshot(window, directory / "results.png")
        window.result_tabs.setCurrentIndex(1)
        app.processEvents()
        _screenshot(window, directory / "validation.png")
        window.result_tabs.setCurrentWidget(window.topology)
        app.processEvents()
        window.topology.fit_graph()
        app.processEvents()
        bounds = window.topology.graph_item.boundingRect()
        case["topology"]["graph_bounds"] = {
            "width": bounds.width(),
            "height": bounds.height(),
        }
        if bounds.width() <= 0 or bounds.height() <= 0:
            raise ValueError("The recorded topology has no visible graph bounds")
        _screenshot(window, directory / "topology.png")
        digest_after = file_hash(Path(topology["source"]))
        case["topology"]["source_sha256_after_render"] = digest_after
        if digest_after != topology["sha256"]:
            raise ValueError("The original topology source changed during display")
        window.result_tabs.setCurrentWidget(window.metrics.parentWidget())
        app.processEvents()
        case["state"] = "passed"
    except Exception as error:
        case["state"] = "failed"
        case["errors"].append(type(error).__name__ + ": " + str(error))
        case["window_status"] = window.run_status.text()
        case["evidence_directory"] = window._run_target
        _screenshot(window, directory / "failure.png")
    finally:
        case["elapsed_seconds"] = time.monotonic() - started
        (directory / "window-log.txt").write_text(
            window.run_log.toPlainText(), encoding="utf-8"
        )
        (directory / "editor-log.txt").write_text(
            window.editor.validation_output.toPlainText(), encoding="utf-8"
        )
        _save(directory / "case.json", case)
    return case


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=_cases, default=_cases("configured:gemm,reference:bfs")
    )
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("--input-seed", type=int)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.input_seed is not None and not 0 <= args.input_seed <= 2147483647:
        parser.error("--input-seed requires a nonnegative signed 32-bit integer")
    evidence = args.evidence_dir or PROJECT / "evidence" / (
        "desktop-workbench-acceptance-"
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    evidence = evidence.absolute()
    if evidence.exists() or evidence.is_symlink():
        raise ValueError("Integration evidence directory must be new")
    evidence.mkdir(parents=True, exist_ok=False)
    before = source_identity(PROJECT)
    _save(evidence / "source-before.json", before)
    _snapshot_sources(before, PROJECT, None, evidence)
    driver = evidence / "integration-driver.py"
    shutil.copyfile(Path(__file__), driver)
    manifest = json.loads((PROJECT / "workspace.json").read_text(encoding="utf-8-sig"))
    selected = manifest["configuration_engine"]
    engine = Path(selected["path"]).resolve(strict=True)
    sys.path.insert(0, str(engine / "gem5-SALAM-gui/src"))
    from gui.config_generator import ConfigGeneratorDialog

    if (
        ConfigGeneratorDialog.generate_files.__module__
        != "salam_workbench.gui_editor_qt"
    ):
        raise ValueError("The selected GUI has no checked production adapter")
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    settings = QSettings(str(evidence / "test-preferences.ini"), QSettings.IniFormat)
    window = WorkbenchWindow(
        PROJECT,
        engine,
        selected["distribution"],
        ConfigGeneratorDialog,
        settings=settings,
        auto_discover=False,
    )
    window.catalog = discover_benchmarks(engine)
    window._show_catalog()
    window.show()
    app.processEvents()
    ticks = [0]
    ticker = QTimer()
    ticker.setInterval(100)
    ticker.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
    ticker.start()
    record = {
        "kind": "production_desktop_workbench_acceptance",
        "schema_version": 1,
        "state": "running",
        "evidence_directory": str(evidence),
        "cases": [],
        "source_sha256": before["sha256"],
        "driver_sha256": file_hash(driver),
        "rendering": "Qt offscreen product render; no manual Windows input claim",
        "backend_results_mocked": False,
        "errors": [],
    }
    _save(evidence / "acceptance.json", record)
    for index, (mode, benchmark) in enumerate(args.cases, 1):
        name = "{:02d}-{}-{}".format(index, mode, benchmark.rsplit("/", 1)[-1])
        print(
            json.dumps(
                {"kind": "workbench_acceptance", "stage": "starting", "case": name}
            ),
            flush=True,
        )
        ticks_before = ticks[0]
        case = _run_case(app, window, mode, benchmark, evidence / name, args.timeout, args.input_seed)
        case["event_loop_ticks"] = ticks[0] - ticks_before
        if case["event_loop_ticks"] < 1:
            case["state"] = "failed"
            case["errors"].append(
                "The event loop did not remain responsive during the real job"
            )
        _save(evidence / name / "case.json", case)
        record["cases"].append(case)
        _save(evidence / "acceptance.json", record)
        print(
            json.dumps(
                {
                    "kind": "workbench_acceptance",
                    "stage": "finished",
                    "case": name,
                    "state": case["state"],
                    "evidence_directory": case.get("evidence_directory"),
                }
            ),
            flush=True,
        )
        if case["state"] != "passed":
            break
    after = source_identity(PROJECT)
    _save(evidence / "source-after.json", after)
    record["source_unchanged"] = before == after
    record["event_loop_ticks"] = ticks[0]
    if before != after:
        record["errors"].append("Workbench source changed during acceptance")
    record["state"] = (
        "passed"
        if record["cases"]
        and all(case["state"] == "passed" for case in record["cases"])
        and not record["errors"]
        and len(record["cases"]) == len(args.cases)
        else "failed"
    )
    _save(evidence / "acceptance.json", record)
    ticker.stop()
    if _quiet(window):
        window.close()
    else:
        # Do not present a timeout as completion. Retain the process/window until
        # its owned job settles; the caller can inspect the live evidence path.
        print(
            json.dumps(
                {
                    "kind": "workbench_acceptance",
                    "stage": "waiting_after_failure",
                    "evidence_directory": window._run_target,
                }
            ),
            flush=True,
        )
        while not _quiet(window):
            app.processEvents()
            time.sleep(0.05)
        window.close()
    print(
        json.dumps(
            {
                "state": record["state"],
                "evidence_directory": str(evidence),
                "issues": record["errors"],
            }
        ),
        flush=True,
    )
    return 0 if record["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
