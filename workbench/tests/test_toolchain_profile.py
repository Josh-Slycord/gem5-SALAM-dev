"""Selected-runtime isolation, receipt invalidation, and conservative readiness."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from salam_workbench import configurator, doctor, runner, system_witness
from salam_workbench import toolchain_profile as profiles


def manifest(profile):
    return {"configuration_engine": {"toolchain_profile": profile}}


class ToolchainProfileTests(unittest.TestCase):
    def setUp(self):
        self.legacy = profiles.load_toolchain(manifest={})
        self.modern = profiles.load_toolchain(manifest=manifest(profiles.MODERN_ID))

    def test_absent_profile_keeps_exact_legacy_build_and_environment(self):
        self.assertEqual(
            profiles.build_argv(self.legacy, jobs=3),
            [
                "/usr/bin/python3.8",
                "/usr/bin/scons",
                "build/ARM/gem5.opt",
                "-j3",
                "CXX=/usr/bin/g++",
                "PYTHON_CONFIG=/usr/bin/python3.8-config",
                "USE_KVM=0",
                "PROTOCOL=CHI",
            ],
        )
        self.assertEqual(
            profiles.apply_environment(
                {"PATH": "/old", "HOME": "/home/test"}, self.legacy
            ),
            {"PATH": "/usr/lib/llvm-12/bin:/old", "HOME": "/home/test"},
        )

    def test_modern_profile_selects_venv_and_modern_build_flags(self):
        command = profiles.build_argv(self.modern)
        self.assertEqual(command[:2], [self.modern["python"], self.modern["scons"]])
        self.assertIn("--with-salam", command)
        self.assertIn("LLVM_CONFIG=/usr/bin/llvm-config-14", command)
        self.assertFalse(
            any(value.startswith(("PROTOCOL=", "USE_KVM=")) for value in command)
        )
        environment = profiles.apply_environment(
            {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "0"}, self.modern
        )
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
        self.assertEqual(environment["CXX"], "/usr/bin/g++")
        self.assertEqual(environment["PYTHON_CONFIG"], "/usr/bin/python3.12-config")
        self.assertFalse(
            any(value.startswith(("CXX=", "PYTHON_CONFIG=")) for value in command)
        )
        self.assertTrue(
            environment["PATH"].startswith(
                "/usr/lib/llvm-14/bin:/home/jslycord/.venvs/salam26-20261030/bin:/usr/bin:"
            )
        )

    def test_modern_overrides_are_explicit_absolute_direct_arguments(self):
        selected = profiles.load_toolchain(
            manifest=manifest(
                {
                    "id": profiles.MODERN_ID,
                    "python": "/opt/runtime with spaces/bin/python",
                }
            )
        )
        self.assertEqual(
            profiles.build_argv(selected)[0], "/opt/runtime with spaces/bin/python"
        )
        self.assertNotEqual(
            profiles.profile_identity(selected), profiles.profile_identity(self.modern)
        )

    def test_modern_compiler_environment_is_sensitive_to_explicit_profile(self):
        selected = profiles.load_toolchain(
            manifest=manifest(
                {
                    "id": profiles.MODERN_ID,
                    "cxx": "/opt/compiler/g++",
                    "python_config": "/opt/headers/python3.12-config",
                }
            )
        )
        environment = profiles.apply_environment(
            {"CXX": "/incorrect/compiler", "PYTHON_CONFIG": "/incorrect/config"},
            selected,
        )
        self.assertEqual(environment["CXX"], "/opt/compiler/g++")
        self.assertEqual(environment["PYTHON_CONFIG"], "/opt/headers/python3.12-config")

    def test_modern_cpu_aliases_record_requested_and_effective_classes(self):
        for requested, effective in (
            ("DerivO3CPU", "ArmO3CPU"),
            ("O3CPU", "ArmO3CPU"),
            ("TimingSimpleCPU", "ArmTimingSimpleCPU"),
            ("AtomicSimpleCPU", "ArmAtomicSimpleCPU"),
            ("MinorCPU", "ArmMinorCPU"),
        ):
            options = {"cpu-type": requested, "mem-size": "4GB"}
            result = profiles.normalize_system_options(self.modern, options)
            self.assertEqual(result["requested"], options)
            self.assertEqual(result["effective"]["cpu-type"], effective)
            self.assertEqual(result["normalizations"][0]["requested"], requested)
            self.assertEqual(options["cpu-type"], requested)
            legacy = profiles.normalize_system_options(self.legacy, options)
            self.assertEqual(legacy["effective"], options)
            self.assertEqual(legacy["normalizations"], [])

    def test_modern_explicit_cpu_and_unknown_cpu_are_not_silently_replaced(self):
        for name in ("ArmTimingSimpleCPU", "UnknownCpu"):
            result = profiles.normalize_system_options(self.modern, {"cpu-type": name})
            self.assertEqual(result["effective"]["cpu-type"], name)
            self.assertEqual(result["normalizations"], [])

    def test_modern_simulator_argv_uses_effective_cpu_but_retains_intent(self):
        spec = {
            "name": "gemm",
            "benchmark": "benchmarks/sys_validation/gemm",
            "system": {"cpu-type": "TimingSimpleCPU"},
        }
        with mock.patch.object(
            configurator, "load_toolchain", return_value=self.modern
        ):
            args = configurator.simulator_args(
                Path("/engine"), Path("/workspace"), spec
            )
            configuration = configurator.effective_system_configuration(spec)
        self.assertIn("--cpu-type=ArmTimingSimpleCPU", args)
        self.assertNotIn("--cpu-type=TimingSimpleCPU", args)
        self.assertEqual(configuration["requested"]["cpu-type"], "TimingSimpleCPU")
        self.assertEqual(spec["system"]["cpu-type"], "TimingSimpleCPU")

    def test_modern_cpu_witness_checks_actual_base_simobject_type(self):
        with tempfile.TemporaryDirectory() as directory:
            ini = Path(directory) / "config.ini"
            for requested, effective_type in (
                ("ArmTimingSimpleCPU", "BaseTimingSimpleCPU"),
                ("ArmAtomicSimpleCPU", "BaseAtomicSimpleCPU"),
                ("ArmO3CPU", "BaseO3CPU"),
                ("ArmMinorCPU", "BaseMinorCPU"),
            ):
                ini.write_text("[system.cpu]\ntype=" + effective_type + "\n")
                self.assertEqual(
                    system_witness.witness_system(ini, {"cpu-type": requested})[
                        "state"
                    ],
                    "passed",
                )
                ini.write_text("[system.cpu]\ntype=O3CPU\n")
                self.assertEqual(
                    system_witness.witness_system(ini, {"cpu-type": requested})[
                        "state"
                    ],
                    "failed",
                )

    def test_modern_bootloaders_are_staged_under_m5_path_with_exact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, workspace = root / "engine", root / "workspace"
            for relative in (
                "system/arm/bootloader/arm/boot.arm",
                "system/arm/bootloader/arm64/boot.arm64",
            ):
                path = engine / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic asset transport: " + relative.encode())
            records = configurator.stage_modern_bootloaders(engine, workspace)
            self.assertEqual(len(records), 2)
            for record in records:
                self.assertEqual(Path(record["staged"]).parent, workspace / "binaries")
                self.assertEqual(runner.file_hash(record["staged"]), record["sha256"])
                self.assertEqual(
                    Path(record["path"]).read_bytes(),
                    Path(record["staged"]).read_bytes(),
                )

    def test_missing_modern_bootloader_fails_before_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                configurator.stage_modern_bootloaders(
                    Path(directory), Path(directory) / "workspace"
                )

    def test_runner_forwards_only_explicit_python_isolation_flags(self):
        # Synthetic subprocess transport evidence, not a simulator/correctness run.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "transport.py"
            script.write_text(
                "import argparse,json,os\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--outdir');p.add_argument('--transport',action='store_true');a=p.parse_args();d=Path(a.outdir);d.mkdir(exist_ok=True)\n(d/'system.terminal').write_text('Check Passed\\n')\n(d/'isolation.json').write_text(json.dumps({k:os.environ.get(k) for k in ('PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE')}))\nprint('Exiting @ tick 1 because m5_exit instruction encountered')\n"
            )
            result = runner.run_experiment(
                [sys.executable, "-B", str(script)],
                ["--transport"],
                cwd=root,
                runs_root=root / "runs",
                experiment={
                    "schema_version": 1,
                    "experiment_id": "synthetic-python-isolation-transport",
                    "evidence_kind": "synthetic-subprocess-fixture",
                },
                env_overrides={"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(result["state"], "passed", json.dumps(result))
            observed = json.loads(
                (Path(result["run_directory"]) / "simulator/isolation.json").read_text()
            )
            self.assertEqual(
                observed, {"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
            )

    def test_unknown_profiles_fields_and_unsafe_paths_fail_without_fallback(self):
        entries = [
            {"id": "unknown"},
            {"id": profiles.MODERN_ID, "silent_fallback": True},
        ]
        entries.extend(
            {"id": profiles.MODERN_ID, "python": path}
            for path in (
                "python3",
                "/",
                "/a/../b",
                "/a/./b",
                "/a//b",
                "C:\\Python\\python.exe",
                "/a\x00b",
                123,
            )
        )
        entries.append({"id": profiles.LEGACY_ID, "python": "/usr/bin/python3"})
        for entry in entries:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                profiles.load_toolchain(manifest=manifest(entry))

    def test_build_plan_rejects_unbounded_jobs_or_unapproved_target(self):
        for jobs in (True, 0, 33, "8"):
            with self.subTest(jobs=jobs), self.assertRaises(ValueError):
                profiles.build_argv(self.modern, jobs=jobs)
        with self.assertRaises(ValueError):
            profiles.build_argv(self.modern, target="build/ALL/gem5.opt")

    def test_selected_llvm_library_bytes_are_in_the_toolchain_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "libLLVM-14.so.1"
            library.write_bytes(b"original LLVM library")
            result = subprocess.CompletedProcess([], 0, str(library) + "\n", "")
            with mock.patch.object(
                profiles.subprocess, "run", return_value=result
            ) as probe:
                before = profiles._llvm_shared_libraries(
                    self.modern, {"PATH": "/fixed"}
                )
                library.write_bytes(b"different LLVM library")
                after = profiles._llvm_shared_libraries(self.modern, {"PATH": "/fixed"})
            self.assertNotEqual(
                before["libraries"][0]["sha256"], after["libraries"][0]["sha256"]
            )
            self.assertEqual(probe.call_args.kwargs["shell"], False)
            self.assertEqual(
                before["argv"],
                [self.modern["llvm_config"], "--libfiles", "--link-shared"],
            )

    def test_failed_or_empty_llvm_query_does_not_create_a_receipt(self):
        for result in (
            subprocess.CompletedProcess([], 1, "", "failed"),
            subprocess.CompletedProcess([], 0, "", ""),
        ):
            with mock.patch.object(
                profiles.subprocess, "run", return_value=result
            ), self.assertRaises(ValueError):
                profiles._llvm_shared_libraries(self.modern, {})

    def test_modern_build_configuration_preserves_exact_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = root / "engine"
            build = engine / "build/ARM/gem5.build"
            build.mkdir(parents=True)
            expected = {
                "config": b"CONFIG_USE_ARM_ISA=y\n",
                "Kconfig": b'source "src/Kconfig"\n',
            }
            for name, payload in expected.items():
                (build / name).write_bytes(payload)
            receipt = configurator._modern_build_configuration(engine, root / "receipt")
            self.assertEqual(
                {Path(item["path"]).name for item in receipt}, set(expected)
            )
            for item in receipt:
                self.assertEqual(
                    Path(item["snapshot"]["path"]).read_bytes(),
                    expected[Path(item["path"]).name],
                )
                self.assertEqual(item["snapshot"]["sha256"], item["sha256"])

    def test_missing_modern_kconfig_file_cannot_be_replaced_by_legacy_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                configurator._modern_build_configuration(
                    Path(directory), Path(directory) / "receipt"
                )

    def test_modern_configured_receipt_cannot_omit_toolchain_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "build.json"
            receipt.write_text(
                json.dumps(
                    {
                        "kind": "configured_engine_build",
                        "state": "built",
                        "binary": {"sha256": "binary"},
                        "compiled_source_sha256": "source",
                    }
                )
            )
            with mock.patch.object(
                configurator, "file_hash", return_value="binary"
            ), mock.patch.object(
                configurator, "compiled_identity", return_value={"sha256": "source"}
            ), mock.patch.object(
                configurator, "load_toolchain", return_value=self.modern
            ), self.assertRaisesRegex(
                ValueError, "selected-toolchain receipt"
            ):
                configurator.verify_engine(Path(directory), receipt)

    def test_changed_linked_llvm_library_invalidates_configured_build(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "build.json"
            selected = {
                "profile": self.modern,
                "tools": {"python": {"path": "/python", "sha256": "binary"}},
                "llvm_shared_libraries": {
                    "libraries": [{"path": "/llvm", "sha256": "original"}]
                },
            }
            receipt.write_text(
                json.dumps(
                    {
                        "kind": "configured_engine_build",
                        "state": "built",
                        "binary": {"sha256": "binary"},
                        "compiled_source_sha256": "source",
                        "selected_toolchain": selected,
                    }
                )
            )
            with mock.patch.object(
                configurator, "file_hash", return_value="binary"
            ), mock.patch.object(
                configurator, "compiled_identity", return_value={"sha256": "source"}
            ), mock.patch.object(
                configurator, "load_toolchain", return_value=self.modern
            ), self.assertRaisesRegex(
                ValueError, "linked LLVM library changed"
            ):
                configurator.verify_engine(Path(directory), receipt)


class ModernDoctorTests(unittest.TestCase):
    def setUp(self):
        self.profile = profiles.load_toolchain(manifest=manifest(profiles.MODERN_ID))
        self.host = {
            "system": "Linux",
            "kernel": "6.6-microsoft-standard-WSL2",
            "distribution": "ubuntu",
            "distribution_version": "24.04",
            "python_version": "3.12.3",
            "python_executable": str(Path(self.profile["python"]).resolve()),
            "python_prefix": str(Path(self.profile["python"]).parent.parent.resolve()),
        }
        self.snapshot = {
            "version_probes": {
                name: {"output": value}
                for name, value in {
                    "llvm": "14.0.6",
                    "clang": "Ubuntu clang version 14.0.6",
                    "scons": "engine: v4.10.1",
                    "python_config": "-I/usr/include/python3.12",
                }.items()
            }
        }
        self.source = [
            doctor._check(name, True, {}, "fixture", "")
            for name in ("source", "configured_build_receipt")
        ]

    def inspect(self):
        with mock.patch.object(
            doctor, "_platform_info", return_value=self.host
        ), mock.patch.object(
            doctor, "record_toolchain", return_value=self.snapshot
        ), mock.patch.object(
            doctor,
            "_profile_probe",
            return_value={"return_code": 0, "output": "tool version observed"},
        ), mock.patch.object(
            doctor,
            "_modern_package_check",
            side_effect=lambda profile, name, module: doctor._check(
                name.lower(), True, {"version": "observed"}, "importable", ""
            ),
        ), mock.patch.object(
            doctor, "_modern_source_checks", return_value=self.source
        ):
            return doctor._inspect_modern_environment(
                Path("/engine"), Path("/project"), self.profile, True
            )

    def test_ready_modern_doctor_does_not_claim_numerical_or_legacy_reference_validation(
        self,
    ):
        result = self.inspect()
        self.assertTrue(result["ready"])
        self.assertFalse(result["capabilities"]["reproduce_without_engine_build"])
        self.assertEqual(
            result["capabilities"]["legacy_reference_mode"],
            "unavailable_on_modern_profile",
        )
        self.assertEqual(result["capabilities"]["numerical_simulations"], "not_tested")
        self.assertEqual(result["capabilities"]["gui_rendering"], "not_tested")

    def test_system_python_with_same_executable_is_not_selected_venv(self):
        self.host["python_prefix"] = "/usr"
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertIn("python_runtime", result["failures"])

    def test_mismatched_llvm_and_clang_or_legacy_scons_is_rejected(self):
        for name, value in (
            ("clang", "Ubuntu clang version 14.0.5"),
            ("scons", "engine: v3.1.2"),
        ):
            with self.subTest(name=name):
                original = self.snapshot["version_probes"][name]["output"]
                self.snapshot["version_probes"][name]["output"] = value
                self.assertIn("selected_toolchain", self.inspect()["failures"])
                self.snapshot["version_probes"][name]["output"] = original

    def test_missing_modern_build_receipt_keeps_readiness_false(self):
        self.source[-1]["status"] = "fail"
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertFalse(result["capabilities"]["recorded_build_matches"])

    def test_manifest_dispatches_modern_check_without_legacy_probes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workspace.json").write_text(
                json.dumps(manifest(profiles.MODERN_ID))
            )
            with mock.patch.object(
                doctor, "_inspect_modern_environment", return_value={"modern": True}
            ) as modern, mock.patch.object(
                doctor, "_probe", side_effect=AssertionError("legacy probe")
            ):
                self.assertEqual(
                    doctor.inspect_environment("/engine", project_root=root),
                    {"modern": True},
                )
                self.assertEqual(modern.call_args.args[2]["id"], profiles.MODERN_ID)
