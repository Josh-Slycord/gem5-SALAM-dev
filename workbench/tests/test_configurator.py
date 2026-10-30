"""Contract tests; these fixtures do not claim simulator or hardware validation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench import configurator as c
from salam_workbench.configurator_runtime import configure_system


class GeneratedDebugObjectRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        self.relative = "build/ARM/python/_m5/param_GarnetNetworkInterface.o"
        self.obj = self.engine / self.relative
        self.obj.parent.mkdir(parents=True)
        self.obj.write_bytes(b"original generated object")
        self.logs = self.root / "build-evidence"
        self.logs.mkdir()

    def diagnostic(self, *, relative=None, section=".debug_loc", symbol=".LVL2030"):
        relative = relative or self.relative
        return (
            "compiler.cc:1: warning: ordinary warning\n"
            + "/usr/bin/ld: "
            + relative
            + ":("
            + section
            + "+0x123): undefined reference to `"
            + symbol
            + "'\n"
            + "/usr/bin/ld: "
            + relative
            + ":("
            + section
            + "+0x124): more undefined references to `"
            + symbol
            + "' follow\n"
            + "collect2: error: ld returned 1 exit status\n"
            + "scons: *** [build/ARM/gem5.opt] Error 1\n"
        )

    def test_only_exclusive_generated_debug_label_errors_are_recognized(self):
        self.assertEqual(
            c._debug_label_recovery_objects(self.engine, self.diagnostic()), [self.obj]
        )
        for invalid in (
            self.diagnostic(symbol="real_missing_function"),
            self.diagnostic(section=".text"),
            self.diagnostic(section=".data"),
            self.diagnostic().replace(".LVL2030", ".LVL2030bad"),
            self.diagnostic() + "another.cc:2: error: compilation failed\n",
            "another.cc:2: error: compilation failed\n" + self.diagnostic(),
            "another.cc:2: internal compiler error: failure\n" + self.diagnostic(),
            self.diagnostic().replace(
                "collect2: error: ld returned 1 exit status\n", ""
            ),
            self.diagnostic().replace(
                "undefined reference to", "relocation truncated to fit:"
            ),
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    c._debug_label_recovery_objects(self.engine, invalid), []
                )
        self.assertEqual(self.obj.read_bytes(), b"original generated object")

    def test_escape_and_non_generated_paths_do_not_authorize_recovery(self):
        for relative in (
            "../outside/param_Bad.o",
            "/tmp/param_Bad.o",
            "build/ARM/python/_m5/../param_Bad.o",
            "build/ARM/hwacc/param_Bad.o",
            "build/ARM/python/_m5/not-a-parameter.o",
        ):
            with self.subTest(relative=relative):
                self.assertEqual(
                    c._debug_label_recovery_objects(
                        self.engine, self.diagnostic(relative=relative)
                    ),
                    [],
                )
        self.assertTrue(self.obj.is_file())

    def test_generated_object_symlink_is_rejected(self):
        linked = self.obj.parent / "param_Link.o"
        linked.symlink_to(self.obj)
        with self.assertRaisesRegex(ValueError, "symlink"):
            c._debug_label_recovery_objects(
                self.engine,
                self.diagnostic(relative=linked.relative_to(self.engine).as_posix()),
            )
        self.assertEqual(self.obj.read_bytes(), b"original generated object")

    def test_symlinked_generated_directory_is_rejected(self):
        other = self.root / "other-engine"
        (other / "build/ARM/python").mkdir(parents=True)
        (other / "build/ARM/python/_m5").symlink_to(
            self.obj.parent, target_is_directory=True
        )
        with self.assertRaisesRegex(ValueError, "symlink"):
            c._debug_label_recovery_objects(other, self.diagnostic())
        self.assertTrue(self.obj.is_file())

    def test_archive_preserves_exact_generated_object_bytes_and_hash(self):
        original = c.file_hash(self.obj)
        receipt = c._archive_debug_label_objects(self.engine, self.logs, [self.obj])
        self.assertEqual(receipt["state"], "archived")
        self.assertFalse(self.obj.exists())
        archived = receipt["objects"][0]
        self.assertEqual(archived["sha256"], original)
        self.assertEqual(archived["relative_path"], self.relative)
        self.assertEqual(c.file_hash(archived["archive"]["path"]), original)
        self.assertEqual(
            Path(archived["archive"]["path"]).read_bytes(), b"original generated object"
        )

    def failed_attempt(self, label, diagnostic):
        stderr = self.logs / (label + ".stderr")
        stderr.write_text(diagnostic)
        record = {
            "state": "failed",
            "return_code": 2,
            "stderr": stderr.name,
            "stderr_sha256": c.file_hash(stderr),
        }
        c._save(self.logs / (label + ".json"), record)
        return record

    def test_one_ordinary_retry_keeps_first_command_and_archived_object(self):
        calls = []
        argv, environment = ["python", "scons", "build/ARM/gem5.opt"], {
            "ENV": "unchanged"
        }

        def command(args, engine, directory, label, env, timeout):
            calls.append((list(args), engine, directory, label, dict(env), timeout))
            if label == "scons":
                self.failed_attempt(label, self.diagnostic())
                raise RuntimeError("scons failed")
            self.assertFalse(self.obj.exists())
            self.obj.write_bytes(b"normally regenerated object")
            return {"state": "completed", "return_code": 0, "stderr": label + ".stderr"}

        receipt = {"state": "running"}
        with patch.object(c, "_command", side_effect=command):
            final = c._run_build_with_debug_recovery(
                self.engine, self.logs, argv, environment, 60, receipt
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][:3], calls[1][:3])
        self.assertEqual(calls[0][4:], calls[1][4:])
        self.assertEqual([row[3] for row in calls], ["scons", "scons-retry1"])
        self.assertEqual(len(receipt["attempts"]), 2)
        self.assertEqual(receipt["attempts"][0]["state"], "failed")
        self.assertEqual(final, receipt["command"])
        self.assertEqual(final["return_code"], 0)
        self.assertEqual(self.obj.read_bytes(), b"normally regenerated object")
        archive = receipt["debug_label_recovery"]["objects"][0]["archive"]["path"]
        self.assertEqual(Path(archive).read_bytes(), b"original generated object")
        self.assertIn(".LVL2030", (self.logs / "scons.stderr").read_text())

    def test_repeated_failure_stops_after_one_retry(self):
        receipt = {"state": "running"}

        def command(args, engine, directory, label, env, timeout):
            self.failed_attempt(label, self.diagnostic())
            raise RuntimeError("link failure")

        with patch.object(c, "_command", side_effect=command) as run:
            with self.assertRaisesRegex(RuntimeError, "link failure"):
                c._run_build_with_debug_recovery(
                    self.engine, self.logs, [], {}, 60, receipt
                )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(receipt["attempts"]), 2)
        self.assertEqual(receipt["command"]["state"], "failed")
        self.assertTrue(
            (self.logs / "debug-label-recovery/objects" / self.obj.name).exists()
        )

    def test_unrelated_build_failure_never_moves_an_object_or_retries(self):
        def command(args, engine, directory, label, env, timeout):
            self.failed_attempt(label, self.diagnostic(symbol="real_function"))
            raise RuntimeError("ordinary failure")

        with patch.object(c, "_command", side_effect=command) as run:
            with self.assertRaisesRegex(RuntimeError, "ordinary failure"):
                c._run_build_with_debug_recovery(self.engine, self.logs, [], {}, 60, {})
        self.assertEqual(run.call_count, 1)
        self.assertTrue(self.obj.exists())
        self.assertFalse((self.logs / "debug-label-recovery").exists())


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def spec(self, **kwargs):
        return dict(
            schema_version=1,
            name="custom",
            benchmark="benchmarks/suite/custom",
            **kwargs,
        )

    def test_spec_rejects_unknown_options_and_escaping_paths(self):
        for spec in (
            dict(self.spec(), unknown=True),
            self.spec(config="../escape"),
            self.spec(system={"kernel": "old.elf"}),
            self.spec(parameters={"system.__dict__": {"x": 1}}),
            self.spec(base_address="0x10020001"),
            self.spec(system={"mem-size": float("nan")}),
        ):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                c.validate_spec(spec)

    def test_multiple_real_system_knobs_are_forwarded(self):
        spec = self.spec(
            system={
                "mem-size": "2GB",
                "mem-type": "DDR3_1600_8x8",
                "cpu-clock": "1GHz",
                "cpu-type": "TimingSimpleCPU",
                "l2cache": False,
            }
        )
        args = c.simulator_args(Path("/engine"), Path("/fresh"), c.validate_spec(spec))
        for value in (
            "--mem-size=2GB",
            "--mem-type=DDR3_1600_8x8",
            "--cpu-clock=1GHz",
            "--cpu-type=TimingSimpleCPU",
        ):
            self.assertIn(value, args)
        self.assertNotIn("--l2cache", args)
        self.assertIn("--accpath=/fresh/benchmarks/suite", args)

    def test_edits_are_explicit_and_misspellings_fail(self):
        docs = [{"acc_cluster": [{"DMA": [{"BufferSize": 128}]}]}]
        c.apply_edits(
            docs,
            [
                {
                    "path": [0, "acc_cluster", 0, "DMA", 0, "BufferSize"],
                    "value": 256,
                }
            ],
        )
        self.assertEqual(docs[0]["acc_cluster"][0]["DMA"][0]["BufferSize"], 256)
        with self.assertRaises(ValueError):
            c.apply_edits(
                docs,
                [
                    {
                        "path": [0, "acc_cluster", 0, "DMA", 0, "Buffersize"],
                        "value": 256,
                    }
                ],
            )

    def test_ini_witness_rejects_missing_changed_and_forged_sections(self):
        ini = self.root / "config.ini"
        ini.write_text("[system.a]\ncycles=2\n")
        applied = {
            "parameters": [
                {
                    "section": "system.a",
                    "parameter": "cycles",
                    "normalized": "2",
                }
            ]
        }
        self.assertEqual(c.witness_parameters(ini, applied)["state"], "passed")
        ini.write_text("[system.a]\ncycles=1\n")
        self.assertEqual(c.witness_parameters(ini, applied)["state"], "failed")
        ini.write_text("[system.b]\ncycles=2\n")
        self.assertEqual(c.witness_parameters(ini, applied)["state"], "failed")

    def test_unused_accelerator_cache_template_cannot_claim_configured_consumer(
        self,
    ):
        benchmark = self.root / "benchmarks/suite/custom"
        benchmark.mkdir(parents=True)
        (benchmark / "config.yml").write_text("acc_cluster: []\n")
        with self.assertRaisesRegex(ValueError, "no Cache memory consumer"):
            c.wire_runtime(
                self.root, self.spec(accelerator_cache={"assoc": 4}), self.root
            )

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
            result = c.run_configuration(
                self.root, spec, self.root / "evidence", simulate=True
            )
        self.assertEqual(result["state"], "failed")
        run.assert_not_called()
        self.assertEqual(
            json.loads((self.root / "evidence/configuration.json").read_text())[
                "stage"
            ],
            "specification",
        )

    def test_runtime_hook_sets_compiled_parameter_and_records_normalization(
        self,
    ):
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
        request.write_text(
            json.dumps(
                {
                    "parameters": {"system": {"cycles": 2}},
                    "witness_path": str(self.root / "applied.json"),
                }
            )
        )
        configure_system(obj, request)
        self.assertEqual(obj.cycles, 2)
        self.assertEqual(
            json.loads((self.root / "applied.json").read_text())["parameters"][0][
                "normalized"
            ],
            "2",
        )
        for fields in ({"typo": 2}, {"cycles": 0.25}):
            request.write_text(
                json.dumps(
                    {
                        "parameters": {"system": fields},
                        "witness_path": str(self.root / "rejected.json"),
                    }
                )
            )
            with self.assertRaises(ValueError):
                configure_system(obj, request)
        self.assertFalse((self.root / "rejected.json").exists())


if __name__ == "__main__":
    unittest.main()
