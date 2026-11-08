# SPDX-License-Identifier: BSD-3-Clause
"""Timeline exports require bound evidence and preserve accepted raw files."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench.runner import file_hash
from salam_workbench.timeline_export import eligible_traces, export_selected_trace


class TimelineExportTests(unittest.TestCase):
    def test_only_hash_bound_fu_artifacts_are_candidates(self):
        base = {
            "name": "fu-scheduling-system.a.invocation-1.json",
            "path": "/evidence/trace.json",
            "sha256": "a" * 64,
            "status": "hash_verified",
        }
        for field, value in (
            ("status", "present_unbound"),
            ("status", "hash_mismatch"),
            ("sha256", None),
            ("name", "stats.txt"),
        ):
            with self.subTest(field=field, value=value):
                item = dict(base, **{field: value})
                self.assertEqual(eligible_traces({"artifacts": [item]}), [])
        self.assertEqual(eligible_traces({"artifacts": [base]}), [base])

    def _fixture(self, project):
        evidence = project / "evidence"
        evidence.mkdir()
        receipt = evidence / "gui-execution.json"
        receipt.write_text("{}")
        trace = evidence / "fu-scheduling-system.a.invocation-1.json"
        trace.write_text('{"fixture":true}')
        return trace, {
            "path": str(receipt),
            "state": "failed",
            "validation_state": "numerical_mismatch",
            "provenance": {"receipt_sha256": file_hash(receipt)},
            "artifacts": [
                {
                    "name": trace.name,
                    "path": str(trace),
                    "status": "hash_verified",
                    "sha256": file_hash(trace),
                }
            ],
        }

    def test_changed_trace_is_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            trace, result = self._fixture(project)
            trace.write_text("{}")
            with self.assertRaisesRegex(ValueError, "changed"):
                export_selected_trace(result, str(trace), project)
            self.assertFalse((project / "evidence/execution-timelines").exists())

    def test_derived_export_keeps_raw_evidence_and_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            trace, result = self._fixture(project)
            digest = file_hash(trace)

            def write_html(source, output, **kwargs):
                self.assertEqual(kwargs["expected_sha256"], digest)
                output.write_text("<html>fixture</html>")
                return {"validation": {"scope": "FU scheduling trace only"}}

            with patch(
                "visualizer.export_salam_visualizer.export_trace",
                side_effect=write_html,
            ):
                first = export_selected_trace(result, str(trace), project)
                second = export_selected_trace(result, str(trace), project)
            self.assertNotEqual(first["html"], second["html"])
            self.assertEqual(file_hash(trace), digest)
            self.assertEqual(first["recorded_run_state"], "failed")
            self.assertIn("not a numerical", first["scope"])
            stored = json.loads(
                Path(first["html"]).with_name("export.json").read_text()
            )
            self.assertEqual(stored["source_trace_sha256"], digest)

    def test_export_failure_is_preserved_without_a_success_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            trace, result = self._fixture(project)
            with patch(
                "visualizer.export_salam_visualizer.export_trace",
                side_effect=ValueError("truncated"),
            ):
                with self.assertRaisesRegex(ValueError, "truncated"):
                    export_selected_trace(result, str(trace), project)
            records = list(
                (project / "evidence/execution-timelines").glob("*/export.json")
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0].read_text())["state"], "failed")
            self.assertFalse(records[0].with_name("timeline.html").exists())

    def test_unbound_trace_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            trace, result = self._fixture(project)
            with self.assertRaisesRegex(ValueError, "hash-verified"):
                export_selected_trace(result, "/tmp/unbound.json", project)

    def test_changed_receipt_is_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            trace, result = self._fixture(project)
            Path(result["path"]).write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                export_selected_trace(result, str(trace), project)
            self.assertFalse((project / "evidence/execution-timelines").exists())

    def test_receipt_change_during_export_preserves_a_failed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            trace, result = self._fixture(project)

            def mutate_receipt(source, output, **kwargs):
                output.write_text("<html>derived</html>")
                Path(result["path"]).write_text('{"changed":true}')
                return {"validation": {"state": "passed"}}

            with patch(
                "visualizer.export_salam_visualizer.export_trace",
                side_effect=mutate_receipt,
            ):
                with self.assertRaisesRegex(ValueError, "receipt changed during"):
                    export_selected_trace(result, str(trace), project)
            records = list(
                (project / "evidence/execution-timelines").glob("*/export.json")
            )
            self.assertEqual(json.loads(records[0].read_text())["state"], "failed")
