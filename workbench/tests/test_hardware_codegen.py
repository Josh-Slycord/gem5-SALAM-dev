"""Safety and failure-contract tests for isolated hardware generation."""
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.hardware_codegen import (
    FLOAT_FIELDS,
    _class_patch,
    generate_hardware_code,
)


class HardwareCodegenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        self.engine.mkdir()
        self.output = self.root / "evidence"

    def test_rejects_unsafe_selection_before_creating_evidence(self):
        with self.assertRaises(ValueError):
            generate_hardware_code(self.engine, "../gemm", self.output)
        self.assertFalse(self.output.exists())

    def test_refuses_to_stage_inside_source_engine(self):
        with self.assertRaises(ValueError):
            generate_hardware_code(self.engine, "gemm", self.engine / "evidence")
        self.assertFalse((self.engine / "evidence").exists())

    def test_missing_generator_retains_failed_receipt(self):
        result = generate_hardware_code(self.engine, "gemm", self.output)
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["valid"])
        self.assertFalse(result["simulation_ready"])
        self.assertIn("HWProfileGenerator.py", result["errors"][0])
        saved = json.loads((self.output / "hardware-codegen.json").read_text())
        self.assertEqual(saved["state"], "failed")
        self.assertFalse((self.engine / "src").exists())

    def test_staged_template_preserves_fu_activity_interface(self):
        source = "\n".join(
            [r"\t" + name + " = Param.UInt32(" for name in FLOAT_FIELDS]
            + [
                "self.inst_dict['instructions'][inst_name]['functional_unit_limit']",
                r'self.base_header_file.write("\t\tuint64_t _in_use;\n\n")',
                r'self.base_header_file.write("\t\tbool is_available() { return (_in_use >= _available); }\n")',
            ]
        )
        patched = _class_patch(source)
        self.assertIn(r"\t\tuint64_t _in_use = 0;", patched)
        self.assertIn("get_in_use() { return _in_use; }", patched)
        self.assertIn(".get('functional_unit_limit', 0)", patched)
        for name in FLOAT_FIELDS:
            self.assertIn(r"\t" + name + " = Param.Float(", patched)

    def test_capable_template_keeps_corrected_capacity_checks(self):
        source = "\n".join(
            [r"\t" + name + " = Param.UInt32(" for name in FLOAT_FIELDS]
            + [
                "self.inst_dict['instructions'][inst_name]['functional_unit_limit']",
                r'self.base_header_file.write("\t\tuint64_t _in_use = 0;\n\n")',
                r'self.base_header_file.write("\t\tuint64_t get_in_use() { return _in_use; }\n")',
                r'self.base_header_file.write("\t\tbool is_available() { return (_available == 0 || _in_use < _available); }\n")',
                "FU occupancy underflow",
            ]
        )
        patched = _class_patch(source, capable=True)
        self.assertIn("_available == 0 || _in_use < _available", patched)
        self.assertEqual(patched.count("get_in_use()"), 1)
        self.assertIn(".get('functional_unit_limit', 0)", patched)
        with self.assertRaisesRegex(ValueError, "exact scheduler repair"):
            _class_patch(
                source.replace(
                    "_available == 0 || _in_use < _available",
                    "_in_use >= _available",
                ),
                capable=True,
            )

    def test_profile_alias_mismatch_stops_before_generator_runs(self):
        for filename in (
            "HWProfileGenerator.py",
            "SALAMClassGenerator.py",
            "SALAMArgs.py",
        ):
            (self.engine / filename).write_text("# fixture source\n")
        profile = (
            self.engine / "benchmarks/sys_validation/gemm/configs/"
            "hw_interface/functional_units/40nm_model/5ns/"
            "default_profile/integer_adder"
        )
        profile.mkdir(parents=True)
        (profile / "integer_adder.yml").write_text(
            "functional_unit:\n  parameters:\n    alias: wrong_unit\n"
        )
        result = generate_hardware_code(self.engine, "gemm", self.output)
        self.assertEqual(result["state"], "failed")
        self.assertIn("alias disagrees", result["errors"][0])
        self.assertFalse((self.output / "generator.stdout").exists())


if __name__ == "__main__":
    unittest.main()
