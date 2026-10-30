"""Focused tests for isolated wrong-output regression controls."""
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

from salam_workbench.regression_negative import (
    MODES,
    MUTATIONS,
    WORKLOADS,
    apply_mutation,
    assess_negative_run,
    main,
)


class NegativeControlsTest(unittest.TestCase):
    def test_each_hardware_mutation_sits_between_completion_and_copyback(self):
        for name in WORKLOADS:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                relative, anchor, injection = MUTATIONS[name]["hw-spm"]
                workspace = Path(temporary)
                target = workspace / name / relative
                target.parent.mkdir(parents=True)
                target.write_text(
                    "void top(void) {\n" + anchor + "\t//Transfer output back\n}\n",
                    encoding="utf-8",
                )
                entry = {"name": name, "relative_path": name}
                original = target.read_text()
                patch = apply_mutation(workspace, entry, "hw-spm")
                changed = target.read_text()
                self.assertEqual(original.count(anchor), 1)
                self.assertLess(changed.index(anchor), changed.index(injection))
                self.assertLess(
                    changed.index(injection),
                    changed.index("Transfer output back"),
                )
                self.assertNotEqual(patch["before_sha256"], patch["after_sha256"])
                self.assertEqual(patch["mode"], "hw-spm")
                with self.assertRaises(ValueError):
                    apply_mutation(workspace, entry, "hw-spm")

    def test_guest_mutation_is_after_completion_and_before_oracle(self):
        for name in WORKLOADS:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                relative, anchor, injection = MUTATIONS[name]["guest"]
                workspace = Path(temporary)
                target = workspace / name / relative
                target.parent.mkdir(parents=True)
                target.write_text(
                    "void main(void) {\n" + anchor + "#ifdef CHECK\n}\n",
                    encoding="utf-8",
                )
                apply_mutation(
                    workspace, {"name": name, "relative_path": name}, "guest"
                )
                changed = target.read_text()
                self.assertLess(changed.index(anchor), changed.index(injection))
                self.assertLess(changed.index(injection), changed.index("#ifdef CHECK"))

    def test_missing_or_ambiguous_anchor_is_rejected_without_source_change(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target = workspace / "fft/hw/top.c"
            target.parent.mkdir(parents=True)
            target.write_text("void top(void) {}\n", encoding="utf-8")
            before = target.read_bytes()
            with self.assertRaises(ValueError):
                apply_mutation(
                    workspace,
                    {"name": "fft", "relative_path": "fft"},
                    "hw-spm",
                )
            self.assertEqual(target.read_bytes(), before)
            target.write_text(MUTATIONS["fft"]["hw-spm"][1] * 2, encoding="utf-8")
            before = target.read_bytes()
            with self.assertRaises(ValueError):
                apply_mutation(
                    workspace,
                    {"name": "fft", "relative_path": "fft"},
                    "hw-spm",
                )
            self.assertEqual(target.read_bytes(), before)

    def _record(self):
        return {
            "state": "failed",
            "return_code": 0,
            "correctness": {
                "outcome": "failed",
                "passed_markers": 0,
                "failed_markers": 1,
            },
            "simulator_exit": {
                "tick": 100,
                "reason": "m5_exit instruction encountered",
            },
            "simulator_exit_events": [
                {"tick": 100, "reason": "m5_exit instruction encountered"}
            ],
            "required_artifact_checks": [
                {"path": "simulator/system.terminal", "available": True}
            ],
            "executable": {"unchanged_after_run": True},
            "inputs": [
                {
                    "unchanged_after_run": True,
                    "snapshot": {"unchanged_after_run": True},
                }
            ],
            "observability": {"status": "valid", "valid": True, "issues": []},
        }

    def test_only_explicit_guest_failure_with_normal_simulator_exit_is_witness(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            terminal = run_dir / "simulator/system.terminal"
            terminal.parent.mkdir()
            terminal.write_text("Job complete\nCheck Failed\n", encoding="utf-8")
            record = self._record()
            self.assertTrue(
                assess_negative_run(record, run_dir)["intentional_failure_detected"]
            )
            record["return_code"] = 1
            self.assertFalse(
                assess_negative_run(record, run_dir)["intentional_failure_detected"]
            )
            record["return_code"] = 0
            terminal.write_text("Check Failed\n", encoding="utf-8")
            self.assertFalse(
                assess_negative_run(record, run_dir)["intentional_failure_detected"]
            )
            terminal.write_text(
                "Job complete\nCheck Passed\nCheck Failed\n", encoding="utf-8"
            )
            self.assertFalse(
                assess_negative_run(record, run_dir)["intentional_failure_detected"]
            )

    def test_nw_duplicate_failure_markers_are_accepted_but_observability_must_hold(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            terminal = run_dir / "simulator/system.terminal"
            terminal.parent.mkdir()
            terminal.write_text(
                "Job complete\nCheck Failed\nCheck Failed\n", encoding="utf-8"
            )
            record = self._record()
            record["correctness"]["failed_markers"] = 2
            self.assertTrue(
                assess_negative_run(record, run_dir)["intentional_failure_detected"]
            )
            record["observability"]["status"] = "invalid"
            self.assertFalse(
                assess_negative_run(record, run_dir)["intentional_failure_detected"]
            )

    def test_control_matrix_covers_four_workloads_and_two_distinct_modes(self):
        self.assertEqual(set(WORKLOADS), {"bfs", "nw", "fft", "stencil3d"})
        self.assertEqual(set(MODES), {"hw-spm", "guest"})
        self.assertTrue(all(set(MUTATIONS[name]) == set(MODES) for name in WORKLOADS))

    def test_cli_requires_explicit_workload_selection(self):
        argv = [
            "regression_negative",
            "--engine",
            "/unused/engine",
            "--positive-session",
            "/unused/session",
        ]
        with mock.patch("sys.argv", argv), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
