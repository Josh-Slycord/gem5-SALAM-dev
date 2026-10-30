"""Exercise the production desktop window, real QProcess jobs and result reader.

This is explicit integration work, never a unit test. Qt renders offscreen;
the configured simulator and reference harnesses still run for real. It saves
requests, raw result-reader output, screenshots and source identity so the
application's displayed success can be inspected after the run.
"""
import argparse
import configparser
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
from PySide6.QtWidgets import QApplication, QFormLayout, QSpinBox

from salam_workbench.checks import _snapshot_sources, source_identity
from salam_workbench.gui_editor_qt import MODEL_FIELDS
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
        "fu_trace_event_limit": 1048576
        if editor.trace_budget_check.isChecked()
        else None,
    }


_BREADTH = {
    "fft": {
        "unit": "double_multiplier",
        "instruction": "fmul",
        "outputs": 1024,
        "runtime_cycles": 6,
        "trace_event_limit": 1048576,
    },
    "stencil3d": {
        "unit": "integer_adder",
        "instruction": "add",
        "outputs": 16384,
        "runtime_cycles": 4,
        "trace_event_limit": 4194304,
    },
}


def _one_row(tree, name):
    rows = [
        tree.topLevelItem(index)
        for index in range(tree.topLevelItemCount())
        if tree.topLevelItem(index).text(0) == name
    ]
    if len(rows) != 1:
        raise ValueError("Expected one live editor row for " + name)
    return rows[0]


def _configure_breadth(editor, workload, require_rebuilds):
    """Edit exposed widgets, including the explicit scalar RegisterBank port."""
    selection = _BREADTH[workload]
    editor.mem_size_edit.setText("2GB")
    if not editor.trace_budget_check.isEnabled():
        raise ValueError("Selected engine has no source-verified trace-budget control")
    editor.trace_budget_check.setChecked(True)
    editor.trace_budget_spin.setValue(selection["trace_event_limit"])
    if editor.hardware_target_combo.findText(workload) < 0:
        raise ValueError("GUI did not expose the requested leaf accelerator")
    editor.hardware_target_combo.setCurrentText(workload)
    unit = _one_row(editor.fu_tree, selection["unit"])
    instruction = _one_row(editor.inst_tree, selection["instruction"])
    unit.setText(1, "1")
    unit.setText(2, "2")
    instruction.setText(1, str(selection["runtime_cycles"]))
    changes = {
        "mem-size": "2GB",
        selection["unit"] + ".cycles": 1,
        selection["unit"] + ".limit": 2,
        selection["instruction"] + ".runtime_cycles": selection["runtime_cycles"],
        "fu_trace_event_limit": selection["trace_event_limit"],
    }
    if require_rebuilds:
        model = _one_row(editor.model_tree, selection["unit"])
        # Synthetic coefficients exercise transport; they are not calibration.
        for name, value in (("area", "7.125"), ("fu_latency", "7")):
            model.setText(MODEL_FIELDS.index(name) + 1, value)
        changes["compiled_profile"] = {
            selection["unit"]: {"area": 7.125, "fu_latency": 7}
        }
    if workload == "stencil3d":
        memories = [
            editor.component_tree.topLevelItem(index)
            for index in range(editor.component_tree.topLevelItemCount())
            if editor.component_tree.topLevelItem(index)
            .data(0, Qt.UserRole)
            .get("type")
            == "memory"
            and editor.component_tree.topLevelItem(index)
            .data(0, Qt.UserRole)
            .get("memory_type")
            == "RegisterBank"
        ]
        if len(memories) != 1:
            raise ValueError("Expected one source RegisterBank in stencil3d")
        memory = memories[0]
        source_ports = memory.data(0, Qt.UserRole).get("ports")
        editor.component_tree.setCurrentItem(memory)
        ports = []
        for index in range(editor.details_layout.rowCount()):
            label = editor.details_layout.itemAt(index, QFormLayout.LabelRole)
            field = editor.details_layout.itemAt(index, QFormLayout.FieldRole)
            if label and field and label.widget().text() == "Ports:":
                ports.append(field.widget())
        if len(ports) != 1 or not isinstance(ports[0], QSpinBox):
            raise ValueError("RegisterBank Ports widget was not exposed")
        ports[0].setValue(1)
        if memory.data(0, Qt.UserRole).get("ports") != 1:
            raise ValueError(
                "Visible RegisterBank Ports edit did not change the component"
            )
        changes["registerbank_ports"] = {
            "name": memory.data(0, Qt.UserRole)["name"],
            "source": source_ports,
            "selected": 1,
            "reason": "Compiled RegisterBank has one scalar private response port",
        }
    return changes


