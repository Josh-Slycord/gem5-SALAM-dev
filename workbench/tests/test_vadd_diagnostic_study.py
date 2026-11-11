# SPDX-License-Identifier: BSD-3-Clause
"""Study classifier controls use synthetic receipts, never simulator evidence."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench.benchmark_oracles import (
    assess_output,
    make_fixture,
    reference_outputs,
    render_output,
)

PROJECT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


study = _load("vadd_diagnostic_study", PROJECT / "scripts/run_vadd_diagnostic.py")
numpy_tool = _load("vadd_diagnostic_numpy", PROJECT / "scripts/verify_numpy_outputs.py")


class VaddStudyClassifierTests(unittest.TestCase):
    def setUp(self):
        self.fixture = make_fixture("vadd", "seeded", 1, length=8)
        output = reference_outputs(self.fixture)
        output[0] ^= 1
        raw = render_output(self.fixture, output)
        self.oracle = assess_output(raw, self.fixture)
        saved = numpy_tool.load_fixture(json.dumps(self.fixture).encode())
        observed, _ = numpy_tool.parse_observed(raw.encode(), saved)
        self.numpy = numpy_tool.compare_vectors(
            numpy_tool.expected_outputs(saved), observed, "int32"
        )

    def _receipts(self, forced):
        pipeline = {
            "state": "failed",
            "stage": "independent_numerical_validation" if forced else "simulation",
            "errors": [
                "ValueError: Independent full-output numerical oracle rejected the simulation"
                if forced
                else "ValueError: Simulator/guest did not pass: ['Nonzero process exit or explicit guest correctness failure']"
            ],
        }
        run = {
            "state": "passed" if forced else "failed",
            "stage": "assessment",
            "return_code": 0,
            "correctness": {
                "passed_markers": 1 if forced else 0,
                "failed_markers": 0 if forced else 1,
                "outcome": "passed" if forced else "failed",
            },
            "errors": []
            if forced
            else ["Nonzero process exit or explicit guest correctness failure"],
        }
        return pipeline, run

    def test_both_expected_gate_failures_require_two_actual_numerical_comparisons(self):
        for forced in (False, True):
            with self.subTest(forced=forced):
                pipeline, run = self._receipts(forced)
                self.assertEqual(
                    study._negative_errors(
                        pipeline, run, self.oracle, self.numpy, 8, forced
                    ),
                    [],
                )

    def test_crashes_timeouts_unrelated_errors_and_wrong_markers_never_count(self):
        for forced in (False, True):
            pipeline, run = self._receipts(forced)
            variants = [
                (dict(pipeline, stage="source_staging"), run),
                (dict(pipeline, state="passed"), run),
                (dict(pipeline, errors=["ValueError: compiler failed"]), run),
                (pipeline, dict(run, state="timed_out")),
                (pipeline, dict(run, return_code=-6)),
                (pipeline, dict(run, return_code=None)),
                (pipeline, dict(run, stage="execution")),
                (pipeline, dict(run, errors=["Input source changed"])),
                (
                    pipeline,
                    dict(run, correctness={"passed_markers": 0, "failed_markers": 0}),
                ),
            ]
            for changed_pipeline, changed_run in variants:
                with self.subTest(
                    forced=forced, pipeline=changed_pipeline, run=changed_run
                ):
                    self.assertTrue(
                        study._negative_errors(
                            changed_pipeline,
                            changed_run,
                            self.oracle,
                            self.numpy,
                            8,
                            forced,
                        )
                    )

    def test_missing_partial_or_unrelated_mismatch_is_not_the_expected_control(self):
        pipeline, run = self._receipts(True)
        for check in (
            {"state": "rejected"},
            dict(self.oracle, state="passed"),
            dict(self.oracle, compared_count=7),
            dict(self.oracle, mismatch_count=2),
            dict(self.oracle, issues=["Numerical output mismatch at index 7"]),
        ):
            with self.subTest(check=check):
                self.assertTrue(
                    study._negative_errors(pipeline, run, check, self.numpy, 8, True)
                )
        wrong = copy.deepcopy(self.numpy)
        wrong["first_mismatches"][0]["index"] = 7
        self.assertTrue(
            study._negative_errors(pipeline, run, self.oracle, wrong, 8, True)
        )
        self.assertTrue(
            study._negative_errors(
                pipeline, run, self.oracle, {"state": "rejected"}, 8, True
            )
        )

    def test_existing_output_is_retained_before_any_pipeline_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / "receipt.json"
            receipt.write_text("{}")
            output = root / "existing"
            output.mkdir()
            retained = output / "keep.txt"
            retained.write_text("retained")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                study.run_study(root, receipt, output)
            self.assertEqual(retained.read_text(), "retained")

    def test_cli_defaults_to_preparation_and_never_implicitly_simulates(self):
        with patch.object(
            study, "run_study", return_value={"state": "prepared"}
        ) as run:
            self.assertEqual(
                study.main(
                    [
                        "--engine",
                        "engine",
                        "--build-receipt",
                        "receipt",
                        "--output",
                        "fresh",
                    ]
                ),
                0,
            )
        self.assertFalse(run.call_args.kwargs["simulate"])
        self.assertFalse(run.call_args.kwargs["include_max"])


if __name__ == "__main__":
    unittest.main()
