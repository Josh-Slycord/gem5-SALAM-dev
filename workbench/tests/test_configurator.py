"""Contract tests; these fixtures do not claim simulator or hardware validation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from salam_workbench import configurator as c
from salam_workbench.configurator_runtime import configure_system


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def spec(self, **kwargs):
        return dict(schema_version=1, name="custom", benchmark="benchmarks/suite/custom", **kwargs)

    def test_spec_rejects_unknown_options_and_escaping_paths(self):
        for spec in (dict(self.spec(), unknown=True), self.spec(config="../escape"),
                     self.spec(system={"kernel": "old.elf"}), self.spec(parameters={"system.__dict__": {"x": 1}}),
                     self.spec(base_address="0x10020001"), self.spec(system={"mem-size": float("nan")})):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                c.validate_spec(spec)

    def test_multiple_real_system_knobs_are_forwarded(self):
        spec = self.spec(system={"mem-size": "2GB", "mem-type": "DDR3_1600_8x8", "cpu-clock": "1GHz",
                                 "cpu-type": "TimingSimpleCPU", "l2cache": False})
        args = c.simulator_args(Path("/engine"), Path("/fresh"), c.validate_spec(spec))
        for value in ("--mem-size=2GB", "--mem-type=DDR3_1600_8x8", "--cpu-clock=1GHz", "--cpu-type=TimingSimpleCPU"):
            self.assertIn(value, args)
        self.assertNotIn("--l2cache", args)
        self.assertIn("--accpath=/fresh/benchmarks/suite", args)

    def test_edits_are_explicit_and_misspellings_fail(self):
        docs = [{"acc_cluster": [{"DMA": [{"BufferSize": 128}]}]}]
        c.apply_edits(docs, [{"path": [0, "acc_cluster", 0, "DMA", 0, "BufferSize"], "value": 256}])
        self.assertEqual(docs[0]["acc_cluster"][0]["DMA"][0]["BufferSize"], 256)
        with self.assertRaises(ValueError):
            c.apply_edits(docs, [{"path": [0, "acc_cluster", 0, "DMA", 0, "Buffersize"], "value": 256}])

    def test_ini_witness_rejects_missing_changed_and_forged_sections(self):
        ini = self.root / "config.ini"
        ini.write_text("[system.a]\ncycles=2\n")
        applied = {"parameters": [{"section": "system.a", "parameter": "cycles", "normalized": "2"}]}
        self.assertEqual(c.witness_parameters(ini, applied)["state"], "passed")
        ini.write_text("[system.a]\ncycles=1\n")
        self.assertEqual(c.witness_parameters(ini, applied)["state"], "failed")
        ini.write_text("[system.b]\ncycles=2\n")
        self.assertEqual(c.witness_parameters(ini, applied)["state"], "failed")

    def test_unused_accelerator_cache_template_cannot_claim_configured_consumer(self):
        benchmark = self.root / "benchmarks/suite/custom"
        benchmark.mkdir(parents=True)
        (benchmark / "config.yml").write_text("acc_cluster: []\n")
        with self.assertRaisesRegex(ValueError, "no Cache memory consumer"):
            c.wire_runtime(self.root, self.spec(accelerator_cache={"assoc": 4}), self.root)

    def test_compiled_source_change_invalidates_build_identity(self):
        engine = self.root / "engine"
        (engine / "src").mkdir(parents=True)
        (engine / "SConstruct").write_text("# build\n")
        source = engine / "src/test.cc"
        source.write_text("// source\n")
        before = c.compiled_identity(engine)
        (engine / "build").mkdir()
        (engine / "build/unrelated.log").write_text("noise")
        self.assertEqual(before, c.compiled_identity(engine))
        source.write_text("// changed\n")
        self.assertNotEqual(before, c.compiled_identity(engine))

    def test_failed_preflight_has_durable_receipt_and_no_simulator(self):
        spec = self.root / "bad.json"
        spec.write_text(json.dumps(dict(self.spec(), bogus=1)))
        with patch.object(c, "run_experiment") as run:
            result = c.run_configuration(self.root, spec, self.root / "evidence", simulate=True)
        self.assertEqual(result["state"], "failed")
        run.assert_not_called()
        self.assertEqual(json.loads((self.root / "evidence/configuration.json").read_text())["stage"], "specification")

    def test_runtime_hook_sets_compiled_parameter_and_records_normalization(self):
        class Value(int):
            def ini_str(self):
                return str(self)
        class Descriptor:
            ptype = Value
            ptype_str = "UInt32"
        class Obj:
            _params = {"cycles": Descriptor()}
            def __setattr__(self, name, value):
                object.__setattr__(self, name, Value(value))
        obj = Obj()
        request = self.root / "request.json"
        request.write_text(json.dumps({"parameters": {"system": {"cycles": 2}}, "witness_path": str(self.root / "applied.json")}))
        configure_system(obj, request)
        self.assertEqual(obj.cycles, 2)
        self.assertEqual(json.loads((self.root / "applied.json").read_text())["parameters"][0]["normalized"], "2")
        for fields in ({"typo": 2}, {"cycles": 0.25}):
            request.write_text(json.dumps({"parameters": {"system": fields}, "witness_path": str(self.root / "rejected.json")}))
            with self.assertRaises(ValueError):
                configure_system(obj, request)
        self.assertFalse((self.root / "rejected.json").exists())


if __name__ == "__main__":
    unittest.main()