def _assert_breadth_scheduling(result, workload):
    selection = _BREADTH[workload]
    units = {}
    for metric in result.get("metrics", []):
        name = metric.get("name", "")
        if (
            "." + selection["unit"] + "." in name
            and "." + workload + ".invocation-" in name
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
            and values.get("releases") == values.get("grants")
            and values.get("outstanding") == 0
        ):
            return {"name": name, **values}
    raise ValueError(
        "Complete direct scheduling replay did not witness the edited "
        + selection["unit"]
    )


def _read_witness(path):
    path = Path(path).resolve(strict=True)
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path),
        "sha256": file_hash(path),
    }


def _assert_breadth_rebuild(receipt_path, request, workload, *, require_fresh=True):
    """Verify changed generated bytes, a real build and effective defaults.

    Repeat acceptance can verify a fingerprint-checked previously rebuilt
    variant. Fresh acceptance still requires physical generation/build in this
    execution; both modes retain the same source, binary and SimObject checks.
    """
    receipt, gui_source = _read_witness(receipt_path)
    plan = receipt.get("regeneration_plan", {})
    if any(
        plan.get(key) is not True
        for key in (
            "topology_python_and_address_headers",
            "guest_elf_and_accelerator_ir",
            "simulator_rebuild",
        )
    ):
        raise ValueError("GUI did not request the complete regeneration/rebuild path")
    hardware = receipt.get("hardware", {})
    allowed_states = {"built"} if require_fresh else {"built", "reused"}
    if hardware.get("state") not in allowed_states:
        raise ValueError(
            "Fresh hardware rebuild required; cached or reused engines do not establish this acceptance"
            if require_fresh
            else "Verified rebuilt hardware required; the base engine is insufficient"
        )
    generated, generation_source = _read_witness(hardware["generation_receipt"])
    build, build_source = _read_witness(hardware["build_receipt"])
    base = receipt.get("base_build", {})
    if generated.get("state") != "generated" or generated.get("valid") is not True:
        raise ValueError("No valid generated hardware source receipt")
    if generated.get("selection", {}).get("benchmark") != workload:
        raise ValueError("Generated hardware belongs to a different benchmark")
    overrides = request["hardware_profile"].get("fu_overrides", {})
    if generated.get("profile_overrides") != overrides:
        raise ValueError("Compiled generation did not retain the GUI model edits")
    outputs = generated.get("outputs", [])
    engine = Path(hardware["engine_path"]).resolve(strict=True)
    changed = []
    original_engine = Path(base["binary"]["path"]).resolve(strict=True).parents[2]
    for output in outputs:
        relative = Path(output["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe generated output witness")
        installed = engine / relative
        if file_hash(installed) != output["sha256"]:
            raise ValueError(
                "Generated output was not installed exactly: " + str(relative)
            )
        original = original_engine / relative
        if not original.is_file() or file_hash(original) != output["sha256"]:
            changed.append(relative.as_posix())
    if not outputs or not changed:
        raise ValueError("No changed generated hardware bytes were established")
    if (
        build.get("state") != "built"
        or build.get("command", {}).get("return_code") != 0
    ):
        raise ValueError("No successful actual SCons command was recorded")
    if build.get("compiled_source_sha256") == base.get("compiled_source_sha256"):
        raise ValueError("Compiled source identity did not change from the base")
    if build.get("binary", {}).get("sha256") == base.get("binary", {}).get("sha256"):
        raise ValueError("Simulator binary did not change from the base")
    if file_hash(engine / "build/ARM/gem5.opt") != build["binary"]["sha256"]:
        raise ValueError("Rebuilt simulator no longer matches its build receipt")
    pipeline, pipeline_source = _read_witness(receipt["pipeline_receipt"]["path"])
    ini_path = Path(receipt["run_directory"]) / "simulator/config.ini"
    ini = configparser.ConfigParser(interpolation=None, strict=True)
    ini.optionxform = str
    ini.read_string(ini_path.read_text(encoding="utf-8"))
    selection = _BREADTH[workload]
    accelerator = "system." + workload + "_clstr." + workload
    fu = accelerator + ".hw_interface.functional_units." + selection["unit"]
    if ini.getfloat(fu, "area") != 7.125 or ini.getint(fu, "fu_latency") != 7:
        raise ValueError("Compiled GUI model edits did not reach the real SimObject")
    if ini.getint(fu, "limit") != 2 or ini.getint(fu, "cycles") != 1:
        raise ValueError("Runtime GUI FU edits did not reach the real SimObject")
    if (
        ini.getint(accelerator + ".hw_interface.cycle_counts", selection["instruction"])
        != selection["runtime_cycles"]
    ):
        raise ValueError("GUI instruction latency did not reach the real SimObject")
    for name in ("top", workload):
        if (
            ini.getint(
                "system." + workload + "_clstr." + name + ".llvm_interface",
                "fu_trace_event_limit",
            )
            != selection["trace_event_limit"]
        ):
            raise ValueError("GUI trace budget did not reach both actual interfaces")
    if pipeline.get("independent_oracle", {}).get("state") != "passed":
        raise ValueError("Rebuilt pipeline did not independently validate its outputs")
    return {
        "state": "passed",
        "variant_state": hardware["state"],
        "freshly_built_in_this_run": hardware["state"] == "built",
        "fresh_build_required": require_fresh,
        "gui_receipt": gui_source,
        "generation_receipt": generation_source,
        "build_receipt": build_source,
        "pipeline_receipt": pipeline_source,
        "changed_generated_outputs": changed,
        "compiled_source_sha256": build["compiled_source_sha256"],
        "binary_sha256": build["binary"]["sha256"],
        "config_ini": {"path": str(ini_path), "sha256": file_hash(ini_path)},
        "model_claim": "Synthetic area and latency coefficients; transport checked, calibration unverified",
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


def _run_case(
    app,
    window,
    mode,
    benchmark,
    directory,
    timeout,
    input_seed=None,
    require_rebuilds=False,
    verify_rebuilt_profiles=False,
):
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
            workload = benchmark.rsplit("/", 1)[-1]
            if (
                benchmark == "benchmarks/sys_validation/" + workload
                and workload in _BREADTH
            ):
                case["configuration_changes"] = _configure_breadth(
                    window.editor, workload, require_rebuilds or verify_rebuilt_profiles
                )
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
        if mode == "configured" and benchmark in {
            "benchmarks/sys_validation/" + name for name in _BREADTH
        }:
            workload = benchmark.rsplit("/", 1)[-1]
            if transported.get("system", {}).get("mem-size") != "2GB":
                raise ValueError("Edited memory size was not transported")
            case["functional_unit_scheduling"] = _assert_breadth_scheduling(
                result, workload
            )
            if require_rebuilds or verify_rebuilt_profiles:
                case["regeneration_rebuild_witness"] = _assert_breadth_rebuild(
                    result["path"],
                    transported,
                    workload,
                    require_fresh=require_rebuilds,
                )
        if mode == "configured" and input_seed is not None:
            if transported.get("benchmark_input") != {
                "dataset": "seeded",
                "seed": input_seed,
            }:
                raise ValueError("Selected generated inputs did not reach the backend")
            oracle = result.get("independent_oracle", {})
            if oracle.get("state") != "passed":
                raise ValueError(
                    "Results reader did not independently validate every accelerator output"
                )
            workload = benchmark.rsplit("/", 1)[-1]
            if workload in _BREADTH and (
                oracle.get("expected_count") != _BREADTH[workload]["outputs"]
                or oracle.get("compared_count") != _BREADTH[workload]["outputs"]
                or oracle.get("mismatch_count") != 0
            ):
                raise ValueError(
                    "Independent oracle did not compare the complete workload output"
                )
            case["independent_oracle"] = oracle
            if (
                benchmark.endswith("/gemm")
                and window.editor.trace_budget_check.isChecked()
            ):
                for name in ("top", "gemm"):
                    if transported.get("parameters", {}).get(
                        "system.gemm_clstr." + name + ".llvm_interface"
                    ) != {"fu_trace_event_limit": 1048576}:
                        raise ValueError(
                            "GUI trace-budget override did not reach the checked backend"
                        )
        case["rendered_metrics"] = _tree_rows(window.metrics)
        case["rendered_checks"] = _tree_rows(window.checks)
        window.pages.setCurrentIndex(2)
        window.result_tabs.setCurrentIndex(0)
        app.processEvents()
        _screenshot(window, directory / "results.png")
        checks_tab = window.checks
        while checks_tab is not None and window.result_tabs.indexOf(checks_tab) < 0:
            checks_tab = checks_tab.parentWidget()
        if checks_tab is None:
            raise ValueError("Could not locate the actual validation checks tab")
        window.result_tabs.setCurrentWidget(checks_tab)
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
    rebuilds = parser.add_mutually_exclusive_group()
    rebuilds.add_argument(
        "--require-rebuilds",
        action="store_true",
        help="Require fresh GUI-driven FFT/stencil hardware generation and actual simulator rebuilds; cached variants fail this acceptance",
    )
    rebuilds.add_argument(
        "--verify-rebuilt-profiles",
        action="store_true",
        help="Verify GUI-driven FFT/stencil runs using rebuilt profiles; fingerprint-checked cached variants are allowed and reported explicitly",
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.input_seed is not None and not 0 <= args.input_seed <= 2147483647:
        parser.error("--input-seed requires a nonnegative signed 32-bit integer")
    if args.require_rebuilds or args.verify_rebuilt_profiles:
        rebuild_option = (
            "--require-rebuilds"
            if args.require_rebuilds
            else "--verify-rebuilt-profiles"
        )
        if args.input_seed is None:
            parser.error(
                rebuild_option
                + " requires --input-seed for complete independent output checks"
            )
        if any(
            mode != "configured"
            or benchmark
            not in (
                "benchmarks/sys_validation/fft",
                "benchmarks/sys_validation/stencil3d",
            )
            for mode, benchmark in args.cases
        ):
            parser.error(
                rebuild_option + " accepts only configured:fft and configured:stencil3d"
            )
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
        "fresh_hardware_rebuilds_required": args.require_rebuilds,
        "verify_rebuilt_profiles": args.verify_rebuilt_profiles,
        "hardware_acceptance_mode": (
            "fresh_generation_and_rebuild"
            if args.require_rebuilds
            else "verify_rebuilt_profile_including_checked_cache"
            if args.verify_rebuilt_profiles
            else "default"
        ),
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
        case = _run_case(
            app,
            window,
            mode,
            benchmark,
            evidence / name,
            args.timeout,
            args.input_seed,
            args.require_rebuilds,
            args.verify_rebuilt_profiles,
        )
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
