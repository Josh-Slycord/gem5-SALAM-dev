"""Behavioral checks for staged ConfigPath support and provenance."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest

from salam_workbench.topology_adapter import adapt_staged_configpaths


PARSER_SOURCE = '''__version__ = "3.0.0.pre[1.0.0]"


class MiniParser:
    def path(self, M5_Path, configFile, deviceDict):
        configPath = configFile
        for deviceDict in [deviceDict]:
            if True:
                # if 'ConfigPath' in deviceDict:
                #     configPath = deviceDict['ConfigPath']
        return configPath
'''


class ConfigPathAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        self.stage = self.root / "stage"
        self.benchmark = "benchmarks/suite/custom"
        self.profile = "configs/workbench_profile.yml"
        self.ir = "benchmarks/suite/custom/hw/top.ll"
        for root in (self.engine, self.stage):
            parser = root / "SALAM-Configurator/parser.py"
            parser.parent.mkdir(parents=True)
            parser.write_text(PARSER_SOURCE)
        self.config = self.stage / self.benchmark / "config.yml"
        self.config.parent.mkdir(parents=True)
        self.source_profile = self.engine / self.profile
        self.source_profile.parent.mkdir(parents=True)
        self.source_profile.write_text(
            "hw_config:\n  top:\n    instructions:\n      add:\n        runtime_cycles: 3\n"
        )

    def config_text(self, profile=None):
        lines = [
            "acc_cluster:",
            "  - Name: custom",
            "  - Accelerator:",
            "      - Name: top",
            "        PIOSize: 64",
            "        IrPath: " + self.ir,
        ]
        if profile is not None:
            lines.append("        ConfigPath: " + profile)
        return "\n".join(lines) + "\n"

    def test_per_accelerator_yaml_is_staged_and_executed_by_patched_parser(self):
        self.config.write_text(self.config_text(self.profile))
        original = (self.engine / "SALAM-Configurator/parser.py").read_bytes()
        receipt_path = self.root / "adapter.json"
        result = adapt_staged_configpaths(self.engine, self.stage, self.benchmark,
                                          receipt_path=receipt_path)
        self.assertEqual(result["state"], "patched")
        self.assertEqual((self.engine / "SALAM-Configurator/parser.py").read_bytes(), original)
        self.assertEqual((self.stage / self.profile).read_bytes(), self.source_profile.read_bytes())
        self.assertIn("CONFIGPATH_CONSUMER_VERSION = 1",
                      (self.stage / "SALAM-Configurator/parser.py").read_text())
        self.assertIn("ConfigPath", result["parser"]["unified_diff"])
        self.assertEqual(json.loads(receipt_path.read_text())["state"], "patched")
        mini = runpy.run_path(str(self.stage / "SALAM-Configurator/parser.py"))["MiniParser"]()
        self.assertEqual(mini.path(str(self.stage), "default.yml",
                                   {"ConfigPath": self.profile}),
                         str(self.stage / self.profile))
        with self.assertRaises(ValueError):
            mini.path(str(self.stage), "default.yml",
                      {"ConfigPath": "../outside.yml"})

    def test_two_accelerators_bind_distinct_yaml_profiles(self):
        second = "benchmarks/suite/custom/hw/configs/second.yml"
        source_second = self.engine / second
        source_second.parent.mkdir(parents=True)
        source_second.write_text(
            "hw_config:\n  second:\n    instructions:\n      mul:\n        runtime_cycles: 7\n"
        )
        self.config.write_text(
            self.config_text(self.profile)
            + "  - Accelerator:\n"
            + "      - Name: second\n"
            + "        PIOSize: 64\n"
            + "        IrPath: benchmarks/suite/custom/hw/second.ll\n"
            + "        ConfigPath: " + second + "\n"
        )
        result = adapt_staged_configpaths(self.engine, self.stage, self.benchmark)
        self.assertEqual(result["state"], "patched")
        self.assertEqual(len(result["bindings"]), 2)
        self.assertEqual({item["config_path"] for item in result["bindings"]},
                         {self.profile, second})
        self.assertEqual(len(result["referenced_inputs"]), 2)
        self.assertEqual((self.stage / second).read_bytes(), source_second.read_bytes())
    def test_alternate_source_config_preserves_self_reference_provenance(self):
        alternate = "benchmarks/suite/custom/custom_configpath.yml"
        source_config = self.engine / alternate
        source_config.parent.mkdir(parents=True)
        original_text = (
            self.config_text(self.benchmark + "/config.yml")
            + "hw_config:\n  top:\n    instructions:\n      add:\n        runtime_cycles: 2\n"
        )
        source_config.write_text(original_text)
        self.config.write_text(original_text.replace("runtime_cycles: 2", "runtime_cycles: 3"))
        result = adapt_staged_configpaths(
            self.engine, self.stage, self.benchmark,
            source_config_relative=alternate,
        )
        self.assertEqual(result["state"], "patched")
        self.assertEqual(result["source_config_path"], str(source_config))
        self.assertEqual(result["referenced_inputs"][0]["path"], str(source_config))
        self.assertNotEqual(result["referenced_inputs"][0]["sha256"],
                            result["referenced_inputs"][0]["staged_sha256"])
    def test_no_configpath_leaves_parser_unpatched(self):
        self.config.write_text(self.config_text())
        before = (self.stage / "SALAM-Configurator/parser.py").read_bytes()
        result = adapt_staged_configpaths(self.engine, self.stage, self.benchmark)
        self.assertEqual(result["state"], "not_required")
        self.assertEqual((self.stage / "SALAM-Configurator/parser.py").read_bytes(), before)

    def test_legacy_ini_profile_is_rejected_without_patch(self):
        self.config.write_text(self.config_text(self.profile[:-4] + ".ini"))
        before = (self.stage / "SALAM-Configurator/parser.py").read_bytes()
        receipt_path = self.root / "rejected.json"
        with self.assertRaises(ValueError):
            adapt_staged_configpaths(self.engine, self.stage, self.benchmark,
                                     receipt_path=receipt_path)
        self.assertEqual((self.stage / "SALAM-Configurator/parser.py").read_bytes(), before)
        self.assertEqual(json.loads(receipt_path.read_text())["state"], "failed")

    def test_missing_ir_stem_profile_is_rejected(self):
        self.config.write_text(self.config_text(self.profile))
        self.source_profile.write_text("hw_config:\n  other:\n    instructions:\n      add:\n        runtime_cycles: 3\n")
        with self.assertRaises(ValueError):
            adapt_staged_configpaths(self.engine, self.stage, self.benchmark)
        self.assertNotIn("CONFIGPATH_CONSUMER_VERSION",
                         (self.stage / "SALAM-Configurator/parser.py").read_text())


if __name__ == "__main__":
    unittest.main()