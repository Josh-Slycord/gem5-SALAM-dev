"""Capability-check tests use source-derived version text, no real tool execution."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from salam_workbench import doctor

HOST = {
    "system": "Linux",
    "kernel": "5.15.167.4-microsoft-standard-WSL2",
    "distribution": "ubuntu",
    "distribution_version": "20.04",
    "distribution_label": "Ubuntu 20.04.6 LTS",
    "python_version": "3.8.10",
    "python_executable": "/usr/bin/python3.8",
    "expected_python_executable": "/usr/bin/python3.8",
}
VERSIONS = {
    "clang": "Ubuntu clang version 12.0.0-3ubuntu1~20.04.5",
    "llvm": "12.0.0",
    "gcc": "9.4.0",
    "gxx": "9.4.0",
    "arm_gcc": "arm-none-eabi-gcc (GNU Tools for Arm Embedded Processors 9-2019-q4-major) 9.2.1 20191025 (release)",
    "arm_gxx": "arm-none-eabi-g++ (GNU Tools for Arm Embedded Processors 9-2019-q4-major) 9.2.1 20191025 (release)",
    "scons": "SCons by Steven Knight et al.:\n script: v3.1.2\n engine: v3.1.2",
    "make": "GNU Make 4.2.1",
    "python_config": "-I/usr/include/python3.8 -I/usr/include/python3.8",
}
PACKAGES = {
    "PyYAML": "6.0.3",
    "PySide6": "6.2.4",
    "networkx": "3.1",
    "numpy": "1.24.4",
}


def source_pass():
    return [
        doctor._check(name, True, {}, "fixture", "")
        for name in ("source", "gemm_contract", "build_receipt")
    ]


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.versions = dict(VERSIONS)
        self.packages = dict(PACKAGES)
        self.source = source_pass()
        self.host = dict(HOST)
        self.calls = []
        for target, replacement in (
            ("_platform_info", lambda: self.host),
            ("_probe", self.probe),
            ("_source_checks", lambda *args: self.source),
        ):
            patcher = mock.patch.object(doctor, target, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def probe(self, argv, **kwargs):
        self.calls.append(list(argv))
        for name, known, expected, pattern in doctor.TOOL_CHECKS:
            if tuple(argv) == known:
                output = self.versions[name]
                return {
                    "argv": list(argv),
                    "return_code": 0 if output is not None else None,
                    "output": output or "",
                    "error": None if output else "missing command",
                }
        for name, version in self.packages.items():
            if repr(name) in argv[-1]:
                return {
                    "argv": list(argv),
                    "return_code": 0 if version else 1,
                    "output": json.dumps({"version": version, "module_path": "fixture"})
                    if version
                    else "ImportError",
                }
        raise AssertionError("unexpected command: " + repr(argv))

    def inspect(self, **kwargs):
        return doctor.inspect_environment(
            "/engine", project_root="/workbench", **kwargs
        )

    def test_recorded_profile_with_source_and_receipt_is_ready(self):
        result = self.inspect()
        self.assertTrue(result["ready"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["kind"], "workbench_environment_check")
        self.assertTrue(result["capabilities"]["recorded_build_matches"])
        self.assertEqual(
            result["capabilities"]["fresh_distro_installation"], "not_verified"
        )
        self.assertEqual(result["capabilities"]["gui_rendering"], "not_tested")
        json.dumps(result, allow_nan=False)

    def test_llvm14_is_not_accepted_as_llvm12(self):
        self.versions["clang"] = "Ubuntu clang version 14.0.6"
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertIn("clang", result["failures"])
        self.assertFalse(result["capabilities"]["supported_toolchain"])

    def test_wrong_patch_version_is_outside_exact_profile(self):
        self.versions["gcc"] = "9.3.0"
        self.host["python_version"] = "3.8.19"
        result = self.inspect()
        self.assertIn("gcc", result["failures"])
        self.assertIn("python_runtime", result["failures"])

    def test_optional_gui_failures_do_not_block_cli(self):
        self.packages["PySide6"] = None
        self.packages["networkx"] = None
        result = self.inspect()
        self.assertTrue(result["ready"])
        self.assertFalse(result["capabilities"]["optional_gui_dependencies"])
        self.assertTrue(any(c["status"] == "fail" for c in result["optional_checks"]))

    def test_skip_gui_runs_no_gui_probes(self):
        result = self.inspect(include_gui=False)
        self.assertEqual(result["optional_checks"], [])
        self.assertIsNone(result["capabilities"]["optional_gui_dependencies"])
        self.assertFalse(any("PySide6" in str(c) for c in self.calls))

    def test_missing_pyyaml_is_an_actionable_required_failure(self):
        self.packages["PyYAML"] = None
        result = self.inspect()
        self.assertIn("pyyaml", result["failures"])
        row = next(c for c in result["required_checks"] if c["id"] == "pyyaml")
        self.assertIn("Python3.8", row["action"])

    def test_missing_compiler_and_malformed_version_do_not_pass(self):
        for output in (None, "not a version", "clang version 120.0.0"):
            self.versions["clang"] = output
            self.assertIn("clang", self.inspect()["failures"])

    def test_receipt_mismatch_does_not_hide_toolchain_readiness(self):
        self.source[-1] = doctor._check(
            "build_receipt",
            False,
            "hash mismatch",
            "matching receipt",
            "rebuild deliberately",
        )
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertTrue(result["capabilities"]["supported_toolchain"])
        self.assertTrue(result["capabilities"]["source_contract"])
        self.assertFalse(result["capabilities"]["recorded_build_matches"])

    def test_other_distribution_is_not_claimed_supported(self):
        self.host["distribution_version"] = "22.04"
        self.assertIn("platform", self.inspect()["failures"])

    def test_windows_runtime_still_returns_structured_failures(self):
        self.host["system"] = "Windows"
        self.host["python_executable"] = "C:/python.exe"
        result = self.inspect()
        self.assertIn("platform", result["failures"])
        self.assertIn("python_runtime", result["failures"])

    def test_cli_emits_json_and_nonzero_on_failure(self):
        for ready, expected_exit in ((True, 0), (False, 1)):
            output = io.StringIO()
            with mock.patch.object(
                doctor, "inspect_environment", return_value={"ready": ready}
            ), contextlib.redirect_stdout(output):
                code = doctor.main(["--engine", "/engine", "--no-gui"])
            self.assertEqual(code, expected_exit)
            self.assertEqual(json.loads(output.getvalue()), {"ready": ready})


class ReadOnlyProbeTests(unittest.TestCase):
    def test_probe_uses_fixed_argv_without_shell_or_unrestricted_environment(
        self,
    ):
        with mock.patch.object(
            doctor.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "9.4.0\n", ""),
        ) as run:
            with mock.patch.dict(
                doctor.os.environ,
                {
                    "SECRET_EXAMPLE": "must-not-propagate",
                    "PYTHONPATH": "must-not-propagate",
                },
            ):
                result = doctor._probe(("/usr/bin/gcc", "-dumpversion"))
        self.assertEqual(result["return_code"], 0)
        kwargs = run.call_args[1]
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertNotIn("SECRET_EXAMPLE", kwargs["env"])
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertLessEqual(kwargs["timeout"], 20)

    def test_missing_or_timed_out_probe_is_structured(self):
        for error in (
            FileNotFoundError("missing"),
            subprocess.TimeoutExpired(["version"], 20),
        ):
            with mock.patch.object(doctor.subprocess, "run", side_effect=error):
                result = doctor._probe(("/usr/bin/gcc", "--version"))
            self.assertIsNone(result["return_code"])
            self.assertIn("error", result)

    def test_source_receipt_failure_is_preserved_without_building(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Path(directory)
            (engine / "SConstruct").write_text("# fixture", encoding="utf-8")
            gemm = SimpleNamespace(
                BASELINE="a" * 40,
                engine_source_digest=mock.Mock(return_value="b" * 64),
                git=mock.Mock(side_effect=[b"c" * 40, b"commit"]),
            )
            config = SimpleNamespace(
                validate_gemm_config=mock.Mock(return_value={"contract": "gemm-m1-v1"})
            )
            builds = SimpleNamespace(
                verify_receipt=mock.Mock(
                    side_effect=ValueError(
                        "Simulator binary differs from the selected build receipt"
                    )
                )
            )
            with mock.patch.dict(
                sys.modules,
                {
                    "salam_workbench.gemm": gemm,
                    "salam_workbench.config": config,
                    "salam_workbench.builds": builds,
                },
            ):
                checks = doctor._source_checks(engine, engine)
            self.assertEqual([c["status"] for c in checks], ["pass", "pass", "fail"])
            self.assertIn("Simulator binary differs", checks[-1]["observed"])
            self.assertIn("--build-engine", checks[-1]["action"])
            config.validate_gemm_config.assert_called_once_with(
                engine / "benchmarks/sys_validation/gemm/config.yml",
                engine,
                require_ir=False,
            )


if __name__ == "__main__":
    unittest.main()
