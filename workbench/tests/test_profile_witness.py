import tempfile
from pathlib import Path
import unittest

from salam_workbench.profile_witness import witness_profiles


REGISTRY = '_FU_REGISTRY = {"adder": Adder, "multiplier": Multiplier}\n'
FIELDS = {
    "power_units": ('String', '"mW"'),
    "energy_units": ('String', '"pJ"'),
    "time_units": ('String', '"ns"'),
    "area_units": ('String', '"um^2"'),
    "fu_latency": ("UInt32", "5"),
    "internal_power": ("Float", "0.009743773"),
    "switch_power": ("Float", "0.007400587"),
    "dynamic_power": ("Float", "0.001800732"),
    "dynamic_energy": ("Float", "0.009003937"),
    "leakage_power": ("Float", "7.395312e-05"),
    "area": ("Float", "5.981433"),
    "path_delay": ("Float", "1.75"),
}
VALUES = {
    "power_units": "mW", "energy_units": "pJ", "time_units": "ns",
    "area_units": "um^2", "fu_latency": "5",
    "internal_power": "0.009743773", "switch_power": "0.007400587",
    "dynamic_power": "0.001800732", "dynamic_energy": "0.009003937",
    "leakage_power": "7.395312e-05", "area": "5.981433",
    "path_delay": "1.75",
}


class ProfileWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "engine"
        registry = self.root / "configs/SALAM/HWAccConfig.py"
        defaults = self.root / "src/hwacc/FunctionalUnits.py"
        registry.parent.mkdir(parents=True)
        defaults.parent.mkdir(parents=True)
        registry.write_text(REGISTRY, encoding="utf-8")
        self.defaults = defaults
        self._write_source()
        self.ini = Path(self.temp.name) / "config.ini"
        self._write_ini()

    def _write_source(self, integer_power=False):
        lines = []
        for class_name in ("Adder", "Multiplier"):
            lines.append("class " + class_name + ":")
            for field, (param_type, literal) in FIELDS.items():
                if integer_power and field == "internal_power":
                    param_type = "UInt32"
                lines.append("    " + field + " = Param." + param_type +
                             "(" + literal + ", 'fixture')")
        self.defaults.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_ini(self, overrides=None, omit=None, accelerators=("acc0", "acc1")):
        overrides = overrides or {}
        lines = []
        for accelerator in accelerators:
            for fu in ("adder", "multiplier"):
                section = ("system.cluster." + accelerator +
                           ".hw_interface.functional_units." + fu)
                if section == omit:
                    continue
                lines.append("[" + section + "]")
                for field, default in VALUES.items():
                    value = overrides.get((section, field), default)
                    lines.append(field + "=" + value)
                lines.append("")
        self.ini.write_text("\n".join(lines), encoding="utf-8")

    def test_all_defaults_reach_each_accelerator(self):
        result = witness_profiles(self.root, self.ini)
        self.assertEqual(result["state"], "passed")
        self.assertEqual(len(result["checks"]), 48)
        self.assertFalse(result["issues"])
        self.assertFalse(result["model_claims"]["measured_power_or_energy"])
        self.assertEqual(len(result["source_hashes"]), 3)

    def test_original_uint32_fractional_default_and_truncation_fail(self):
        self._write_source(integer_power=True)
        section = "system.cluster.acc0.hw_interface.functional_units.adder"
        self._write_ini(overrides={(section, "internal_power"): "0"})
        result = witness_profiles(self.root, self.ini)
        kinds = {issue["kind"] for issue in result["issues"]}
        self.assertEqual(result["state"], "failed")
        self.assertIn("profile_mismatch", kinds)
        self.assertIn("lossy_source_param_type", kinds)
        self.assertFalse(result["model_claims"]["coefficient_transport_verified"])

    def test_explicit_parameter_override_takes_precedence(self):
        section = "system.cluster.acc0.hw_interface.functional_units.adder"
        self._write_ini(overrides={(section, "internal_power"): "0.25"})
        result = witness_profiles(
            self.root, self.ini,
            parameter_overrides={section: {"internal_power": 0.25}})
        self.assertEqual(result["state"], "passed")
        check = next(c for c in result["checks"]
                     if c["section"] == section and c["field"] == "internal_power")
        self.assertEqual(check["origin"], "explicit_parameter_override")
        self.assertEqual(check["source_default"], "0.009743773")

    def test_missing_functional_unit_fails(self):
        section = "system.cluster.acc1.hw_interface.functional_units.multiplier"
        self._write_ini(omit=section)
        result = witness_profiles(self.root, self.ini)
        self.assertEqual(result["state"], "failed")
        self.assertIn("missing_functional_unit",
                      {issue["kind"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
