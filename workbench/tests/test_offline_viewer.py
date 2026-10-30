"""Offline evidence and recovered-widget tests; synthetic records are not gem5 runs."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from salam_workbench import report
from salam_workbench.offline_viewer import (
    accelerator_measurement_rows,
    create_window,
    inspection_summary,
    load_legacy_model,
    load_viewer_model,
    main,
)
from salam_workbench.runner import file_hash

DOT = r"""digraph CDFG {
 n0 [label="load\nUID:0\nCycles:3" fillcolor=lightblue];
 n1 [label="mul\nUID:1\nCycles:2" fillcolor=lightgreen];
 n0 -> n1 [color=blue];
}"""
HAS_QT = importlib.util.find_spec("PySide6") is not None
HAS_NETWORKX = importlib.util.find_spec("networkx") is not None


class OfflineViewerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="salam-offline-viewer-fixture-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.a = self.make_run("a")
        self.b = self.make_run("b")
        self.comparison = self.base / "comparison.json"
        self.save_comparison()

    def make_run(self, name):
        directory = self.base / name
        (directory / "simulator").mkdir(parents=True)
        files = {
            "simulator/stats.txt": "---------- Begin Simulation Statistics ----------\n"
            "simTicks 1000\nsimSeconds 0.000001\nsimInsts 64\nhostSeconds 0.1\n"
            "---------- End Simulation Statistics ----------\n",
            "simulator/system.terminal": "Check Passed\n",
            "stdout.txt": "Exiting @ tick 1000 because m5_exit instruction encountered\n",
            "stderr.txt": "",
            "experiment.json": json.dumps(
                {
                    "kind": "synthetic-offline-viewer-fixture",
                    "workload": "gemm",
                }
            ),
        }
        for relative, content in files.items():
            (directory / relative).write_text(content, encoding="utf-8")
        record = {
            "run_id": name,
            "state": "passed",
            "return_code": 0,
            "correctness": {
                "outcome": "passed",
                "passed_markers": 1,
                "failed_markers": 0,
                "guest_output": "simulator/system.terminal",
                "present": True,
            },
            "simulator_exit": {
                "tick": 1000,
                "reason": "m5_exit instruction encountered",
            },
            "simulator_exit_events": [
                {"tick": 1000, "reason": "m5_exit instruction encountered"}
            ],
            "experiment_spec_sha256": file_hash(directory / "experiment.json"),
            "executable": {
                "path": "/fixture/gem5",
                "sha256": "a" * 64,
                "sha256_after_run": "a" * 64,
                "unchanged_after_run": True,
            },
            "inputs": [
                {
                    "path": "/fixture/input",
                    "sha256": "b" * 64,
                    "sha256_after_run": "b" * 64,
                    "unchanged_after_run": True,
                }
            ],
            "argv": [
                "/fixture/gem5",
                "--outdir=" + str(directory / "simulator"),
                "/fixture/config.py",
            ],
            "cwd": "/fixture",
            "environment": {"M5_PATH": "/fixture"},
            "artifacts": [
                {"path": relative, "sha256": file_hash(directory / relative)}
                for relative in files
            ],
        }
        (directory / "run.json").write_text(json.dumps(record), encoding="utf-8")
        return directory

    def add_artifact(self, directory, relative, content):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        record = json.loads((directory / "run.json").read_text())
        record["artifacts"].append({"path": relative, "sha256": file_hash(path)})
        (directory / "run.json").write_text(json.dumps(record))

    def save_comparison(self):
        self.comparison.write_text(
            json.dumps(report.compare_runs(self.a, self.b)), encoding="utf-8"
        )

    def add_current_observability(self):
        if __package__:
            from .test_observability import payload
        else:
            from test_observability import payload
        for directory in (self.a, self.b):
            data = payload()
            self.add_artifact(
                directory,
                "simulator/observability/system.gemm_clstr.gemm.invocation-1.json",
                json.dumps(data),
            )
            path = directory / "experiment.json"
            experiment = json.loads(path.read_text())
            experiment["observability"] = {
                "kind": "salam_observability",
                "schema_version": 1,
                "expected_invocations": {"system.gemm_clstr.gemm": [1]},
            }
            path.write_text(json.dumps(experiment))
            record = json.loads((directory / "run.json").read_text())
            record["experiment_spec_sha256"] = file_hash(path)
            for entry in record["artifacts"]:
                if entry["path"] == "experiment.json":
                    entry["sha256"] = file_hash(path)
            (directory / "run.json").write_text(json.dumps(record))
        self.save_comparison()

    def model(self):
        return load_viewer_model(
            self.a / "run.json", self.b / "run.json", self.comparison
        )

    def test_saved_runs_revalidated_without_launching_any_process(self):
        with mock.patch(
            "subprocess.Popen",
            side_effect=AssertionError("Offline viewer must not launch simulator"),
        ):
            with mock.patch.object(report, "load_run", wraps=report.load_run) as loader:
                model = self.model()
        self.assertGreaterEqual(loader.call_count, 2)
        self.assertTrue(model["evidence_verified"])
        self.assertTrue(model["accepted"])
        self.assertEqual(model["qt_binding"], "PySide6")
        self.assertEqual(
            [run["cdfg"]["status"] for run in model["runs"]],
            ["missing", "missing"],
        )
        self.assertIn("input generation", model["measurement_scope"])
        self.assertEqual(inspection_summary(model)["metric_count"], 4)
        self.assertEqual(
            inspection_summary(model)["runs"][0]["observability"]["status"],
            "unavailable",
        )
        self.assertIsNone(accelerator_measurement_rows(model["runs"][0])[0]["value"])

    def test_tampered_guest_evidence_cannot_hide_behind_saved_passed_summary(
        self,
    ):
        (self.b / "simulator/system.terminal").write_text("Check Failed\n")
        model = self.model()
        self.assertFalse(model["evidence_verified"])
        self.assertFalse(model["accepted"])
        self.assertFalse(model["runs"][1]["correctness_verified"])

    def test_forged_saved_metric_and_outcome_are_rejected(self):
        saved = json.loads(self.comparison.read_text())
        saved["metrics"][0]["a"]["value"] = "999999"
        saved["outcome"] = "different"
        self.comparison.write_text(json.dumps(saved))
        model = self.model()
        self.assertFalse(model["saved_comparison_consistent"])
        self.assertFalse(model["accepted"])
        self.assertEqual(model["comparison"]["metrics"][0]["a"]["value"], "1000")

    def test_swapped_saved_run_identity_is_rejected(self):
        saved = json.loads(self.comparison.read_text())
        saved["runs"].reverse()
        self.comparison.write_text(json.dumps(saved))
        self.assertFalse(self.model()["saved_comparison_consistent"])

    def test_system_topology_dot_is_not_accelerator_cdfg(self):
        self.add_artifact(
            self.a, "simulator/config.dot", "digraph system { cpu -> memory; }"
        )
        self.save_comparison()
        model = self.model()
        self.assertTrue(model["evidence_verified"])
        self.assertEqual(model["runs"][0]["cdfg"]["status"], "missing")
        self.assertEqual(model["runs"][0]["cdfg"]["artifacts"], [])

    @unittest.skipUnless(HAS_NETWORKX, "Recovered parser requires NetworkX")
    def test_actual_recovered_parser_contract_and_hash_gate(self):
        self.add_artifact(self.a, "simulator/cdfg.dot", DOT)
        self.save_comparison()
        graph = self.model()["runs"][0]["cdfg"]
        self.assertEqual(graph["status"], "available")
        self.assertEqual(
            (graph["artifacts"][0]["nodes"], graph["artifacts"][0]["edges"]),
            (2, 1),
        )
        (self.a / "simulator/cdfg.dot").write_text(DOT + "\n// changed")
        model = self.model()
        self.assertFalse(model["evidence_verified"])
        self.assertEqual(
            model["runs"][0]["cdfg"]["artifacts"][0]["status"], "unverified"
        )

    @unittest.skipUnless(HAS_NETWORKX, "Recovered parser requires NetworkX")
    def test_non_instruction_dot_does_not_claim_available_cdfg(self):
        self.add_artifact(self.a, "simulator/cdfg.dot", "digraph other { a -> b; }")
        self.save_comparison()
        graph = self.model()["runs"][0]["cdfg"]
        self.assertEqual(graph["status"], "unavailable")
        self.assertEqual(graph["artifacts"][0]["status"], "unsupported")

    def test_unknown_comparison_kind_does_not_assume_repeat_semantics(self):
        self.comparison.write_text(
            json.dumps({"kind": "unknown", "outcome": "accepted"})
        )
        model = self.model()
        self.assertTrue(all(run["correctness_verified"] for run in model["runs"]))
        self.assertFalse(model["accepted"])
        self.assertFalse(model["saved_comparison_consistent"])

    def test_parameter_comparison_dispatch_preserves_intended_delta_semantics(
        self,
    ):
        # Dispatcher fixture only; actual parameter contracts are variant_report's responsibility.
        fresh = report.compare_runs(self.a, self.b)
        fresh.update(
            kind="gem5_parameter_comparison", outcome="accepted", accepted=True
        )
        fresh.pop("repeatability_accepted")
        fresh["metrics"] = [
            {
                "name": item["name"],
                "a": item["a"],
                "b": item["b"],
                "delta": "0",
                "percent_change": "0",
                "domain": "simulated",
            }
            for item in fresh["metrics"]
        ]
        self.comparison.write_text(json.dumps(fresh))
        module = types.ModuleType("salam_workbench.variant_report")
        module.compare_variant_runs = mock.Mock(return_value=fresh)
        with mock.patch.dict(sys.modules, {module.__name__: module}):
            model = self.model()
        module.compare_variant_runs.assert_called_once_with(
            self.a.resolve(), self.b.resolve()
        )
        self.assertTrue(model["accepted"])
        self.assertEqual(model["comparison"]["kind"], "gem5_parameter_comparison")

    @unittest.skipUnless(HAS_QT, "PySide6 not installed in this interpreter")
    def test_offscreen_window_displays_verified_runs_and_missing_cdfg(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QTabWidget

        app = QApplication.instance() or QApplication([])
        window = create_window(self.model())
        self.addCleanup(window.close)
        window.show()
        app.processEvents()
        self.assertEqual(
            window.findChild(QLabel, "evidence-status").text(),
            "Saved evidence verified",
        )
        self.assertEqual(window.findChild(QTabWidget, "evidence-tabs").count(), 7)
        self.assertEqual(window.findChild(QTableWidget, "metric-table").rowCount(), 4)
        self.assertFalse(window.grab().isNull())
        window.close()

    def test_observability_values_require_run_contract_and_hash_verification(
        self,
    ):
        self.add_current_observability()
        model = self.model()
        self.assertTrue(model["evidence_verified"], model["issues"])
        rows = {
            entry["metric"]: entry
            for entry in accelerator_measurement_rows(model["runs"][0])
        }
        self.assertEqual(rows["memory.reads.completed"]["value"], 2)
        self.assertEqual(rows["memory.reads.completed"]["unit"], "logical_request")
        self.assertEqual(rows["memory.reads.latency_ticks.mean"]["value"], "4")
        self.assertIsNone(rows["power"]["value"])
        self.assertEqual(rows["power"]["availability"], "unavailable")
        self.assertIn("characterized", rows["power"]["scope"])
        summary = inspection_summary(model)["runs"][0]["observability"]
        self.assertEqual(summary["identities"][0]["logical_reads_completed"], 2)
        self.assertTrue(summary["identities"][0]["measurements_verified"])
        path = (
            self.a / "simulator/observability/system.gemm_clstr.gemm.invocation-1.json"
        )
        path.write_text(path.read_text() + "\n")
        model = self.model()
        self.assertFalse(model["evidence_verified"])
        rows = accelerator_measurement_rows(model["runs"][0])
        self.assertTrue(all(entry["value"] is None for entry in rows))
        self.assertTrue(all(not entry["verified"] for entry in rows))
        self.assertEqual(
            next(
                entry for entry in rows if entry["metric"] == "memory.reads.completed"
            )["availability"],
            "unverified",
        )
        self.assertIsNone(
            inspection_summary(model)["runs"][0]["observability"]["identities"][0][
                "logical_reads_completed"
            ]
        )

    def test_legacy_mode_loads_without_run_paths_and_never_validates_runtime_values(
        self,
    ):
        path = self.base / "old.json"
        path.write_text(
            json.dumps(
                {
                    "salam_stats": {
                        "version": "3.0",
                        "memory_access": {"cache_hits": 0},
                    }
                }
            )
        )
        model = load_legacy_model(path, "legacy_flat_v3")
        self.assertFalse(model["evidence_verified"])
        self.assertFalse(model["accepted"])
        self.assertEqual(model["legacy"]["metrics"]["cache_hits"]["raw_value"], 0)
        self.assertIsNone(model["legacy"]["metrics"]["cache_hits"]["value"])
        self.assertEqual(
            model["legacy"]["metrics"]["spm_reads"]["availability"], "missing"
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch(
            "salam_workbench.offline_viewer.create_window",
            side_effect=AssertionError("Inspect must not import Qt"),
        ):
            code = main(
                [
                    "--legacy-stats",
                    str(path),
                    "--legacy-format",
                    "legacy_flat_v3",
                    "--inspect",
                ]
            )
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["measurements_validated"])
        self.assertEqual(
            inspection_summary(model)["provenance"]["sha256"], file_hash(path)
        )

    @unittest.skipUnless(HAS_QT, "PySide6 not installed in this interpreter")
    def test_offscreen_measurement_columns_and_legacy_unknown_values(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

        app = QApplication.instance() or QApplication([])
        self.add_current_observability()
        window = create_window(self.model())
        self.addCleanup(window.close)
        window.show()
        app.processEvents()
        table = window.findChild(QTableWidget, "observability-table")
        self.assertEqual(
            [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())],
            [
                "Run",
                "Accelerator",
                "Invocation",
                "Metric",
                "Value",
                "Unit",
                "Availability",
                "Scope / reason",
                "Source field",
            ],
        )
        power_row = next(
            row
            for row in range(table.rowCount())
            if table.item(row, 3).text() == "power"
        )
        self.assertEqual(table.item(power_row, 4).text(), "unknown")
        self.assertEqual(table.item(power_row, 6).text(), "unavailable")
        self.assertFalse(window.grab().isNull())
        window.close()
        path = self.base / "legacy.json"
        path.write_text(
            json.dumps(
                {
                    "salam_stats": {
                        "version": "3.0",
                        "memory_access": {"cache_hits": 7},
                    }
                }
            )
        )
        legacy_window = create_window(load_legacy_model(path, "legacy_flat_v3"))
        self.addCleanup(legacy_window.close)
        legacy_window.show()
        app.processEvents()
        self.assertIn(
            "unvalidated",
            legacy_window.findChild(QLabel, "legacy-status").text(),
        )
        legacy_table = legacy_window.findChild(QTableWidget, "legacy-metric-table")
        self.assertTrue(
            all(
                legacy_table.item(row, 2).text() == "unknown"
                for row in range(legacy_table.rowCount())
            )
        )
        self.assertFalse(legacy_window.grab().isNull())
        legacy_window.close()

    @unittest.skipUnless(HAS_QT and HAS_NETWORKX, "PySide6 and NetworkX required")
    def test_offscreen_recovered_widget_renders_parsed_instruction_graph(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication

        from salam_workbench.vendor.salam_gui.widgets.cdfg_viewer import CDFGViewer

        self.add_artifact(self.a, "simulator/cdfg.dot", DOT)
        self.save_comparison()
        app = QApplication.instance() or QApplication([])
        window = create_window(self.model())
        self.addCleanup(window.close)
        window.show()
        app.processEvents()
        viewer = window.findChild(CDFGViewer)
        self.assertIsNotNone(viewer)
        self.assertEqual(len(viewer.node_items), 2)
        self.assertEqual(viewer.graph.nodes[1].opcode, "mul")
        self.assertFalse(window.grab().isNull())
        window.close()


if __name__ == "__main__":
    unittest.main()
