"""Receipt and patch boundaries for the isolated GUI checked-prepare route."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from salam_workbench import configurator_gui_bridge as bridge


class CheckedGuiBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "workbench"
        self.project.mkdir()
        self.engine = self.root / "configurator-engine"
        selected = self.engine / "benchmarks/sys_validation/gemm/config.yml"
        selected.parent.mkdir(parents=True)
        selected.write_text("acc_cluster: []\n")
        self.selected = selected
        (self.engine / "gem5-SALAM-gui/src/gui").mkdir(parents=True)
        (self.engine / bridge.GUI_RELATIVE).write_text("# isolated GUI\n")
        (self.project / "evidence").mkdir()
        generated_outputs = []
        for relative, kind in (
                ("src/hwacc/generated/a.cc", "compiled_source"),
                ("src/hwacc/FunctionalUnits.py", "simobject_source"),
                ("src/hwacc/generated/SConscript", "build_declaration")):
            path = self.engine / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative + "\n")
            generated_outputs.append({
                "relative_path": relative, "sha256": bridge._sha(path), "kind": kind
            })
        generation = self.project / "evidence/generation.json"
        generation.write_text(json.dumps({
            "state": "generated", "valid": True,
            "selection": {"period": "5ns", "model": "40nm_model", "profile": "default_profile"},
            "outputs": generated_outputs
        }))
        build = self.project / "evidence/build.json"
        build.write_text("{}")
        (self.project / "workspace.json").write_text(json.dumps({
            "configuration_engine": {
                "distribution": "Ubuntu-20.04",
                "path": str(self.engine),
                "generation_receipt": "evidence/generation.json",
                "build_receipt": "evidence/build.json",
            }
        }))

    def prepare(self, **kwargs):
        return bridge.prepare_selected(
            kwargs.pop("engine", self.engine),
            "benchmarks/sys_validation/gemm",
            "benchmarks/sys_validation/gemm/config.yml",
            distro="Ubuntu-20.04",
            requested_period=kwargs.pop("period", "5ns"),
            project=self.project,
            evidence_dir=self.root / kwargs.pop("evidence", "gui-evidence"),
        )

    @staticmethod
    def successful_pipeline(engine, spec_path, directory, *, simulate=False):
        assert simulate is False
        Path(directory).mkdir()
        (Path(directory) / "configuration.json").write_text(json.dumps({
            "state": "prepared", "generated_after_build": {"outputs": ["guest", "ir"]},
            "simulation_requested": False
        }))
        return {"state": "prepared"}

    def test_success_requires_disk_prepared_receipt_and_leaves_yaml_unchanged(self):
        before = self.selected.read_bytes()
        with patch.object(bridge, "verify_engine", return_value={"binary": "verified"}), \
                patch.object(bridge, "run_configuration", side_effect=self.successful_pipeline) as run:
            result = self.prepare()
        self.assertEqual(result["state"], "prepared")
        self.assertEqual(self.selected.read_bytes(), before)
        self.assertFalse(result["editor_form_applied"])
        self.assertFalse(result["simulation_requested"])
        self.assertEqual(json.loads((self.root / "gui-evidence/gui-prepare.json").read_text())["state"],
                         "prepared")
        self.assertFalse(run.call_args.kwargs["simulate"])

    def test_period_mismatch_fails_before_prepare(self):
        with patch.object(bridge, "verify_engine") as identity, \
                patch.object(bridge, "run_configuration") as run:
            result = self.prepare(period="1ns")
        self.assertEqual(result["state"], "failed")
        self.assertIn("cycle time differs", result["errors"][0])
        identity.assert_not_called()
        run.assert_not_called()

    def test_generation_receipt_hash_mismatch_fails_before_prepare(self):
        generation_path = self.project / "evidence/generation.json"
        generation = json.loads(generation_path.read_text())
        generation["outputs"][0]["sha256"] = "0" * 64
        generation_path.write_text(json.dumps(generation))
        with patch.object(bridge, "verify_engine") as identity, \
                patch.object(bridge, "run_configuration") as run:
            result = self.prepare()
        self.assertEqual(result["state"], "failed")
        self.assertIn("Generated output differs", result["errors"][0])
        identity.assert_not_called()
        run.assert_not_called()
    def test_returned_success_cannot_override_failed_disk_receipt(self):
        def false_success(engine, spec_path, directory, *, simulate=False):
            Path(directory).mkdir()
            (Path(directory) / "configuration.json").write_text(json.dumps({
                "state": "failed", "generated_after_build": {}, "simulation_requested": False
            }))
            return {"state": "prepared"}
        with patch.object(bridge, "verify_engine", return_value={"binary": "verified"}), \
                patch.object(bridge, "run_configuration", side_effect=false_success):
            result = self.prepare()
        self.assertEqual(result["state"], "failed")

    def test_wrong_engine_fails_before_pipeline(self):
        wrong = self.root / "original-engine"
        wrong.mkdir()
        with patch.object(bridge, "run_configuration") as run:
            result = self.prepare(engine=wrong)
        self.assertEqual(result["state"], "failed")
        run.assert_not_called()

    def test_gui_render_removes_old_zero_exit_success_route(self):
        original = '''class Dialog:
    def setup(self):
        self.generate_btn = QPushButton("Generate Files")
    def generate_files(self):
        QMessageBox.question(self)
        command = "python3 -m salam_config.cli generate"
        message = "Generation completed successfully!"
    def _run_generation_in_wsl(self):
        pass
    def save_config(self):
        pass
'''
        updated = bridge.render_checked_gui_source(original)
        self.assertIn("Prepare Selected YAML (checked)", updated)
        self.assertIn("selected_engine != independent", updated)
        self.assertNotIn("python3 -m salam_config.cli generate", updated)
        self.assertNotIn("QMessageBox.question", updated)


if __name__ == "__main__":
    unittest.main()