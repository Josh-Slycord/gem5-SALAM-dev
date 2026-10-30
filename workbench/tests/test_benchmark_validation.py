"""Integration guard tests; generated protocol fixtures are not simulator runs."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.benchmark_oracles import (
    fixture_sha256, make_fixture, reference_outputs, render_output,
)
from salam_workbench.benchmark_validation import (
    assess_configured_output, fixture_for_spec, validate_input_case, numerical_output_relative,
)


def _helper(filename):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location("breadth_helper_" + path.stem, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_gui = _helper("test_gui_editor.py")
_reader = _helper("test_workbench_results.py")


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if isinstance(data, dict) else data,
                    encoding="utf-8")
    return path


def _record(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class BenchmarkValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="salam-breadth-validation-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.spec = {"benchmark": "benchmarks/sys_validation/gemm",
                     "benchmark_input": {"dataset": "seeded", "seed": 1}}
        self.fixture = fixture_for_spec(self.spec)
        self.terminal = _write(self.root / "system.terminal",
                               render_output(self.fixture) + "Check Passed\n")

    def test_malformed_or_explicitly_unknown_output_transport_is_rejected(self):
        for inputs in (None, [], "text", {"output_transport": None},
                       {"output_transport": "unknown"}):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                numerical_output_relative({"benchmark_inputs": inputs})
        self.assertEqual(numerical_output_relative({}), "simulator/system.terminal")

    def test_guest_templates_are_restorable_source_and_midrun_changes_reject(self):
        from unittest.mock import patch
        from salam_workbench.checks import source_identity
        from salam_workbench.configurator import snapshot_pipeline_tooling
        from salam_workbench.provenance import assert_tooling_unchanged

        template = _write(self.root / "experiments/breadth/overlays/common/result.h", "// original\n")
        _write(self.root / "salam_workbench/example.py", "answer = 1\n")
        relative = template.relative_to(self.root).as_posix()
        self.assertIn(relative, source_identity(self.root)["files"])
        with patch("salam_workbench.configurator.PROJECT", self.root):
            hashes = snapshot_pipeline_tooling(self.root / "snapshot")
        self.assertEqual((self.root / "snapshot" / relative).read_bytes(), template.read_bytes())
        template.write_text("// changed\n")
        with self.assertRaisesRegex(RuntimeError, "Tooling source changed"):
            assert_tooling_unchanged(self.root, hashes)

    def test_selector_regenerates_complete_fixture_and_changes_actual_inputs(self):
        self.assertEqual(self.fixture, make_fixture("gemm", "seeded", 1))
        changed = copy.deepcopy(self.spec)
        changed["benchmark_input"]["seed"] = 2
        self.assertNotEqual(self.fixture["inputs"], fixture_for_spec(changed)["inputs"])
        assessment = assess_configured_output(changed, self.terminal)
        self.assertEqual(assessment["state"], "failed")
        self.assertIn("identity", assessment["issues"][0])

    def test_saved_fixture_content_tamper_rejected_even_with_valid_new_digest(self):
        changed = copy.deepcopy(self.fixture)
        changed["inputs"]["a"][0] += 1
        changed["fixture_sha256"] = fixture_sha256(changed)
        path = _write(self.root / "fixture.json", changed)
        with self.assertRaisesRegex(ValueError, "fixture|requested input"):
            assess_configured_output(self.spec, self.terminal, path)

    def test_saved_fixture_type_tamper_cannot_hide_behind_python_numeric_equality(self):
        changed = copy.deepcopy(self.fixture)
        changed["seed"] = True
        self.assertEqual(changed, self.fixture)  # Python equates True with 1.
        path = _write(self.root / "fixture.json", changed)
        with self.assertRaises(ValueError):
            assess_configured_output(self.spec, self.terminal, path)

    def test_complete_hardware_output_is_checked_despite_guest_pass(self):
        output = reference_outputs(self.fixture)
        output[17] += 1
        _write(self.terminal, render_output(self.fixture, output) + "Check Passed\n")
        result = assess_configured_output(self.spec, self.terminal)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["compared_count"], 64)
        self.assertEqual(result["mismatch_count"], 1)
        self.assertEqual(result["terminal_sha256"], _record(self.terminal)["sha256"])

    def test_selector_rejects_nonfinite_boolean_seed_and_unbounded_controls(self):
        invalid = [
            {"dataset": "seeded", "seed": True},
            {"dataset": "seeded", "seed": -1},
            {"dataset": "seeded", "seed": 2147483648},
            {"dataset": "seeded", "seed": float("inf")},
            {"dataset": "seeded", "seed": float("nan")},
            {"dataset": "seeded", "seed": 1, "inject_mismatch": "true"},
            {"dataset": "seeded", "seed": 1, "force_guest_pass": True},
            {"dataset": "arbitrary", "seed": 1},
            {"dataset": "seeded", "seed": 1, "unexpected": 0},
        ]
        for selector in invalid:
            with self.subTest(selector=selector):
                with self.assertRaises(ValueError):
                    validate_input_case(self.spec["benchmark"], selector)
        controls = {"dataset": "seeded", "seed": 1,
                    "inject_mismatch": True, "force_guest_pass": True}
        self.assertEqual(validate_input_case(self.spec["benchmark"], controls), controls)
        with self.assertRaises(ValueError):
            validate_input_case("benchmarks/sys_validation/bfs", controls)

    def test_gui_request_preserves_dataset_seed_and_source_bound_snapshot(self):
        fixture = _gui.GuiEditorTests("runTest")
        fixture.setUp()
        fixture.snapshot["benchmark_input"] = {"dataset": "seeded", "seed": 2}
        request = fixture.request()
        self.assertEqual(request["benchmark_input"], {"dataset": "seeded", "seed": 2})
        self.assertEqual(request["provenance"]["editor_snapshot"]["benchmark_input"],
                         request["benchmark_input"])

    def test_gui_cannot_enable_backend_negative_controls_even_when_false(self):
        fixture = _gui.GuiEditorTests("runTest")
        fixture.setUp()
        for key, value in (("inject_mismatch", True), ("force_guest_pass", True),
                           ("inject_mismatch", False)):
            fixture.snapshot["benchmark_input"] = {"dataset": "seeded", "seed": 1,
                                                    key: value}
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, "backend-only"):
                    fixture.request()

    def _reader_case(self, *, corrupted_output=False, tampered_fixture=False):
        helpers = _reader.WorkbenchResultsTests("runTest")
        helpers.setUp()
        self.addCleanup(helpers.doCleanups)
        raw = helpers.raw_run("configured/pipeline/runs/run-1")
        output = reference_outputs(self.fixture)
        if corrupted_output:
            output[0] += 1
        terminal = _write(raw / "simulator/system.terminal",
                          render_output(self.fixture, output) + "Check Passed\n")
        record = json.loads((raw / "run.json").read_text())
        for item in record["artifacts"]:
            if item["path"] == "simulator/system.terminal":
                item["sha256"] = _record(terminal)["sha256"]
        _write(raw / "run.json", record)
        directory = raw.parent.parent
        spec_path = _write(directory / "specification.json", self.spec)
        fixture = copy.deepcopy(self.fixture)
        if tampered_fixture:
            fixture["inputs"]["a"][1] += 1
            fixture["fixture_sha256"] = fixture_sha256(fixture)
        fixture_path = _write(directory / "fixture.json", fixture)
        pipeline = _write(directory / "configuration.json", {
            "state": "passed", "run_directory": str(raw),
            "specification": _record(spec_path),
            "benchmark_fixture": _record(fixture_path),
            "independent_oracle": {"state": "passed"},
        })
        return _reader.load_run(pipeline, helpers.project)

    def test_results_reader_replays_complete_outputs_and_ignores_saved_pass(self):
        positive = self._reader_case()
        check = next(row for row in positive["checks"]
                     if row["name"] == "Independent numerical validation")
        self.assertEqual(check["status"], "passed")
        failed = self._reader_case(corrupted_output=True)
        self.assertEqual(failed["state"], "passed")  # Recorded status is preserved.
        self.assertEqual(failed["independent_oracle"]["state"], "failed")
        self.assertEqual(failed["validation_state"], "failed")

    def test_results_reader_regenerates_fixture_despite_matching_saved_file_hash(self):
        result = self._reader_case(tampered_fixture=True)
        check = next(row for row in result["checks"]
                     if row["name"] == "Independent numerical validation")
        self.assertEqual(check["status"], "failed")
        self.assertEqual(result["validation_state"], "failed")


if __name__ == "__main__":
    unittest.main()
