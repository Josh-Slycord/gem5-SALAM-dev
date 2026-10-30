"""Contract tests use synthetic engine sources; simulator evidence is separate."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.config_contract import analyze_configuration
from salam_workbench.fu_capability import MARKER, REQUIRED_SOURCE_FILES

YAML = """acc_cluster:
  - Name: demo_clstr
  - DMA:
      - Name: dma
        Type: NonCoherent
        BufferSize: 128
        MaxReqSize: 64
        PIOMaster: LocalBus
        InterruptNum: 95
  - Accelerator:
      - Name: Top
        IrPath: benchmarks/sys_validation/demo/hw/top.ll
        PIOSize: 25
        PIOMaster: LocalBus
        LocalSlaves: LocalBus
        Debug: false
  - Accelerator:
      - Name: demo
        IrPath: benchmarks/sys_validation/demo/hw/demo.ll
        PIOSize: 1
        PIOMaster: LocalBus
      - Var:
          - Name: DATA
            Type: SPM
            Size: 128
            Ports: 2
            ReadyMode: true
hw_config:
  top:
  demo:
    instructions:
      add:
        functional_unit: 1
        functional_unit_limit: 0
        opcode_num: 13
        runtime_cycles: 2
"""


class ConfigContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "benchmarks/sys_validation/demo/config.yml"
        self._write(self.config, YAML)
        self._write(
            self.root / "configs/SALAM/HWAccConfig.py",
            "_FU_REGISTRY = {'integer_adder': IntegerAdder}\n"
            "_INST_REGISTRY = {'add': Add}\n",
        )
        self._write(
            self.root / "src/hwacc/CycleCounts.py",
            "class CycleCounts:\n    add = Param.UInt32(1, 'cycles')\n",
        )
        self._write(
            self.root / "src/hwacc/FunctionalUnits.py",
            "class IntegerAdder:\n    enum_value = Param.UInt32(1, 'id')\n",
        )
        self._write(
            self.root / "src/hwacc/LLVMRead/src/instruction.hh",
            "bool hasFunctionalUnit() { return false; }\n",
        )

    @staticmethod
    def _write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def analyze(self, **kwargs):
        return analyze_configuration(self.config, self.root, **kwargs)

    def test_structural_contract_is_generic_and_source_backed(self):
        result = self.analyze(base_address=0x10120000)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(result["components"]["clusters"][0]["name"], "demo_clstr")
        self.assertEqual(
            result["expected_effective"][
                "system.demo_clstr.demo.hw_interface.cycle_counts"
            ]["add"],
            "2",
        )
        self.assertEqual(
            result["expected_effective"]["system.demo_clstr.dma"]["pio_addr"],
            str(0x10120000),
        )
        self.assertEqual(
            result["expected_effective"]["system.demo_clstr.data"]["range"],
            "{}:{}".format(0x101200C0, 0x101200C0 + 128),
        )
        self.assertEqual(result["witnesses"]["generated"]["state"], "not_checked")
        self.assertEqual(result["required_actions"]["rebuild_simulator"], None)

    def test_rejects_gui_string_fu_and_dormant_limit(self):
        self._write(
            self.config,
            YAML.replace(
                "functional_unit: 1", "functional_unit: integer_adder"
            ).replace("functional_unit_limit: 0", "functional_unit_limit: 2"),
        )
        result = self.analyze()
        self.assertFalse(result["valid"])
        self.assertIn("invalid_uint32", {issue["code"] for issue in result["issues"]})
        self.assertIn(
            "inactive_fu_limit", {issue["code"] for issue in result["issues"]}
        )

    def test_capable_sources_accept_fu_capacity_but_not_instruction_limit(
        self,
    ):
        hashes = {}
        for name in REQUIRED_SOURCE_FILES:
            path = self.root / name
            self._write(
                path,
                "// SALAM_FU_SCHEDULER_V1\n"
                if name.endswith(("fu_scheduling_pool.hh", "llvm_interface.cc"))
                else "// synthetic source\n",
            )
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self._write(
            self.root / MARKER,
            json.dumps(
                {
                    "schema_version": 1,
                    "capability": "salam_fu_scheduler_v1",
                    "scope": "scalar_compute",
                    "semantics": "nonpipelined_issue_to_completion",
                    "zero_limit": "unlimited",
                    "source_files": hashes,
                }
            ),
        )
        self._write(
            self.config,
            YAML
            + ("    functional_units:\n" "      integer_adder:\n" "        limit: 2\n"),
        )
        result = self.analyze()
        self.assertTrue(result["valid"], result["issues"])
        self.assertTrue(result["fu_scheduler_capability"]["supported"])
        self.assertEqual(
            result["expected_effective"][
                "system.demo_clstr.demo.hw_interface.functional_units.integer_adder"
            ]["limit"],
            "2",
        )
        self._write(
            self.config,
            self.config.read_text().replace(
                "functional_unit_limit: 0", "functional_unit_limit: 2"
            ),
        )
        result = self.analyze()
        self.assertIn("inactive_fu_limit", {item["code"] for item in result["issues"]})

    def test_rejects_silent_configuration_fields(self):
        self._write(
            self.config,
            YAML.replace(
                "runtime_cycles: 2", "runtime_cycles: 2\n        new_magic: 4"
            ),
        )
        result = self.analyze()
        self.assertFalse(result["valid"])
        self.assertIn("unconsumed_field", {issue["code"] for issue in result["issues"]})

    def test_rejects_duplicate_yaml_keys(self):
        self._write(
            self.config,
            YAML.replace(
                "        runtime_cycles: 2",
                "        runtime_cycles: 2\n        runtime_cycles: 3",
            ),
        )
        self.assertIn(
            "contract_error",
            {issue["code"] for issue in self.analyze()["issues"]},
        )

    def test_multi_document_profile_requires_separate_runtime_witness(self):
        self._write(self.config, YAML + "\n---\nhw_config: {}\n")
        self.assertIn(
            "multi_document_profile_unverified",
            {issue["code"] for issue in self.analyze()["issues"]},
        )

    def test_malformed_instruction_block_returns_issue_instead_of_crashing(
        self,
    ):
        self._write(
            self.config,
            YAML.replace(
                "    instructions:\n      add:",
                "    instructions: []\n    unsupported:\n      add:",
            ),
        )
        result = self.analyze()
        self.assertFalse(result["valid"])
        self.assertTrue(result["issues"])

    def test_rejects_address_space_overflow(self):
        result = self.analyze(base_address=0x13FFFF00)
        self.assertFalse(result["valid"])
        self.assertIn(
            "address_range_exceeded",
            {issue["code"] for issue in result["issues"]},
        )

    def test_registerbank_connection_port_count_is_not_silently_accepted(self):
        self._write(
            self.config,
            YAML.replace(
                "            Type: SPM\n            Size: 128\n            Ports: 2\n            ReadyMode: true",
                "            Type: RegisterBank\n            Size: 128\n            Connections: demo:2",
            ),
        )
        self.assertIn(
            "unconsumed_register_ports",
            {issue["code"] for issue in self.analyze()["issues"]},
        )

    def test_external_config_requires_active_staged_parser_consumer(self):
        relative = "configs/workbench_profile.yml"
        config = YAML.split("hw_config:")[0].replace(
            "        IrPath: benchmarks/sys_validation/demo/hw/demo.ll\n",
            "        IrPath: benchmarks/sys_validation/demo/hw/demo.ll\n"
            "        ConfigPath: " + relative + "\n",
        )
        self._write(self.config, config + "hw_config:\n  top:\n  demo:\n")
        self._write(
            self.root / relative,
            "hw_config:\n  demo:\n    instructions:\n      add:\n"
            "        runtime_cycles: 5\n",
        )
        without = self.analyze(generated_root=self.root)
        self.assertIn(
            "unconsumed_field", {issue["code"] for issue in without["issues"]}
        )
        self._write(
            self.root / "SALAM-Configurator/parser.py",
            "CONFIGPATH_CONSUMER_VERSION = 1\n"
            "def connect(M5_Path, deviceDict):\n"
            "    configPath = _workbench_config_path(M5_Path, deviceDict['ConfigPath'])\n",
        )
        prebuild = self.analyze()
        self.assertTrue(prebuild["valid"], prebuild["issues"])
        self.assertEqual(prebuild["witnesses"]["generated"]["state"], "not_checked")
        with_adapter = self.analyze(generated_root=self.root)
        self.assertNotIn(
            "unconsumed_field",
            {issue["code"] for issue in with_adapter["issues"]},
        )
        self.assertEqual(
            with_adapter["expected_effective"][
                "system.demo_clstr.demo.hw_interface.cycle_counts"
            ]["add"],
            "5",
        )
        self.assertEqual(
            with_adapter["external_config_paths"]["demo"]["relative_path"],
            relative,
        )
        self.assertIn(str(self.root / relative), with_adapter["config_paths"])

    def test_generated_and_effective_witnesses_are_independent(self):
        root = self.root
        self._write(
            root / "configs/SALAM/generated/demo_build.py",
            "def builddemo_clstr(options, system, clstr): pass\n"
            "def makeHWAcc(args, system): pass\n"
            "def config():\n"
            "    ir = '"
            + str(root / "benchmarks/sys_validation/demo/hw/top.ll")
            + "'\n"
            "    config = '" + str(self.config) + "'\n"
            "    ir = '"
            + str(root / "benchmarks/sys_validation/demo/hw/demo.ll")
            + "'\n"
            "    config = '" + str(self.config) + "'\n",
        )
        self._write(
            root / "configs/SALAM/generated/fs_demo_build.py",
            "import demo_build\n",
        )
        self._write(
            root / "benchmarks/sys_validation/demo/demo_clstr_hw_defines.h",
            "#define DMA_Flags 0x10120000\n#define DMA_RdAddr 0x10120001\n"
            "#define DMA_WrAddr 0x10120009\n#define DMA_CopyLen 0x10120011\n"
            "#define TOP 0x10120040\n#define DEMO 0x10120080\n#define DATA 0x101200c0\n",
        )
        prelim = self.analyze(
            generated_root=root,
            system_name="demo_build",
            base_address=0x10120000,
        )
        self.assertEqual(prelim["witnesses"]["generated"]["state"], "passed")
        ini = root / "config.ini"
        self._write(
            ini,
            "".join(
                "[{}]\n{}\n".format(
                    section,
                    "".join(
                        "{}={}\n".format(key, value) for key, value in fields.items()
                    ),
                )
                for section, fields in prelim["expected_effective"].items()
            ),
        )
        result = self.analyze(
            generated_root=root,
            effective_config=ini,
            system_name="demo_build",
            base_address=0x10120000,
        )
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(result["witnesses"]["effective"]["state"], "passed")
        self._write(ini, ini.read_text().replace("add=2", "add=9"))
        wrong = self.analyze(
            generated_root=root,
            effective_config=ini,
            system_name="demo_build",
            base_address=0x10120000,
        )
        self.assertFalse(wrong["valid"])
        self.assertEqual(wrong["witnesses"]["effective"]["state"], "failed")


if __name__ == "__main__":
    unittest.main()
