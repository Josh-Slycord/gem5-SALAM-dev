"""Discovery tests never execute a simulator or establish numerical coverage."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench.workbench_catalog import discover_benchmarks

CONFIG = """acc_cluster:
- Name: compute_clstr
- Accelerator:
  - Name: compute
    IrPath: hw/compute.ll
    PIOSize: 1
"""


class WorkbenchCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def workload(
        self,
        name="gemm",
        suite="sys_validation",
        config=CONFIG,
        build=True,
        profile=True,
    ):
        directory = self.root / "benchmarks" / suite / name
        directory.mkdir(parents=True)
        if config is not None:
            (directory / "config.yml").write_text(config, encoding="utf-8")
        if build:
            for relative in ("Makefile", "hw/Makefile", "sw/Makefile"):
                path = directory / relative
                path.parent.mkdir(exist_ok=True)
                path.write_text("all:\n\t@true\n", encoding="utf-8")
        if profile:
            (
                directory
                / "configs/hw_interface/functional_units/40nm_model/5ns/default_profile"
            ).mkdir(parents=True)
        return directory

    def test_real_paths_are_stable_and_no_simulation_is_claimed(self):
        self.workload()
        rows = discover_benchmarks(self.root)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["key"], "benchmarks/sys_validation/gemm")
        self.assertEqual(row["config_relative"], row["key"] + "/config.yml")
        self.assertTrue(row["can_configure"])
        self.assertTrue(row["can_run"])
        self.assertEqual(row["run_readiness"], "preflight_required")
        self.assertIn("not an independent", row["verification"])
        self.assertEqual(row["default_profile_periods"], ["5ns"])
        self.assertTrue(row["fixed_dataset_check_available"])
        self.assertEqual(row["fixed_dataset_runner"], "gemm")

    def test_known_fixed_dataset_coverage_does_not_transfer_to_editor(self):
        self.workload("bfs")
        row = discover_benchmarks(self.root)[0]
        self.assertTrue(row["fixed_dataset_check_available"])
        self.assertEqual(row["fixed_dataset_runner"], "regression")
        self.assertIn("arbitrary editor changes", row["fixed_dataset_check_scope"])
        self.assertIn("not an independent", row["verification"])

    def test_legacy_name_does_not_inherit_fixed_dataset_support(self):
        self.workload("bfs", suite="legacy")
        row = discover_benchmarks(self.root)[0]
        self.assertFalse(row["fixed_dataset_check_available"])

    def test_missing_config_is_disabled_with_reason(self):
        self.workload(config=None)
        row = discover_benchmarks(self.root)[0]
        self.assertFalse(row["can_configure"])
        self.assertFalse(row["can_run"])
        self.assertIsNone(row["config_relative"])
        self.assertIn("No config.yml", row["warnings"][0])

    def test_missing_build_inputs_allows_editing_but_not_run(self):
        self.workload(build=False)
        row = discover_benchmarks(self.root)[0]
        self.assertTrue(row["can_configure"])
        self.assertFalse(row["can_run"])
        self.assertEqual(row["run_readiness"], "missing_build_inputs")

    def test_missing_default_profile_does_not_claim_ready(self):
        self.workload(profile=False)
        row = discover_benchmarks(self.root)[0]
        self.assertTrue(row["can_configure"])
        self.assertFalse(row["can_run"])
        self.assertEqual(row["run_readiness"], "hardware_profile_required")

    def test_suite_root_config_is_visible_as_unsupported_layout(self):
        suite = self.root / "benchmarks/mobilenetv2"
        (suite / "hw").mkdir(parents=True)
        (suite / "sw").mkdir()
        (suite / "config.yml").write_text(CONFIG, encoding="utf-8")
        rows = discover_benchmarks(self.root)
        self.assertEqual([row["key"] for row in rows], ["benchmarks/mobilenetv2"])
        self.assertFalse(rows[0]["can_configure"])
        self.assertEqual(rows[0]["availability"], "unsupported_layout")

    def test_yaml_duplicate_keys_and_multiple_documents_are_disabled(self):
        self.workload("duplicate", config=CONFIG + "acc_cluster: []\n")
        self.workload("multiple", config=CONFIG + "---\n" + CONFIG)
        rows = discover_benchmarks(self.root)
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            all(row["availability"] == "invalid_configuration" for row in rows)
        )
        self.assertTrue(all(not row["can_run"] for row in rows))

    def test_ambiguous_yaml_names_are_not_silently_selected(self):
        directory = self.workload()
        (directory / "config.yaml").write_text(CONFIG, encoding="utf-8")
        row = discover_benchmarks(self.root)[0]
        self.assertEqual(row["availability"], "ambiguous_configuration")
        self.assertFalse(row["can_configure"])

    def test_symlinked_workload_and_source_are_disabled(self):
        original = self.workload()
        linked = original.parent / "linked"
        try:
            linked.symlink_to(original, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("This host cannot create local symlinks")
        other = self.workload("linked_config", config=None)
        (other / "config.yml").symlink_to(original / "config.yml")
        rows = {row["name"]: row for row in discover_benchmarks(self.root)}
        self.assertFalse(rows["linked"]["can_configure"])
        self.assertFalse(rows["linked_config"]["can_configure"])
        self.assertIsNone(rows["linked_config"]["config_relative"])

    def test_discovery_is_sorted_and_does_not_recurse_other_suites(self):
        self.workload("zeta")
        self.workload("alpha")
        self.workload("hidden", suite="some_other_suite")
        self.assertEqual(
            [row["name"] for row in discover_benchmarks(self.root)], ["alpha", "zeta"]
        )

    def test_discovery_rejects_silently_truncated_inventory(self):
        self.workload()
        with patch("salam_workbench.workbench_catalog.MAX_BENCHMARKS_PER_SUITE", 0):
            with self.assertRaisesRegex(ValueError, "discovery limit"):
                discover_benchmarks(self.root)


if __name__ == "__main__":
    unittest.main()
