"""GUI model tests; these do not claim a simulator run."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from salam_workbench.gui_editor import (
    build_gui_request, discover_profile_periods, extract_components, render_document,
)
from salam_workbench.fu_capability import MARKER, REQUIRED_SOURCE_FILES


class GuiEditorTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "acc_cluster": [
                {"Name": "gemm_clstr"},
                {"DMA": [{"Name": "dma", "Type": "NonCoherent",
                          "MaxReqSize": 64, "BufferSize": 128,
                          "PIOMaster": "LocalBus", "InterruptNum": 95}]},
                {"Accelerator": [{"Name": "Top", "IrPath": "benchmarks/sys_validation/gemm/hw/top.ll",
                                  "PIOSize": 25, "PIOMaster": "LocalBus",
                                  "InterruptNum": 68, "LocalSlaves": "LocalBus"}]},
                {"Accelerator": [{"Name": "gemm", "IrPath": "benchmarks/sys_validation/gemm/hw/gemm.ll",
                                  "PIOSize": 1, "PIOMaster": "LocalBus"},
                                 {"Var": [{"Name": "MATRIX1", "Type": "SPM", "Size": 32768,
                                           "Ports": 2, "ResetOnRead": True}]},
                                 {"Var": [{"Name": "MATRIX2", "Type": "SPM", "Size": 32768,
                                           "Ports": 2}]}]},
            ],
            "hw_config": {
                "name": "gemm_clstr", "top": None,
                "gemm": {
                    "instructions": {
                        "mul": {"functional_unit": 5, "functional_unit_limit": 0,
                                "opcode_num": 17, "runtime_cycles": 2}
                    },
                    "functional_units": {"integer_multiplier": {"cycles": 2, "limit": 0}},
                },
            },
        }
        cluster, components = extract_components(self.base)
        self.snapshot = {
            "cluster_name": cluster, "components": components,
            "hardware_target": "gemm",
            "functional_units": {"integer_multiplier": {"cycles": 3, "limit": 0}},
            "instructions": {"mul": {"runtime_cycles": 3, "functional_unit": "5"}},
            "base_address": "0x10120000", "alignment": 64,
            "system": {"mem-size": "2GB", "mem-type": "DDR3_1600_8x8",
                       "cpu-clock": "1GHz", "sys-clock": "500MHz"},
            "hardware_profile": {"model": "40nm_model", "period": "10ns",
                                 "profile": "default_profile", "fu_overrides": {}},
        }

    def request(self, snapshot=None):
        return build_gui_request(
            self.base, snapshot or self.snapshot,
            benchmark="benchmarks/sys_validation/gemm",
            engine_root="/home/example/configurator-engine",
            distro="Ubuntu-20.04",
            source_config_relative="benchmarks/sys_validation/gemm/config.yml",
            source_config_sha256="a" * 64,
        )

    def test_live_edits_preserve_two_accelerators_memory_and_hidden_fields(self):
        snapshot = deepcopy(self.snapshot)
        for item in snapshot["components"]:
            if item["type"] == "dma":
                item["buffer_size"] = 256
            if item["type"] == "memory" and item["name"] == "MATRIX1":
                item["ports"] = 3
            if item["type"] == "accelerator" and item["name"] == "gemm":
                item["pio_size"] = 5
        request = self.request(snapshot)
        self.assertEqual(request["action"], "apply_and_run")
        self.assertEqual(request["system"]["mem-size"], "2GB")
        self.assertEqual(request["hardware_profile"]["period"], "10ns")
        self.assertEqual(request["provenance"]["editor_snapshot"]["components"], snapshot["components"])
        doc = request["configuration_documents"][0]
        self.assertEqual(len([x for x in doc["acc_cluster"] if "Accelerator" in x]), 2)
        self.assertEqual(doc["acc_cluster"][1]["DMA"][0]["BufferSize"], 256)
        self.assertEqual(doc["acc_cluster"][1]["DMA"][0]["InterruptNum"], 95)
        gemm = doc["acc_cluster"][3]["Accelerator"]
        self.assertEqual(gemm[0]["PIOSize"], 5)
        self.assertEqual(gemm[1]["Var"][0]["Ports"], 3)
        self.assertTrue(gemm[1]["Var"][0]["ResetOnRead"])
        self.assertEqual(doc["hw_config"]["gemm"]["instructions"]["mul"]["runtime_cycles"], 3)
        self.assertEqual(doc["hw_config"]["gemm"]["instructions"]["mul"]["opcode_num"], 17)
        self.assertEqual(doc["hw_config"]["gemm"]["functional_units"]["integer_multiplier"]["cycles"], 3)
        self.assertEqual(self.base["acc_cluster"][1]["DMA"][0]["BufferSize"], 128)

    def test_nonzero_functional_unit_limit_is_rejected(self):
        snapshot = deepcopy(self.snapshot)
        snapshot["functional_units"]["integer_multiplier"]["limit"] = 2
        with self.assertRaisesRegex(ValueError, "Nonzero FU limits"):
            self.request(snapshot)

    def test_capable_source_exports_fu_capacity_and_profile_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = Path(tmp)
            hashes = {}
            for name in REQUIRED_SOURCE_FILES:
                path = engine / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("// SALAM_FU_SCHEDULER_V1\n" if name.endswith(
                    ("fu_scheduling_pool.hh", "llvm_interface.cc")) else "// synthetic\n")
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            marker = engine / MARKER
            marker.write_text(json.dumps({
                "schema_version": 1, "capability": "salam_fu_scheduler_v1",
                "scope": "scalar_compute", "semantics": "nonpipelined_issue_to_completion",
                "zero_limit": "unlimited", "source_files": hashes}))
            snapshot = deepcopy(self.snapshot)
            snapshot["functional_units"]["integer_multiplier"]["limit"] = 2
            snapshot["hardware_profile"]["fu_overrides"] = {
                "integer_multiplier": {"limit": "2"}}
            request = build_gui_request(
                self.base, snapshot, benchmark="benchmarks/sys_validation/gemm",
                engine_root="/linux-only/fu-scheduling-engine", distro="Ubuntu-20.04",
                source_config_relative="benchmarks/sys_validation/gemm/config.yml",
                source_config_sha256="a" * 64,
                capability_source_root=engine)
            self.assertEqual(request["engine_root"], "/linux-only/fu-scheduling-engine")
            self.assertEqual(request["configuration_documents"][0]["hw_config"]
                             ["gemm"]["functional_units"]["integer_multiplier"]["limit"], 2)
            self.assertEqual(request["hardware_profile"]["fu_overrides"]
                             ["integer_multiplier"]["limit"], 2)

    def test_gui_only_metadata_moves_to_explicit_selected_profile(self):
        base = deepcopy(self.base)
        base["global"] = {"memory": {"base_address": "0x10120000", "alignment": 64}}
        base["hw_config"]["gemm"]["cycle_time"] = "10ns"
        doc = render_document(base, self.snapshot)
        self.assertNotIn("global", doc)
        self.assertNotIn("cycle_time", doc["hw_config"]["gemm"])
        base["hw_config"]["gemm"]["cycle_time"] = "1ns"
        edited = render_document(base, self.snapshot)
        self.assertNotIn("cycle_time", edited["hw_config"]["gemm"])
        request = build_gui_request(
            base, self.snapshot, benchmark="benchmarks/sys_validation/gemm",
            engine_root="/home/example/configurator-engine", distro="Ubuntu-20.04",
            source_config_relative="benchmarks/sys_validation/gemm/config.yml",
            source_config_sha256="a" * 64)
        self.assertEqual(request["hardware_profile"]["period"], "10ns")
        self.assertEqual(base["hw_config"]["gemm"]["cycle_time"], "1ns")
        with self.assertRaisesRegex(ValueError, "unhandled fields"):
            render_document({**base, "global": {"memory": {}, "secret": "ignored"}},
                            self.snapshot)

    def test_profile_periods_discovered_from_selected_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = (root / "benchmarks/sys_validation/gemm/configs/hw_interface/"
                      "functional_units/test_model/2ns/default_profile")
            folder.mkdir(parents=True)
            self.assertEqual(discover_profile_periods(
                root, "benchmarks/sys_validation/gemm", "test_model",
                "default_profile"), ["2ns"])
            self.assertEqual(discover_profile_periods(
                root, "benchmarks/sys_validation/gemm", "test_model",
                "missing_profile"), [])
            with self.assertRaisesRegex(ValueError, "Invalid hardware model"):
                discover_profile_periods(
                    root, "benchmarks/sys_validation/gemm", "../escape",
                    "default_profile")

    def test_alignment_other_than_64_is_rejected(self):
        snapshot = deepcopy(self.snapshot)
        snapshot["alignment"] = 128
        with self.assertRaisesRegex(ValueError, "fixed 64-byte"):
            self.request(snapshot)

    def test_flattened_accelerators_are_rejected_before_loss(self):
        flattened = deepcopy(self.base)
        flattened["acc_cluster"][2]["Accelerator"].append(
            {"Name": "second", "IrPath": "benchmarks/sys_validation/gemm/hw/second.ll",
             "PIOSize": 1})
        with self.assertRaisesRegex(ValueError, "Duplicate accelerator fields"):
            extract_components(flattened)


if __name__ == "__main__":
    unittest.main()
