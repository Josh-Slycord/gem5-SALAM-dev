"""Qt interaction and local-evidence safety for the conceptual process view."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from salam_workbench.process_view import (
    ProcessPanel,
    preview_artifact,
    related_artifacts,
)


class ProcessViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        evidence = self.project / "evidence"
        evidence.mkdir()
        path = evidence / "stats.txt"
        data = b"simTicks 123\n"
        path.write_bytes(data)
        self.item = {
            "name": "stats.txt",
            "path": str(path),
            "status": "hash_verified",
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def test_selected_stage_updates_details_and_reads_the_actual_verified_run_file(
        self,
    ):
        panel = ProcessPanel(self.project)
        panel.show_run(
            {
                "benchmark": "benchmarks/sys_validation/gemm",
                "state": "passed",
                "artifacts": [self.item],
            }
        )
        panel.buttons[6].click()
        self.assertEqual(panel.heading.text(), "Inspect + compare")
        self.assertEqual(panel.artifacts.count(), 1)
        panel.artifacts.setCurrentRow(0)
        self.assertIn("simTicks 123", panel.preview.toPlainText())
        self.assertIn("filename alone does not establish", panel.run_summary.text())
        panel.close()

    def test_tampered_file_is_not_shown_as_verified(self):
        Path(self.item["path"]).write_text("different bytes")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            preview_artifact(self.project, self.item)

    def test_missing_or_unverified_artifacts_remain_unavailable(self):
        altered = dict(self.item, status="present_unbound")
        self.assertEqual(related_artifacts({"artifacts": [altered]}, 6), [])
        panel = ProcessPanel(self.project)
        panel.show_run({"artifacts": [altered]})
        panel.select_stage(6)
        self.assertEqual(panel.artifacts.count(), 0)
        panel.show_run(None)
        self.assertIn("Select a recorded run", panel.run_summary.text())
        panel.close()

    def test_escape_and_symlink_do_not_open_as_evidence(self):
        outside = self.project / "stats.txt"
        outside.write_text("secret")
        with self.assertRaisesRegex(ValueError, "outside"):
            preview_artifact(self.project, dict(self.item, path=str(outside)))
        link = self.project / "evidence" / "link.txt"
        link.symlink_to(outside)
        with self.assertRaises(ValueError):
            preview_artifact(self.project, dict(self.item, path=str(link)))

    def test_hardware_selection_precedes_workload_compilation(self):
        panel = ProcessPanel(self.project)
        self.assertEqual(len(panel.buttons), 7)
        panel.buttons[2].click()
        self.assertIn("reuse", panel.description.text())
        self.assertIn("rebuild", panel.description.text())
        self.assertEqual(panel.buttons[3].accessibleName(), "Compile workload")
        panel.close()


if __name__ == "__main__":
    unittest.main()
