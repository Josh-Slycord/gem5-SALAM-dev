"""Acceptance-study guard tests; synthetic fixtures are not simulator runs."""
import configparser
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_configurable_breadth.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_configurable_breadth", str(SCRIPT)
)
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


class ConfigurableBreadthTests(unittest.TestCase):
    def _transport_fixture(self, folder):
        root = Path(folder)
        simulator = root / "simulator"
        simulator.mkdir()
        terminal = simulator / "system.terminal"
        terminal.write_text("Check Passed\n", encoding="utf-8")
        output = simulator / "salam-results.txt"
        output.write_text("complete numeric protocol fixture\n", encoding="utf-8")
        run = {
            "run_directory": str(root),
            "artifacts": [
                {"path": path.relative_to(root).as_posix(), "sha256": study._sha(path)}
                for path in (terminal, output)
            ],
        }
        return run, terminal, output

    def test_explicit_file_transport_uses_complete_output_and_keeps_uart_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            run, terminal, output = self._transport_fixture(folder)
            path, transport = study.numerical_output_artifact(
                run,
                {
                    "benchmark_inputs": {
                        "output_transport": "gem5_semihosting_writefile_text_v1",
                        "output_relative": "simulator/salam-results.txt",
                    }
                },
            )
            self.assertEqual(path, output)
            self.assertNotEqual(path, terminal)
            self.assertEqual(transport, "gem5_semihosting_writefile_text_v1")
            output.write_text("changed numerical payload\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                study.numerical_output_artifact(
                    run,
                    {
                        "benchmark_inputs": {
                            "output_transport": "gem5_semihosting_writefile_text_v1"
                        }
                    },
                )

    def test_preserved_uart_transport_is_explicitly_labelled_and_unknowns_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as folder:
            run, terminal, _ = self._transport_fixture(folder)
            path, transport = study.numerical_output_artifact(
                run, {"benchmark_inputs": {}}
            )
            self.assertEqual(path, terminal)
            self.assertEqual(transport, "legacy_uart_text_v1")
            for inputs in (
                {"output_transport": "unknown_future_format"},
                {"output_transport": None},
                {
                    "output_transport": "gem5_semihosting_writefile_text_v1",
                    "output_relative": "../elsewhere",
                },
            ):
                with self.subTest(inputs=inputs):
                    with self.assertRaises(ValueError):
                        study.numerical_output_artifact(
                            run, {"benchmark_inputs": inputs}
                        )

    def test_declared_file_transport_never_falls_back_to_uart_when_unrecorded(self):
        with tempfile.TemporaryDirectory() as folder:
            run, _, _ = self._transport_fixture(folder)
            run["artifacts"] = [
                entry
                for entry in run["artifacts"]
                if entry["path"] != "simulator/salam-results.txt"
            ]
            with self.assertRaisesRegex(ValueError, "Missing or duplicated"):
                study.numerical_output_artifact(
                    run,
                    {
                        "benchmark_inputs": {
                            "output_transport": "gem5_semihosting_writefile_text_v1"
                        }
                    },
                )

    def _system_settings(self):
        return {"cpu-clock": "2GHz", "sys-clock": "1GHz", "cacheline_size": 64}

    def _system_witness(self):
        checks = {
            key: {"status": "passed", "requested": value, "observed": value}
            for key, value in self._system_settings().items()
        }
        checks["mem-size"] = {
            "status": "passed",
            "requested": "4GB",
            "observed": 4294967296,
        }
        checks["bare-metal"] = {
            "status": "unwitnessed",
            "requested": True,
            "observed": None,
        }
        return {
            "state": "partial",
            "issues": [],
            "unmapped_options": ["bare-metal"],
            "checks": checks,
        }

    def test_known_bare_metal_gap_is_retained_without_weakening_explicit_checks(self):
        witness = self._system_witness()
        original = copy.deepcopy(witness)
        assessment = study.study_system_witness(witness, self._system_settings())
        self.assertEqual(assessment["state"], "partial")
        self.assertEqual(assessment["explicit_study_settings"], "passed")
        self.assertEqual(assessment["unmapped_options"], ["bare-metal"])
        self.assertIn("not independently witnessed", assessment["limitations"][0])
        self.assertEqual(witness, original)

    def test_partial_exception_rejects_other_unknowns_errors_and_failed_explicit_fields(
        self,
    ):
        edits = (
            ("unmapped_options", ["bare-metal", "mem-type"]),
            ("unmapped_options", ["mem-type"]),
            ("unmapped_options", []),
            ("issues", ["Observed wrong system clock"]),
            ("state", "failed"),
        )
        for key, value in edits:
            witness = self._system_witness()
            witness[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    study.study_system_witness(witness, self._system_settings())
        for key in ("cpu-clock", "sys-clock", "cacheline_size", "mem-size"):
            for status in ("failed", "unwitnessed"):
                witness = self._system_witness()
                witness["checks"][key]["status"] = status
                with self.subTest(key=key, status=status):
                    with self.assertRaises(ValueError):
                        study.study_system_witness(witness, self._system_settings())

    def test_explicit_system_setting_cannot_be_missing_or_claimed_for_another_request(
        self,
    ):
        witness = self._system_witness()
        witness["checks"].pop("cpu-clock")
        with self.assertRaises(ValueError):
            study.study_system_witness(witness, self._system_settings())
        witness = self._system_witness()
        witness["checks"]["cpu-clock"]["requested"] = "1GHz"
        with self.assertRaises(ValueError):
            study.study_system_witness(witness, self._system_settings())
        witness = self._system_witness()
        witness["checks"]["cacheline_size"]["requested"] = True
        with self.assertRaises(ValueError):
            study.study_system_witness(witness, self._system_settings())
        with self.assertRaises(ValueError):
            study.study_system_witness(self._system_witness(), {"bare-metal": True})

    def test_default_matrix_has_independent_negatives_for_all_three_workloads(self):
        cases = study.matrix_cases()
        self.assertEqual(len(cases), 15)
        self.assertEqual(len({row["id"] for row in cases}), 15)
        for workload in study.WORKLOADS:
            rows = [row for row in cases if row["workload"] == workload]
            self.assertEqual({row["seed"] for row in rows}, {1, 2})
            self.assertEqual(
                sum(row["expected_outcome"] == "passed" for row in rows), 4
            )
            self.assertEqual(sum(row["variant"] == "wrong_output" for row in rows), 1)

    def test_matrix_rejects_ambiguous_or_invalid_case_requests(self):
        for workloads, seeds, repeats in (
            (("gemm", "gemm"), (1, 2), 1),
            (("neural",), (1, 2), 1),
            (("gemm",), (True, 2), 1),
            (("gemm",), (1, 1), 1),
            (("gemm",), (1, 2), 0),
        ):
            with self.subTest(workloads=workloads, seeds=seeds, repeats=repeats):
                with self.assertRaises(ValueError):
                    study.matrix_cases(workloads, seeds, repeats)

    def test_runtime_parameter_binds_to_source_cluster_and_ir_identity(self):
        documents = [
            {
                "acc_cluster": [
                    {"Name": "renamed_cluster"},
                    {
                        "Accelerator": [
                            {
                                "Name": "OtherTop",
                                "IrPath": "benchmarks/sys_validation/fft/hw/top.ll",
                            }
                        ]
                    },
                    {
                        "Accelerator": [
                            {
                                "Name": "ActualFFT",
                                "IrPath": "benchmarks/sys_validation/fft/hw/fft.ll",
                            }
                        ]
                    },
                ]
            }
        ]
        case = study.matrix_cases(("fft",), (1,), negatives=False)[1]
        specification, target = study.specification_from_documents(documents, case)
        self.assertEqual(target, "system.renamed_cluster.actualfft")
        self.assertEqual(
            specification["parameters"],
            {target + ".hw_interface.cycle_counts": {"fmul": 4}},
        )
        self.assertEqual(
            specification["benchmark_input"], {"dataset": "seeded", "seed": 1}
        )
        self.assertEqual(specification["configuration_documents"], documents)

    def test_negative_control_requests_actual_mismatch_and_guest_pass(self):
        documents = [
            {
                "acc_cluster": [
                    {"Name": "a"},
                    {
                        "Accelerator": [
                            {
                                "Name": "gemm",
                                "IrPath": "benchmarks/sys_validation/gemm/hw/gemm.ll",
                            }
                        ]
                    },
                ]
            }
        ]
        case = study.matrix_cases(("gemm",), (1,))[-1]
        specification, _ = study.specification_from_documents(documents, case)
        self.assertIs(specification["benchmark_input"]["inject_mismatch"], True)
        self.assertIs(specification["benchmark_input"]["force_guest_pass"], True)

    def test_stencil_single_register_port_is_explicit_and_original_yaml_is_preserved(
        self,
    ):
        documents = [
            {
                "acc_cluster": [
                    {"Name": "stencil3d_clstr"},
                    {
                        "Accelerator": [
                            {
                                "Name": "stencil3d",
                                "IrPath": "benchmarks/sys_validation/stencil3d/hw/stencil3d.ll",
                            },
                            {
                                "Var": [
                                    {
                                        "Name": "C_VAR",
                                        "Type": "RegisterBank",
                                        "Size": 8,
                                        "Ports": 2,
                                    }
                                ]
                            },
                            {
                                "Var": [
                                    {
                                        "Name": "INPUT",
                                        "Type": "SPM",
                                        "Size": 65536,
                                        "Ports": 2,
                                    }
                                ]
                            },
                        ]
                    },
                ]
            }
        ]
        original = copy.deepcopy(documents)
        case = study.matrix_cases(("stencil3d",), (1,), negatives=False)[0]
        specification, _ = study.specification_from_documents(documents, case)
        self.assertEqual(documents, original)
        selected = specification["configuration_documents"][0]["acc_cluster"][1][
            "Accelerator"
        ]
        self.assertEqual(selected[1]["Var"][0]["Ports"], 1)
        self.assertEqual(selected[2]["Var"][0]["Ports"], 2)
        self.assertEqual(selected[1]["Var"][0]["Size"], 8)
        self.assertIn(
            "C_VAR source Ports=2 explicitly configured Ports=1",
            specification["correctness"]["description"],
        )
        self.assertIn(
            "multiport RegisterBank is outside this study",
            specification["correctness"]["description"],
        )
        self.assertEqual(
            specification["parameters"][
                "system.stencil3d_clstr.stencil3d.llvm_interface"
            ],
            {"fu_trace_event_limit": 1048576},
        )
        self.assertIn(
            "complete independent replay remains required",
            specification["correctness"]["description"],
        )

    def test_stencil_trace_budget_requires_an_explicit_matching_live_value(self):
        target = "system.changed_cluster.changed_accelerator"
        section = target + ".llvm_interface"
        specification = {
            "benchmark": "benchmarks/sys_validation/stencil3d",
            "parameters": {section: {"fu_trace_event_limit": 1048576}},
        }
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_dict({section: {"fu_trace_event_limit": "1048576"}})
        result = study.witness_trace_event_limit(parser, specification, target)
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["observed"], 1048576)
        self.assertIn(section, result["source"])
        parser.set(section, "fu_trace_event_limit", "262144")
        with self.assertRaisesRegex(ValueError, "did not reach"):
            study.witness_trace_event_limit(parser, specification, target)
        parser.remove_option(section, "fu_trace_event_limit")
        with self.assertRaises(configparser.Error):
            study.witness_trace_event_limit(parser, specification, target)
        invalid = copy.deepcopy(specification)
        invalid["parameters"][section]["fu_trace_event_limit"] = 262144
        with self.assertRaisesRegex(ValueError, "explicitly request"):
            study.witness_trace_event_limit(parser, invalid, target)
        self.assertIsNone(
            study.witness_trace_event_limit(
                parser, {"benchmark": "benchmarks/sys_validation/fft"}, target
            )
        )

    def test_stencil_register_port_choice_never_hides_an_invalid_source_request(self):
        for value in (0, -1, True, "2", None):
            documents = [
                {
                    "acc_cluster": [
                        {"Name": "a"},
                        {
                            "Accelerator": [
                                {"Name": "stencil3d", "IrPath": "hw/stencil3d.ll"},
                                {
                                    "Var": [
                                        {
                                            "Name": "C_VAR",
                                            "Type": "RegisterBank",
                                            "Ports": value,
                                        }
                                    ]
                                },
                            ]
                        },
                    ]
                }
            ]
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "explicit positive"):
                    study.specification_from_documents(
                        documents,
                        study.matrix_cases(("stencil3d",), (1,), negatives=False)[0],
                    )

    def test_missing_workload_ir_cannot_reuse_arbitrary_accelerator(self):
        documents = [
            {
                "acc_cluster": [
                    {"Name": "a"},
                    {
                        "Accelerator": [
                            {
                                "Name": "gemm",
                                "IrPath": "benchmarks/sys_validation/gemm/hw/top.ll",
                            }
                        ]
                    },
                ]
            }
        ]
        with self.assertRaises(ValueError):
            study.specification_from_documents(documents, study.matrix_cases()[0])

    def test_artifact_replay_requires_unique_recorded_matching_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            terminal = root / "terminal"
            terminal.write_text("original hardware output", encoding="utf-8")
            entry = {"path": "terminal", "sha256": study._sha(terminal)}
            run = {"run_directory": str(root), "artifacts": [entry]}
            self.assertEqual(study._verified_artifact(run, "terminal"), terminal)
            terminal.write_text("changed bytes", encoding="utf-8")
            with self.assertRaises(ValueError):
                study._verified_artifact(run, "terminal")
            run["artifacts"] = [entry, entry]
            with self.assertRaises(ValueError):
                study._verified_artifact(run, "terminal")

    def _rows(self):
        rows = []
        for case in study.matrix_cases(("gemm",), (1, 2), negatives=False):
            rows.append(
                {
                    "case": case,
                    "state": "passed",
                    "fixture_sha256": "fixture-" + str(case["seed"]),
                    "input_content_sha256": "inputs-" + str(case["seed"]),
                    "output_sha256": "outputs-" + str(case["seed"]),
                    "accelerator_elapsed_ticks": 100
                    if case["variant"] == "baseline"
                    else 140,
                }
            )
        return rows

    def test_setting_pairs_require_fixed_inputs_and_observed_simulator_response(self):
        comparisons, inputs = study.compare_cases(self._rows())
        self.assertTrue(all(row["state"] == "passed" for row in comparisons + inputs))
        rows = self._rows()
        rows[1]["accelerator_elapsed_ticks"] = 100
        comparisons, _ = study.compare_cases(rows)
        self.assertEqual(comparisons[0]["state"], "failed")
        self.assertIn("timing response", comparisons[0]["issues"][0])
        rows = self._rows()
        rows[1]["fixture_sha256"] = "different-input"
        comparisons, _ = study.compare_cases(rows)
        self.assertEqual(comparisons[0]["state"], "failed")

    def test_input_breadth_cannot_be_claimed_for_identical_fixtures(self):
        rows = self._rows()
        for row in rows:
            row["fixture_sha256"] = "same-input"
        _, checks = study.compare_cases(rows)
        self.assertEqual(checks[0]["state"], "failed")
        self.assertEqual(checks[0]["distinct_fixture_count"], 1)

    def test_seed_labels_alone_do_not_establish_numeric_input_breadth(self):
        from salam_workbench.benchmark_oracles import make_fixture

        first, second = make_fixture("gemm", "zeros", 1), make_fixture(
            "gemm", "zeros", 2
        )
        self.assertNotEqual(first["fixture_sha256"], second["fixture_sha256"])
        self.assertEqual(
            study.input_content_sha256(first), study.input_content_sha256(second)
        )
        rows = self._rows()
        for row in rows:
            row["input_content_sha256"] = "identical-numeric-inputs"
        _, checks = study.compare_cases(rows)
        self.assertEqual(checks[0]["state"], "failed")
        self.assertEqual(checks[0]["distinct_numeric_input_count"], 1)

    def test_settings_preserve_actual_output_bits_and_input_content(self):
        rows = self._rows()
        rows[1]["output_sha256"] = "different-hardware-output"
        comparisons, _ = study.compare_cases(rows)
        self.assertEqual(comparisons[0]["state"], "failed")
        self.assertIn("output bits", comparisons[0]["issues"][0])
        rows = self._rows()
        rows[1]["input_content_sha256"] = "different-numeric-inputs"
        comparisons, _ = study.compare_cases(rows)
        self.assertEqual(comparisons[0]["state"], "failed")
        self.assertIn("input content", comparisons[0]["issues"][0])

    def test_failed_or_incomplete_run_pair_is_not_accepted(self):
        rows = self._rows()
        rows.pop(1)
        comparisons, _ = study.compare_cases(rows)
        self.assertEqual(comparisons[0]["state"], "failed")


if __name__ == "__main__":
    unittest.main()
