# SPDX-License-Identifier: BSD-3-Clause
"""Checkpoint entry points must not restore the old guest-pass-only path."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from salam_workbench import configured_run

PROJECT = Path(__file__).resolve().parents[1]


class CheckpointIntegrationTests(unittest.TestCase):
    def test_source_ci_covers_upgrade_pr_and_visualizer(self):
        workflow = yaml.safe_load(
            (PROJECT.parent / ".github/workflows/ci.yml").read_text()
        )
        events = workflow.get("on", workflow.get(True))
        self.assertIn("codex/gem5-26-*", events["pull_request"]["branches"])
        for name, job in workflow["jobs"].items():
            if not name.startswith("source-only"):
                continue
            syntax = [
                step["run"]
                for step in job["steps"]
                if step.get("name") == "Check Python and curated configuration syntax"
            ]
            self.assertEqual(len(syntax), 1)
            self.assertIn("'visualizer'", syntax[0])

    def test_gemm_shell_has_valid_syntax_and_requires_explicit_request(self):
        script = PROJECT.parent / "run_gemm.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--request", result.stdout)

    def test_saved_request_requires_selected_benchmark_and_generated_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "request.json"
            with patch.object(configured_run, "apply_request") as launch:
                source.write_text(
                    json.dumps({"benchmark": "benchmarks/sys_validation/fft"})
                )
                with self.assertRaisesRegex(ValueError, "selected benchmark"):
                    configured_run.run_saved_request(source, benchmark="gemm")
                source.write_text(
                    json.dumps({"benchmark": "benchmarks/sys_validation/gemm"})
                )
                with self.assertRaisesRegex(ValueError, "generated inputs"):
                    configured_run.run_saved_request(source, benchmark="gemm")
                launch.assert_not_called()

    def test_failed_simulation_does_not_export_timelines(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "request.json"
            source.write_text(
                json.dumps(
                    {
                        "benchmark": "benchmarks/sys_validation/gemm",
                        "benchmark_input": {"dataset": "generated"},
                    }
                )
            )
            with patch.object(
                configured_run, "apply_request", return_value={"state": "failed"}
            ), patch.object(configured_run, "export_selected_trace") as export:
                result = configured_run.run_saved_request(source, benchmark="gemm")
            self.assertEqual(result["state"], "failed")
            export.assert_not_called()

    def test_current_evidence_failure_overrides_recorded_pipeline_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "request.json"
            source.write_text(
                json.dumps(
                    {
                        "benchmark": "benchmarks/sys_validation/gemm",
                        "benchmark_input": {"dataset": "generated"},
                    }
                )
            )
            for assessment, oracle in (
                ("failed", "passed"),
                ("incomplete", "passed"),
                ("checked_recorded_evidence", "failed"),
            ):
                with self.subTest(assessment=assessment, oracle=oracle):
                    with patch.object(
                        configured_run,
                        "apply_request",
                        return_value={
                            "state": "passed",
                            "evidence_directory": temporary,
                        },
                    ), patch.object(
                        configured_run,
                        "load_run",
                        return_value={
                            "validation_state": assessment,
                            "independent_oracle": {"state": oracle},
                        },
                    ), patch.object(
                        configured_run, "export_selected_trace"
                    ) as export:
                        result = configured_run.run_saved_request(
                            source, benchmark="gemm"
                        )
                    self.assertEqual(result["state"], "failed")
                    export.assert_not_called()
