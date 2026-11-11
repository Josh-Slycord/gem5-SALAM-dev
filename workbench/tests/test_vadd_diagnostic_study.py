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

    def test_only_bare_metal_gap_can_be_closed_with_bound_arm_elf(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            elf = directory / "workspace/benchmarks/sys_validation/vadd/sw/main.elf"
            elf.parent.mkdir(parents=True)
            elf.write_bytes(bytes.fromhex("7f454c4601010100000000000000000002002800"))
            digest = study._hash(elf)
            run_directory = directory / "runs/trial"
            config = run_directory / "simulator/config.ini"
            config.parent.mkdir(parents=True)
            config.write_text(
                "[system]\nworkload=system.workload\n"
                "[system.workload]\ntype=ArmFsWorkload\nobject_file="
                + str(elf)
                + "\nboot_loader=\ndtb_filename=\ninitrd_filename=\n",
                encoding="utf-8",
            )
            relative = "inputs/0001-main.elf"
            snapshot = run_directory / relative
            snapshot.parent.mkdir()
            snapshot.write_bytes(elf.read_bytes())
            identity = {
                "sha256": digest,
                "sha256_after_run": digest,
                "unchanged_after_run": True,
            }
            run = {
                "argv": ["gem5.opt", "--bare-metal", "--kernel=" + str(elf)],
                "inputs": [
                    dict(
                        identity, path=str(elf), snapshot=dict(identity, path=relative)
                    )
                ],
                "artifacts": [
                    {"path": relative, "sha256": digest},
                    {"path": "simulator/config.ini", "sha256": study._hash(config)},
                ],
            }
            pipeline = {
                "run_directory": str(run_directory),
                "vadd_build_witness": {
                    "guest_elf": {"path": str(elf), "sha256": digest}
                },
                "system_configuration": {
                    "effective": {"bare-metal": True, "mem-size": "64MB"}
                },
                "system_witness": {
                    "state": "partial",
                    "issues": [],
                    "unmapped_options": ["bare-metal"],
                    "checks": {
                        "bare-metal": {
                            "status": "unwitnessed",
                            "requested": True,
                            "observed": None,
                        },
                        "mem-size": {"status": "passed", "requested": "64MB"},
                    },
                },
            }
            accepted = study._witness_study_system(pipeline, directory, run)
            self.assertEqual(accepted["state"], "passed")
            self.assertEqual(accepted["pipeline_state"], "partial")
            self.assertEqual(accepted["bare_metal"]["guest_elf"]["sha256"], digest)

            altered = copy.deepcopy(pipeline)
            altered["system_witness"]["checks"]["mem-size"]["status"] = "unwitnessed"
            altered["system_witness"]["unmapped_options"].append("mem-size")
            with self.assertRaisesRegex(ValueError, "gap outside"):
                study._witness_study_system(altered, directory, run)
            altered = dict(
                run, argv=[arg for arg in run["argv"] if arg != "--bare-metal"]
            )
            with self.assertRaisesRegex(ValueError, "argv"):
                study._witness_study_system(pipeline, directory, altered)
            original_config = config.read_text(encoding="utf-8")
            config.write_text(
                original_config.replace("dtb_filename=\n", "dtb_filename=wrong.dtb\n"),
                encoding="utf-8",
            )
            altered = copy.deepcopy(run)
            altered["artifacts"][1]["sha256"] = study._hash(config)
            with self.assertRaisesRegex(ValueError, "does not boot"):
                study._witness_study_system(pipeline, directory, altered)
            config.write_text(original_config, encoding="utf-8")
            snapshot.write_bytes(b"changed ELF snapshot")
            with self.assertRaisesRegex(ValueError, "stale recorded artifact"):
                study._witness_study_system(pipeline, directory, run)

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
