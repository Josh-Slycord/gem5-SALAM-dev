# SPDX-License-Identifier: BSD-3-Clause
"""Host selection boundaries; real factory parity is a separate simulation study."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

from salam_workbench import configurator


class NativeBuilderSelectionTests(unittest.TestCase):
    def specification(self):
        return {
            "schema_version": 1,
            "name": "native_gemm",
            "benchmark": "benchmarks/sys_validation/gemm",
            "base_address": "0x10020000",
            "system": {},
        }

    def test_native_is_explicit_and_unknown_builder_is_rejected(self):
        for builder in ("native", "generated"):
            data = self.specification()
            data["builder"] = builder
            configurator.validate_spec(data)
        for builder in ("automatic", True, 1, None):
            data = self.specification()
            data["builder"] = builder
            with self.subTest(builder=builder), self.assertRaises(ValueError):
                configurator.validate_spec(data)

    def test_managed_native_paths_cannot_be_overridden_by_system_options(self):
        for option in ("salam-builder", "salam-config", "salam-base-address"):
            data = self.specification()
            data["system"][option] = "unmanaged"
            with self.subTest(option=option), self.assertRaises(ValueError):
                configurator.validate_spec(data)

    def test_native_command_uses_canonical_staged_config_and_requested_base(self):
        data = self.specification()
        before = copy.deepcopy(data)
        workspace = Path("/evidence/paired-workspace")
        engine = Path("/isolated/engine")
        legacy = configurator.simulator_args(engine, workspace, data)
        self.assertFalse(any(arg.startswith("--salam-") for arg in legacy))
        self.assertEqual(data, before)
        data.update(builder="native", base_address="0x10024000")
        native = configurator.simulator_args(engine, workspace, data)
        self.assertIn("--salam-builder=native", native)
        self.assertIn(
            "--salam-config=/evidence/paired-workspace/benchmarks/sys_validation/gemm/config.yml",
            native,
        )
        self.assertIn("--salam-base-address=0x10024000", native)


class NativeIRControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/run_native_gemm.py"
        spec = importlib.util.spec_from_file_location("native_gemm_study_tests", path)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def test_actual_engine_module_parse_panic_is_the_expected_control(self):
        self.assertTrue(
            self.module.is_engine_ir_rejection(
                "src/hwacc/llvm_interface.cc:672: panic: Error reading Module\\n"
                "Program aborted at tick 102024000\\n"
            )
        )

    def test_unrelated_failure_is_not_a_valid_ir_control(self):
        for diagnostic in (
            "ValueError: could not parse input",
            "src/hwacc/llvm_interface.cc:672: panic: Error reading Module",
            "src/another_module.cc:2: panic: Error reading Module\\n"
            "Program aborted at tick 100",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.module.is_engine_ir_rejection(diagnostic))


if __name__ == "__main__":
    unittest.main()
