"""Desktop workflow checks; fixture interactions do not claim simulator runs."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QProcess, QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGroupBox,
    QPushButton,
    QTextEdit,
    QTreeWidgetItem,
    QVBoxLayout,
)

from salam_workbench.workbench_window import WorkbenchWindow

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT / "workspace.json"
ENGINE = (
    Path(
        json.loads(WORKSPACE.read_text(encoding="utf-8-sig"))["configuration_engine"][
            "path"
        ]
    )
    if WORKSPACE.is_file()
    else PROJECT / "unbound-engine"
)
GUI_SOURCE = ENGINE / "gem5-SALAM-gui/src"


def _catalog_entry(name, *, suite="sys_validation", available=True):
    key = "benchmarks/" + suite + "/" + name
    return {
        "key": key,
        "benchmark": key,
        "suite": suite,
        "name": name,
        "title": name.upper(),
        "can_configure": available,
        "can_run": available,
        "warnings": [] if available else ["Source inputs are missing"],
        "description": "Test source configuration",
    }


class _LightweightEditor(QDialog):
    """Only the editor-facing UI contract; no success or simulator stub."""

    def __init__(self, engine, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.benchmark_combo = QComboBox()
        for name in ("gemm", "bfs", "md_grid"):
            self.benchmark_combo.addItem(name, name)
        self.bench_dir_combo = QComboBox()
        self.bench_dir_combo.addItems(
            ["benchmarks/sys_validation", "benchmarks/legacy"]
        )
        layout.addWidget(self.benchmark_combo)
        layout.addWidget(self.bench_dir_combo)
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        self.validation_output = QTextEdit()
        group_layout.addWidget(self.validation_output)
        layout.addWidget(group)
        self.validate_btn = QPushButton("Validate")
        self.generate_btn = QPushButton("Generate")
        self.save_btn = QPushButton("Save")
        self.load_btn = QPushButton("Load")
        for button in (
            self.validate_btn,
            self.generate_btn,
            self.save_btn,
            self.load_btn,
        ):
            layout.addWidget(button)
        self.loaded_benchmark = None
        self.launch_count = 0

    def on_benchmark_changed(self, text):
        self.loaded_benchmark = (
            self.bench_dir_combo.currentText()
            + "/"
            + self.benchmark_combo.currentData()
        )

    def generate_files(self):
        self.launch_count += 1
        self.validation_output.setPlainText(
            "Backend launch requested; no passing result exists."
        )
        self._workbench_listener("started", {"request": {}})

    def _make_request(self):
        return {"benchmark": self.loaded_benchmark}


class _EmptyProcessOutput:
    def readAllStandardOutput(self):
        return b""

    def readAllStandardError(self):
        return b""


class WorkbenchWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name).resolve()
        self.engine = self.project / "engine"
        self.engine.mkdir()
        (self.project / "evidence").mkdir()
        (self.project / "runs").mkdir()
        self.settings = QSettings(
            str(self.project / "preferences.ini"), QSettings.IniFormat
        )
        self.window = WorkbenchWindow(
            self.project,
            self.engine,
            "Ubuntu-20.04",
            _LightweightEditor,
            settings=self.settings,
            auto_discover=False,
        )
        self.window.catalog = [
            _catalog_entry("gemm"),
            _catalog_entry("bfs"),
            _catalog_entry("md_grid"),
        ]
        self.window._show_catalog()

    def tearDown(self):
        self.window._set_busy(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _benchmark_item(self, name):
        group = self.window.benchmark_tree.topLevelItem(0)
        return next(
            group.child(i)
            for i in range(group.childCount())
            if group.child(i).data(0, Qt.UserRole)["name"] == name
        )

    def test_selection_and_reference_mode_have_distinct_authority(self):
        self.window.benchmark_tree.setCurrentItem(self._benchmark_item("bfs"))
        self.assertEqual(
            self.window.selected_benchmark["key"], "benchmarks/sys_validation/bfs"
        )
        self.assertEqual(
            self.window.editor.loaded_benchmark, "benchmarks/sys_validation/bfs"
        )
        self.window.mode_combo.setCurrentIndex(1)
        self.assertFalse(self.window.editor.isEnabled())
        self.assertTrue(self.window.run_btn.isEnabled())
        self.assertIn("editor settings are not applied", self.window.mode_note.text())
        self.window.benchmark_tree.setCurrentItem(self._benchmark_item("md_grid"))
        self.assertFalse(self.window.run_btn.isEnabled())
        self.assertIn("No verified reference adapter", self.window.mode_note.text())

    def test_second_launch_and_source_changes_are_locked_during_job(self):
        self.window.start_run()
        self.window.start_run()
        self.assertEqual(self.window.editor.launch_count, 1)
        self.assertTrue(self.window._busy)
        self.assertFalse(self.window.run_btn.isEnabled())
        self.assertFalse(self.window.benchmark_tree.isEnabled())
        self.assertFalse(self.window.mode_combo.isEnabled())
        self.assertFalse(self.window.editor.isEnabled())
        self.assertIn("Running", self.window.run_status.text())
        self.assertNotIn("Completed", self.window.run_status.text())
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())

    def test_unavailable_selection_cannot_check_or_save_the_previous_source(self):
        self.window.catalog.append(_catalog_entry("unavailable", available=False))
        self.window._show_catalog()
        self.window.benchmark_tree.setCurrentItem(self._benchmark_item("unavailable"))
        with self.assertRaisesRegex(ValueError, "no editable configuration"):
            self.window._current_request()
        with patch("salam_workbench.workbench_window.validate_request") as validate:
            self.window.check_settings()
            validate.assert_not_called()
        self.assertIn("Settings rejected", self.window.run_log.toPlainText())
        with patch("salam_workbench.workbench_window.QMessageBox.warning"), patch(
            "salam_workbench.workbench_window.QFileDialog.getSaveFileName"
        ) as save_dialog:
            self.window.save_preset()
            save_dialog.assert_not_called()

    def test_missing_editor_selection_does_not_run_the_previous_benchmark(self):
        self.window.catalog.append(_catalog_entry("not_in_editor"))
        self.window._show_catalog()
        self.window.benchmark_tree.setCurrentItem(self._benchmark_item("not_in_editor"))
        self.assertEqual(
            self.window.editor.loaded_benchmark, "benchmarks/sys_validation/gemm"
        )
        self.assertFalse(self.window.run_btn.isEnabled())
        self.window.start_run()
        self.assertEqual(self.window.editor.launch_count, 0)
        with self.assertRaises(ValueError):
            self.window._current_request()

    def test_stale_evidence_failure_does_not_replace_new_selection(self):
        self.window._load_generation = 2
        self.window.result_heading.setText("Current run detail")
        self.window._data_failed("run:1", "Old missing receipt")
        self.assertEqual(self.window.result_heading.text(), "Current run detail")
        self.window._data_failed("run:2", "Current missing receipt")
        self.assertEqual(
            self.window.result_heading.text(), "Could not inspect this run"
        )

    def test_nominal_passing_wrapper_without_raw_run_is_rejected(self):
        directory = self.project / "evidence/nominal-only"
        directory.mkdir()
        wrapper = {
            "state": "passed",
            "benchmark": "benchmarks/sys_validation/gemm",
            "editor_form_applied": True,
            "simulation_requested": True,
            "pipeline_state": "passed",
            "effective_witness": {"state": "passed", "checks": 999},
            "evidence_directory": str(directory),
        }
        (directory / "gui-execution.json").write_text(
            json.dumps(wrapper), encoding="utf-8"
        )
        self.window.editor._gui_request = {
            "benchmark": "benchmarks/sys_validation/gemm"
        }
        work = []
        with patch.object(
            self.window,
            "_task",
            side_effect=lambda name, function: work.append((name, function)),
        ):
            self.window._candidate_finish("passed", str(directory), [])
        self.assertTrue(self.window._busy)
        self.assertEqual(len(work), 1)
        name, function = work[0]
        result = function()
        self.assertEqual(result["state"], "failed")
        with patch.object(self.window, "refresh_history"), patch.object(
            self.window, "_inspect_run"
        ):
            self.window._data_ready(name, result)
        self.assertEqual(self.window._last_completed_state, "failed")
        self.assertFalse(self.window._busy)

    def test_reader_queue_keeps_latest_selection_with_two_worker_bound(self):
        class HeldTask:
            def __init__(self, name):
                self.name = name

        original_tasks = self.window._tasks
        held = HeldTask("run:1")
        self.window._tasks = [held, HeldTask("history")]
        started = []

        def start(name, function):
            started.append(name)
            self.window._tasks.append(HeldTask(name))

        try:
            with patch.object(self.window, "_start_task", side_effect=start):
                for generation in range(2, 21):
                    self.window._task("run:" + str(generation), lambda: None)
                self.window._task("artifact", lambda: None)
                self.assertEqual(started, [])
                self.window._task_finished(held)
            self.assertEqual(started, ["run:20"])
            self.assertEqual(len(self.window._tasks), 2)
            self.assertIn("artifact", self.window._task_queue)
        finally:
            self.window._tasks = original_tasks
            self.window._task_queue.clear()

    def test_passing_process_summary_does_not_override_failed_durable_receipt(self):
        directory = self.project / "evidence/reference-failed"
        directory.mkdir()
        record = {"state": "failed", "benchmark": "benchmarks/sys_validation/gemm"}
        # Both adapter names are retained here so this test asserts the semantic
        # boundary while the production session format evolves.
        for filename in ("workbench-reference.json", "reference-session.json"):
            (directory / filename).write_text(json.dumps(record), encoding="utf-8")
        self.window._reference_process = _EmptyProcessOutput()
        self.window._reference_summary = {
            "state": "passed",
            "evidence_directory": str(directory),
        }
        self.window._set_busy(True)
        with patch.object(self.window, "refresh_history"), patch.object(
            self.window, "_inspect_run"
        ):
            self.window._reference_finished(0, QProcess.NormalExit)
        self.assertFalse(self.window._busy)
        self.assertEqual(self.window.run_status.text(), "Completed · failed")
        self.assertIn("did not pass", self.window.run_log.toPlainText())

    def test_failed_launch_stays_failed_and_unlocks_controls(self):
        self.window._set_busy(True)
        with patch.object(self.window, "refresh_history"):
            self.window._editor_event(
                "failed_to_start", {"error": "Simulator executable missing"}
            )
        self.assertFalse(self.window._busy)
        self.assertEqual(self.window.run_status.text(), "Completed · failed")
        self.assertTrue(self.window.run_btn.isEnabled())
        self.assertNotIn("passed", self.window.run_status.text())

    def test_metrics_preserve_missing_values_scope_and_failed_checks(self):
        self.window._show_run(
            {
                "benchmark": "benchmarks/sys_validation/gemm",
                "state": "failed",
                "metrics": [
                    {
                        "name": "SALAM cycles",
                        "value": 1054,
                        "unit": "cycle",
                        "scope": "accelerator invocation",
                        "status": "replayed",
                        "source": "salam.json",
                    },
                    {
                        "name": "Power",
                        "value": None,
                        "unit": "mW",
                        "scope": "model estimate",
                        "status": "unavailable",
                        "source": None,
                    },
                ],
                "checks": [
                    {
                        "name": "Numerical oracle",
                        "status": "failed",
                        "detail": "Output differs from reference",
                        "source": "oracle.json",
                    }
                ],
                "warnings": ["Whole-guest cycles are not accelerator timing"],
            }
        )
        self.assertIn("recorded failed", self.window.result_heading.text())
        self.assertEqual(
            self.window.metrics.topLevelItem(0).text(3), "accelerator invocation"
        )
        missing = self.window.metrics.topLevelItem(1)
        self.assertEqual(missing.text(1), "Unavailable")
        self.assertNotEqual(missing.text(1), "0")
        self.assertEqual(missing.text(3), "model estimate")
        self.assertEqual(self.window.checks.topLevelItem(0).text(1), "failed")
        self.window.metric_search.setText("power")
        self.assertTrue(self.window.metrics.topLevelItem(0).isHidden())
        self.assertFalse(missing.isHidden())

    def test_history_filter_retains_failed_and_unknown_results(self):
        self.window._show_history(
            [
                {
                    "benchmark": "gemm",
                    "state": "failed",
                    "started_at": "2026-10-30",
                    "run_id": "wrong-output",
                    "path": str(self.project / "evidence/a"),
                },
                {
                    "benchmark": "bfs",
                    "state": "unknown",
                    "run_id": "unfinished",
                    "path": str(self.project / "evidence/b"),
                },
            ]
        )
        self.assertEqual(self.window.history.topLevelItemCount(), 2)
        self.window.history_search.setText("failed")
        self.assertFalse(self.window.history.topLevelItem(0).isHidden())
        self.assertTrue(self.window.history.topLevelItem(1).isHidden())
        self.window.history_search.setText("unfinished")
        self.assertTrue(self.window.history.topLevelItem(0).isHidden())
        self.assertFalse(self.window.history.topLevelItem(1).isHidden())

    def test_artifact_reader_rejects_outside_path_even_if_row_claims_available(self):
        outside = self.project / "outside.txt"
        outside.write_text("UNRELATED CONTENT MUST NOT BE READ", encoding="utf-8")
        item = QTreeWidgetItem()
        item.setData(
            0,
            Qt.UserRole,
            {"name": "forged", "status": "available", "path": str(outside)},
        )
        queued = []
        with patch.object(
            self.window,
            "_task",
            side_effect=lambda name, function: queued.append(function),
        ):
            self.window._artifact_changed(item, None)
        self.assertEqual(len(queued), 1)
        with self.assertRaises(ValueError):
            queued[0]()
        self.assertNotIn(
            "UNRELATED CONTENT", self.window.artifact_preview.toPlainText()
        )

    def test_run_directory_artifact_is_available_in_the_same_inspector(self):
        log = self.project / "runs/fixed-run/simout.txt"
        log.parent.mkdir()
        log.write_text("Simulation output from a retained run", encoding="utf-8")
        item = QTreeWidgetItem()
        item.setData(
            0,
            Qt.UserRole,
            {"name": "simout.txt", "status": "available", "path": str(log)},
        )
        queued = []
        with patch.object(
            self.window,
            "_task",
            side_effect=lambda name, function: queued.append(function),
        ):
            self.window._artifact_changed(item, None)
        self.assertEqual(len(queued), 1)
        path, text = queued[0]()
        self.assertEqual(path, str(log))
        self.assertEqual(text, "Simulation output from a retained run")

    def test_comparison_does_not_coalesce_different_metric_scopes(self):
        self.window._show_comparison(
            {
                "run_id": "a",
                "metrics": [
                    {
                        "name": "cycles",
                        "value": 1054,
                        "unit": "cycle",
                        "scope": "accelerator",
                    }
                ],
            },
            {
                "run_id": "b",
                "metrics": [
                    {
                        "name": "cycles",
                        "value": 9999,
                        "unit": "cycle",
                        "scope": "whole guest",
                    }
                ],
            },
        )
        self.assertEqual(self.window.comparison.topLevelItemCount(), 2)
        for index in range(2):
            row = self.window.comparison.topLevelItem(index)
            self.assertIn("Unavailable", (row.text(1), row.text(2)))
        self.assertIn(
            "do not establish repeatability or speedup", self.window.result_scope.text()
        )


@unittest.skipUnless(GUI_SOURCE.is_dir(), "independent WSL GUI unavailable")
class WorkbenchWindowRealEditorTests(unittest.TestCase):
    """The actual recovered editor and live request validation, without simulation."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        os.environ["SALAM_WORKBENCH_ROOT"] = str(PROJECT)
        if str(GUI_SOURCE) not in sys.path:
            sys.path.insert(0, str(GUI_SOURCE))
        from gui.config_generator import ConfigGeneratorDialog

        cls.dialog_class = ConfigGeneratorDialog

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = QSettings(
            str(Path(self.temporary.name) / "preferences.ini"), QSettings.IniFormat
        )
        self.window = WorkbenchWindow(
            PROJECT,
            ENGINE,
            "Ubuntu-20.04",
            self.dialog_class,
            settings=self.settings,
            auto_discover=False,
        )
        self.window.catalog = [_catalog_entry("gemm")]
        self.window._show_catalog()

    def tearDown(self):
        self.window._set_busy(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _fu_row(self, name):
        tree = self.window.editor.fu_tree
        return next(
            tree.topLevelItem(i)
            for i in range(tree.topLevelItemCount())
            if tree.topLevelItem(i).text(0) == name
        )

    def test_small_window_system_fields_do_not_overlap_and_remain_reachable(self):
        # The real editor is sourced from the existing engine or the source-only
        # CI fixture. No fake controls or simulator output participate here.
        editor = self.window.editor
        before = editor._make_request()
        self.window.resize(1060, 720)
        self.window.pages.setCurrentIndex(0)
        editor.tabs.setCurrentIndex(0)
        self.window.show()
        for _ in range(3):
            self.app.processEvents()
        self.assertLessEqual(
            self.window.width(),
            1060,
            "Child minimum widths forced the workbench wider than requested",
        )
        self.assertLessEqual(
            self.window.height(),
            720,
            "Child minimum heights forced the workbench taller than requested",
        )
        scroll = self.window._basic_scroll
        content = scroll.widget()
        fields = [
            editor.mem_size_edit,
            editor.mem_type_edit,
            editor.cpu_clock_edit,
            editor.sys_clock_edit,
        ]
        positions = [field.mapToGlobal(QPoint(0, 0)) for field in fields]
        for index in range(len(fields) - 1):
            bottom = positions[index].y() + fields[index].height()
            self.assertGreaterEqual(
                positions[index + 1].y(),
                bottom,
                "System controls overlap at the minimum supported window size",
            )
        for field in fields:
            with self.subTest(field=field.objectName() or field.text()):
                position = field.mapTo(content, QPoint(0, 0))
                self.assertGreaterEqual(position.y(), 0)
                self.assertLessEqual(position.y() + field.height(), content.height())
                scroll.ensureWidgetVisible(field, 8, 8)
                self.app.processEvents()
                viewport_position = field.mapTo(scroll.viewport(), QPoint(0, 0))
                self.assertGreaterEqual(viewport_position.y(), 0)
                self.assertLessEqual(
                    viewport_position.y() + field.height(),
                    scroll.viewport().height(),
                    "The system control cannot be reached by scrolling",
                )
        after = editor._make_request()
        for key in (
            "configuration_documents",
            "system",
            "parameters",
            "hardware_profile",
            "base_address",
        ):
            self.assertEqual(
                after[key], before[key], "Resizing or scrolling changed the run request"
            )

    def test_preset_roundtrip_restores_live_system_and_fu_controls(self):
        editor = self.window.editor
        editor.mem_size_edit.setText("2GB")
        editor.cpu_clock_edit.setText("1GHz")
        row = self._fu_row("integer_multiplier")
        row.setText(1, "3")
        row.setText(2, "0")
        request = editor._make_request()
        editor.mem_size_edit.setText("4GB")
        editor.cpu_clock_edit.clear()
        row.setText(1, "1")
        self.window.restore_preset(deepcopy(request))
        restored = editor._make_request()
        self.assertEqual(restored["system"]["mem-size"], "2GB")
        self.assertEqual(restored["system"]["cpu-clock"], "1GHz")
        self.assertEqual(self._fu_row("integer_multiplier").text(1), "3")
        for key in (
            "configuration_documents",
            "system",
            "parameters",
            "hardware_profile",
            "base_address",
        ):
            self.assertEqual(restored[key], request[key])

    def test_library_selection_loads_distinct_sources_in_the_actual_editor(self):
        # Make a tiny source-only engine so this works in CI, where only the
        # GEMM fixture is guaranteed. These are editor fixtures, not BFS data.
        project = Path(self.temporary.name).resolve()
        engine = project / "source-only-engine"
        for relative in (
            "configs/SALAM/HWAccConfig.py",
            "src/hwacc/FunctionalUnits.py",
        ):
            destination = engine / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ENGINE / relative, destination)
        original = deepcopy(self.window.editor._base_document)
        for name, cluster in (("gemm", "fixture_gemm"), ("second", "fixture_second")):
            document = deepcopy(original)
            next(entry for entry in document["acc_cluster"] if "Name" in entry)[
                "Name"
            ] = cluster
            directory = engine / "benchmarks/sys_validation" / name
            directory.mkdir(parents=True)
            (directory / "config.yml").write_text(
                yaml.safe_dump(document), encoding="utf-8"
            )
            (
                directory
                / "configs/hw_interface/functional_units/40nm_model/5ns/default_profile"
            ).mkdir(parents=True)
        settings = QSettings(str(project / "selection.ini"), QSettings.IniFormat)
        window = WorkbenchWindow(
            project,
            engine,
            "Ubuntu-20.04",
            self.dialog_class,
            settings=settings,
            auto_discover=False,
        )
        try:
            window.catalog = [_catalog_entry("gemm"), _catalog_entry("second")]
            window._show_catalog()
            first_hash = window.editor._source_sha256
            group = window.benchmark_tree.topLevelItem(0)
            window.benchmark_tree.setCurrentItem(group.child(1))
            self.assertEqual(window.selected_benchmark["name"], "second")
            self.assertEqual(window.editor.benchmark_combo.currentData(), "second")
            self.assertEqual(
                window.editor._source_config_relative,
                "benchmarks/sys_validation/second/config.yml",
            )
            self.assertEqual(window.editor.cluster_name_edit.text(), "fixture_second")
            self.assertNotEqual(window.editor._source_sha256, first_hash)
        finally:
            window.close()
            window.deleteLater()

    def test_stale_preset_source_hash_is_rejected_before_controls_change(self):
        editor = self.window.editor
        request = editor._make_request()
        request["provenance"]["source_config"]["sha256"] = "0" * 64
        memory_before = editor.mem_size_edit.text()
        with self.assertRaisesRegex(ValueError, "source YAML changed"):
            self.window.restore_preset(request)
        self.assertEqual(editor.mem_size_edit.text(), memory_before)

    def test_active_job_rejects_preset_without_mutating_the_editor(self):
        editor = self.window.editor
        request = editor._make_request()
        self.window._set_busy(True)
        with self.assertRaisesRegex(ValueError, "active run"):
            self.window.restore_preset(request)
        self.assertEqual(editor.mem_size_edit.text(), request["system"]["mem-size"])


if __name__ == "__main__":
    unittest.main()
