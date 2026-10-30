"""Legacy GUI syntax import never edits its source YAML."""

import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.configuration_import import import_configuration

SOURCE = """acc_cluster: []
hw_config:
  demo:
    ignored_but_preserved: keep_me
    instructions:
      and:
        functional_unit: bitwise_operations
        functional_unit_limit: 7
        runtime_cycles: 2
      switch:
        functional_unit: 0
"""


class LegacyGuiImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.yml"
        self.write(self.config, SOURCE)
        self.write(
            self.root / "configs/SALAM/HWAccConfig.py",
            "_FU_REGISTRY = {'bitwise_operations': BitwiseOperations}\n"
            "_INST_REGISTRY = {'and_inst': AndInst, 'switch_inst': SwitchInst}\n",
        )
        self.write(
            self.root / "src/hwacc/FunctionalUnits.py",
            "class BitwiseOperations:\n    enum_value = Param.UInt32(4, 'id')\n",
        )

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_translates_symbolic_fu_and_instruction_aliases_without_dropping_fields(
        self,
    ):
        original = self.config.read_bytes()
        result = import_configuration(self.config, self.root)
        instructions = result["documents"][0]["hw_config"]["demo"]["instructions"]
        self.assertEqual(list(instructions), ["and_inst", "switch_inst"])
        self.assertEqual(instructions["and_inst"]["functional_unit"], 4)
        self.assertEqual(instructions["and_inst"]["functional_unit_limit"], 7)
        self.assertEqual(
            result["documents"][0]["hw_config"]["demo"]["ignored_but_preserved"],
            "keep_me",
        )
        self.assertEqual(len(result["transformations"]), 3)
        self.assertEqual(self.config.read_bytes(), original)
        json.dumps(result)

    def test_rejects_alias_canonical_collision(self):
        self.write(
            self.config,
            SOURCE.replace(
                "      switch:",
                "      and_inst:\n        functional_unit: 0\n      switch:",
            ),
        )
        with self.assertRaisesRegex(ValueError, "collision"):
            import_configuration(self.config, self.root)

    def test_rejects_unknown_fu_and_instruction(self):
        self.write(self.config, SOURCE.replace("bitwise_operations", "imaginary_fu"))
        with self.assertRaisesRegex(ValueError, "Unknown symbolic functional unit"):
            import_configuration(self.config, self.root)
        self.write(self.config, SOURCE.replace("      switch:", "      sitofp:"))
        with self.assertRaisesRegex(ValueError, "Unknown instruction"):
            import_configuration(self.config, self.root)

    def test_rejects_duplicate_yaml_keys(self):
        self.write(
            self.config,
            SOURCE.replace(
                "        runtime_cycles: 2",
                "        runtime_cycles: 2\n        runtime_cycles: 3",
            ),
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            import_configuration(self.config, self.root)


if __name__ == "__main__":
    unittest.main()
