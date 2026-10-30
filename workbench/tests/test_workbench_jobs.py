"""Reference GUI adapter checks; simulator execution is mocked explicitly."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench import workbench_jobs as jobs


class WorkbenchJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.engine = self.root / "engine"
        self.engine.mkdir()
        (self.project / "workspace.json").write_text(
            json.dumps({"engine": {"path": str(self.engine)}}), encoding="utf-8"
        )
        self.project_patch = patch.object(jobs, "PROJECT", self.project)
        self.project_patch.start()
        self.verify_patch = patch.object(
            jobs, "_verify_engine", return_value={"path": "checked", "sha256": "a" * 64}
        )
        self.verify = self.verify_patch.start()
        self.analysis_patch = patch(
            "salam_workbench.report.load_run",
            return_value={"correctness_verified": True, "issues": []},
        )
        self.analysis = self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()
        self.verify_patch.stop()
        self.project_patch.stop()
        self.temp.cleanup()

    def fake_execute(self, name, engine, runs_root):
        self.assertEqual(engine, self.engine)
        runs_root.resolve().relative_to(self.project / "evidence")
        runs = []
        for label in ("a", "b"):
            directory = runs_root / label
            directory.mkdir()
            (directory / "run.json").write_text('{"state":"passed"}')
            runs.append({"directory": str(directory), "state": "passed"})
        if name == "gemm":
            session = self.project / "evidence" / "gemm-fixture"
            negative = runs_root / "negative"
            negative.mkdir()
            result = {
                "state": "passed",
                "session_directory": str(session),
                "baseline_runs": runs,
                "comparison": {"repeatability_accepted": True},
                "negative_witness": {
                    "directory": str(negative),
                    "state": "failed",
                    "intentional_failure_detected": True,
                },
            }
        else:
            session = self.project / "evidence" / ("regression-fixture-" + name)
            result = {
                "state": "passed",
                "workloads": {
                    name: {
                        "state": "supported_fixed_dataset",
                        "runs": runs,
                        "comparison": {"repeatability_accepted": True},
                    }
                },
            }
        session.mkdir()
        (session / "session.json").write_text(json.dumps(result), encoding="utf-8")
        print("Session evidence: " + str(session))
        return result

    def launch(self, name="fft", execute=None, progress=None):
        with patch.object(
            jobs, "_execute_reference", side_effect=execute or self.fake_execute
        ):
            return jobs.launch_reference(name, project=self.project, progress=progress)

    def test_fixed_reference_uses_manifest_engine_and_private_runs_root(self):
        events = []
        result = self.launch("benchmarks/sys_validation/fft", progress=events.append)
        self.assertEqual(result["state"], "passed")
        self.assertFalse(result["editor_settings_applied"])
        self.assertEqual(result["mode"], "fixed_reference")
        self.assertEqual(len(result["run_directories"]), 2)
        self.assertEqual(result["run_directory"], result["run_directories"][-1])
        self.assertEqual(self.analysis.call_count, 2)
        self.verify.assert_called_once_with(self.project, self.engine)
        receipt = Path(result["evidence_directory"]) / "reference-session.json"
        self.assertEqual(json.loads(receipt.read_text()), result)
        self.assertEqual(events[0]["stage"], "reference_engine_verification")
        self.assertIn("verifying_reference_artifacts", [e["stage"] for e in events])

    def test_gemm_preserves_expected_failed_negative_control(self):
        from salam_workbench.runner import EXPECTED_EXIT_REASON

        negative_analysis = {
            "record": {"state": "failed", "return_code": 0},
            "raw_correctness": {
                "outcome": "failed",
                "passed_markers": 0,
                "failed_markers": 1,
            },
            "raw_simulator_exit": {"reason": EXPECTED_EXIT_REASON},
            "issues": [
                "Run state is not passed: failed",
                "Raw guest correctness evidence or recorded process exit does not satisfy the runner contract",
            ],
        }
        self.analysis.side_effect = [
            negative_analysis,
            {"correctness_verified": True},
            {"correctness_verified": True},
        ]
        result = self.launch("gemm")
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["negative_witness"]["state"], "failed")
        self.assertTrue(result["negative_witness"]["intentional_failure_detected"])
        self.assertNotIn(
            result["negative_witness"]["directory"], result["run_directories"]
        )

    def test_gemm_negative_flag_without_rejected_raw_output_is_insufficient(self):
        result = self.launch("gemm")
        self.assertEqual(result["state"], "failed")
        self.assertIn("negative control raw evidence", result["errors"][0])

    def test_printing_progress_callback_does_not_reenter_output_capture(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.launch(progress=lambda event: print(json.dumps(event)))
        self.assertEqual(result["state"], "passed")
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(events), 4)
        self.assertTrue(all(event["kind"] == "gui_progress" for event in events))

    def test_wrong_project_refused_before_evidence_is_allocated(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "installed Workbench"):
            jobs.launch_reference("fft", project=other)
        self.assertFalse((other / "evidence").exists())

    def test_unreviewed_and_lookalike_suites_refused(self):
        for value in ("foo", "benchmarks/legacy/fft", "../fft", "FFT", 42):
            with self.subTest(value=value), self.assertRaises(ValueError):
                jobs.launch_reference(value, project=self.project)
        self.assertFalse((self.project / "evidence").exists())

    def test_engine_inside_project_refused(self):
        local = self.project / "engine"
        local.mkdir()
        (self.project / "workspace.json").write_text(
            json.dumps({"engine": {"path": str(local)}})
        )
        with self.assertRaisesRegex(ValueError, "outside"):
            jobs.launch_reference("bfs", project=self.project)

    def test_failed_build_receipt_does_not_execute_simulator(self):
        self.verify.side_effect = ValueError("binary differs")
        with patch.object(jobs, "_execute_reference") as execute:
            result = jobs.launch_reference("bfs", project=self.project)
        self.assertEqual(result["state"], "failed")
        self.assertIn("binary differs", result["errors"][0])
        execute.assert_not_called()

    def test_failed_harness_is_not_success(self):
        result = self.launch(execute=lambda *_: {"state": "failed", "error": "bad"})
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["run_directory"])
        self.assertEqual(self.analysis.call_count, 0)

    def test_claimed_pass_without_durable_session_fails(self):
        result = self.launch(execute=lambda *_: {"state": "passed"})
        self.assertEqual(result["state"], "failed")
        self.assertIn("durable session", result["errors"][0])

    def test_changed_session_bytes_refused(self):
        def execute(*args):
            result = self.fake_execute(*args)
            result["state"] = "failed"
            return result

        result = self.launch(execute=execute)
        self.assertEqual(result["state"], "failed")
        self.assertIn("differs", result["errors"][0])

    def test_incomplete_raw_evidence_refused(self):
        self.analysis.return_value = {
            "correctness_verified": False,
            "issues": ["Artifact hash mismatch"],
        }
        result = self.launch()
        self.assertEqual(result["state"], "failed")
        self.assertIn("Artifact hash mismatch", result["errors"][0])

    def test_two_references_to_same_run_refused(self):
        def execute(*args):
            result = self.fake_execute(*args)
            runs = result["workloads"]["fft"]["runs"]
            runs[1] = runs[0]
            session = self.project / "evidence/regression-fixture-fft/session.json"
            session.write_text(json.dumps(result))
            return result

        result = self.launch(execute=execute)
        self.assertEqual(result["state"], "failed")
        self.assertIn("distinct run directories", result["errors"][0])

    def test_session_or_run_outside_evidence_refused(self):
        outside = self.root / "external"
        outside.mkdir()
        (outside / "session.json").write_text('{"state":"passed"}')

        def execute(*_):
            print("Session evidence: " + str(outside))
            return {"state": "passed"}

        result = self.launch(execute=execute)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(self.analysis.call_count, 0)

    def test_session_failure_is_saved_with_outputs(self):
        def execute(*_):
            print("Preparation started")
            raise RuntimeError("source changed")

        result = self.launch(execute=execute)
        directory = Path(result["evidence_directory"])
        self.assertEqual(result["state"], "failed")
        self.assertIn("source changed", result["errors"][0])
        self.assertIn("Preparation started", (directory / "backend.log").read_text())
        self.assertIsNotNone(result["finished_at"])


if __name__ == "__main__":
    unittest.main()
