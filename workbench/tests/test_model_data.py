"""Source-derived 40nm coefficient fixture; no simulator or old agents run.

Rows copied from salam_config/data/power_model_40nm.yaml, SHA-256
167180b86c8afad21e0a19137c4fe7ceea5a430494e23a361d86d01c4f9d5ca5.
The fixture is deliberately a subset, not a second characterization source.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from salam_workbench.model_data import (
    ASSET, ModelDataError, convert_to_si, load_model_inventory, model_estimate,
)

FIXTURE = {
    "metadata": {
        "technology_node": "40nm", "source": "Synopsys DesignWare IP Library",
        "supported_cycle_times": [1, 2, 3, 4, 5, 6, 10],
        "units": {"power": "mW", "energy": "pJ", "time": "ns", "area": "um^2"},
    },
    "functional_units": {
        "integer_multiplier": {
            "enum_value": 2, "description": "32-bit integer multiplier",
            "default_cycles": 1, "instructions": ["mul", "sdiv", "udiv"],
            "timing": {
                "5ns": {"int_power": 0.6866739, "switch_power": 1.038409,
                        "dyn_power": 1.725082, "dyn_energy": 8.625412,
                        "leak_power": 0.04817683, "area": 4595.0, "critical_path": 4.17},
                "10ns": {"int_power": 0.3459049, "switch_power": 0.5337095,
                         "dyn_power": 0.8796144, "dyn_energy": 8.796144,
                         "leak_power": 0.04817683, "area": 4595.0, "critical_path": 4.9},
            },
        },
        "bit_register": {
            "enum_value": 0, "description": "Bit register for temporary storage",
            "default_cycles": 1, "per_bit": True,
            "timing": {"1ns": {"int_power": 5.535310e-4, "switch_power": 1.800732e-4,
                               "dyn_power": 5.535310e-4, "dyn_energy": 5.535310e-3,
                               "leak_power": 7.358945e-5, "area": 5.981433}},
        },
    },
    "instruction_mapping": {"mul": "integer_multiplier", "sdiv": "integer_multiplier"},
}


class ModelDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="salam-model-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.asset = self.root / ASSET
        self.asset.parent.mkdir(parents=True)
        self.data = copy.deepcopy(FIXTURE)
        self.write()

    def write(self):
        self.asset.write_text(yaml.safe_dump(self.data), encoding="utf-8")

    def lookup(self, **kwargs):
        defaults = {"instruction": "mul", "cycle_time_ns": 10}
        defaults.update(kwargs)
        return model_estimate(self.root, **defaults)

    def test_exact_source_value_provenance_and_scope(self):
        result = self.lookup()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["kind"], "model_coefficients")
        self.assertFalse(result["characterization_verified"])
        self.assertEqual(result["source_confidence"], "repository_claim_unverified")
        self.assertEqual(result["asset"]["sha256"], hashlib.sha256(self.asset.read_bytes()).hexdigest())
        self.assertEqual(result["declared_model"]["source_claim"], FIXTURE["metadata"]["source"])
        self.assertEqual(result["coefficients"]["dyn_energy"]["value"], 8.796144)
        self.assertEqual(result["coefficients"]["area"]["unit"], "um^2")
        self.assertIsNone(result["declared_model"]["voltage"])
        self.assertNotIn("total_power", result)
        self.assertNotIn("operation_count", result)
        json.dumps(result, allow_nan=False)

    def test_inventory_counts_and_hash_change(self):
        before = load_model_inventory(self.root)
        self.assertEqual(before["counts"], {"functional_units": 2, "instruction_mappings": 2, "timing_rows": 3})
        self.data["functional_units"]["integer_multiplier"]["timing"]["10ns"]["area"] = 4596
        self.write()
        after = load_model_inventory(self.root)
        self.assertNotEqual(before["asset"]["sha256"], after["asset"]["sha256"])

    def test_period_selection_has_no_fallback_or_interpolation(self):
        for period in (3, 7, 10.5):
            with self.subTest(period=period):
                result = self.lookup(cycle_time_ns=period)
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["coefficients"])
        self.assertEqual(self.lookup(cycle_time_ns=10.0)["status"], "available")
        self.assertEqual(self.lookup(cycle_time_ns=5)["coefficients"]["dyn_energy"]["value"], 8.625412)

    def test_missing_instruction_does_not_default_to_register(self):
        result = self.lookup(instruction="not_an_instruction")
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["functional_unit"])

    def test_per_bit_scope_and_arithmetic_observations_preserve_data(self):
        result = model_estimate(self.root, functional_unit="bit_register", cycle_time_ns=1)
        self.assertEqual(result["scope"], "per_bit")
        self.assertTrue(result["per_bit_declared"])
        self.assertEqual(len(result["warnings"]), 2)
        self.assertEqual(result["coefficients"]["dyn_energy"]["value"], 0.00553531)
        self.assertEqual(result["coefficients"]["critical_path"]["status"], "unknown")
        self.assertEqual(result["status"], "available")  # raw coefficients, not integrated energy

    def test_unit_conversion_is_only_dimensional_scaling(self):
        self.assertEqual(convert_to_si(1, "mW"), {"value_decimal": "0.001", "unit": "W"})
        self.assertEqual(convert_to_si(1, "pJ"), {"value_decimal": "1E-12", "unit": "J"})
        self.assertEqual(convert_to_si(1, "ns"), {"value_decimal": "1E-9", "unit": "s"})
        self.assertEqual(convert_to_si(4595, "um^2"), {"value_decimal": "4.595E-9", "unit": "m^2"})
        with self.assertRaises(ModelDataError):
            convert_to_si(1, "mW_per_access")

    def test_missing_coefficient_is_unknown_not_zero(self):
        del self.data["functional_units"]["integer_multiplier"]["timing"]["10ns"]["area"]
        self.write()
        result = self.lookup()
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["coefficients"]["area"]["value"])
        self.assertEqual(result["coefficients"]["dyn_energy"]["value"], 8.796144)

    def test_invalid_numeric_values_are_unknown(self):
        for value in (True, -1, float("nan"), float("inf"), "4595"):
            with self.subTest(value=repr(value)):
                self.data["functional_units"]["integer_multiplier"]["timing"]["10ns"]["area"] = value
                self.write()
                result = self.lookup()
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["coefficients"]["area"]["value"])
                json.dumps(result, allow_nan=False)

    def test_missing_asset_is_unknown(self):
        result = model_estimate(self.root / "absent-engine", instruction="mul", cycle_time_ns=10)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["asset"]["sha256"])

    def test_missing_or_unsupported_units_fail(self):
        for units in (None, {"power": "W"}, dict(FIXTURE["metadata"]["units"], energy="nJ")):
            with self.subTest(units=units):
                self.data["metadata"]["units"] = units
                self.write()
                with self.assertRaises(ModelDataError):
                    self.lookup()

    def test_missing_metadata_does_not_invent_technology(self):
        del self.data["metadata"]["technology_node"]
        self.write()
        with self.assertRaises(ModelDataError):
            self.lookup()

    def test_bad_mapping_is_rejected(self):
        self.data["instruction_mapping"]["mul"] = "missing_fu"
        self.write()
        with self.assertRaises(ModelDataError):
            load_model_inventory(self.root)

    def test_duplicate_yaml_key_is_rejected(self):
        with self.asset.open("a", encoding="utf-8") as handle:
            handle.write("\nmetadata: {}\n")
        with self.assertRaises(ModelDataError):
            self.lookup()

    def test_bad_selectors_or_periods_are_rejected(self):
        for period in (None, True, 0, -1, float("nan"), "10"):
            with self.subTest(period=repr(period)):
                with self.assertRaises(ModelDataError):
                    self.lookup(cycle_time_ns=period)
        with self.assertRaises(ModelDataError):
            model_estimate(self.root, cycle_time_ns=10)
        with self.assertRaises(ModelDataError):
            self.lookup(functional_unit="integer_multiplier")

    def test_fu_metadata_does_not_synthesize_defaults(self):
        for field, value in (("default_cycles", True), ("enum_value", float("nan")),
                             ("description", {}), ("per_bit", "yes")):
            with self.subTest(field=field):
                self.data = copy.deepcopy(FIXTURE)
                self.data["functional_units"]["integer_multiplier"][field] = value
                self.write()
                with self.assertRaises(ModelDataError):
                    self.lookup()
    def test_file_is_unchanged_after_lookup(self):
        before = self.asset.read_bytes()
        self.lookup()
        load_model_inventory(self.root)
        self.assertEqual(self.asset.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
