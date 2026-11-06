# SPDX-License-Identifier: BSD-3-Clause
"""Host verifier controls with fake commands; no guest or simulator is run."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SIBLING = Path(__file__).with_name("verify_guest_uart.py")
SCRIPT = (
    SIBLING
    if SIBLING.is_file()
    else Path(__file__).resolve().parents[1] / "scripts/verify_guest_uart.py"
)
SPEC = importlib.util.spec_from_file_location("uart_verifier_under_test", SCRIPT)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class GuestUartVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.repo = self.base / "repo with spaces;$"
        self.repo.mkdir()
        files = (
            "build/ARM/gem5.opt",
            "benchmarks/common/syscalls.c",
            "benchmarks/common/guest_uart_regression.c",
            "benchmarks/sys_validation/gemm/sw/boot.s",
            "benchmarks/sys_validation/gemm/sw/boot.ld",
            "configs/SALAM/generated/fs_gemm.py",
            "baremetal/common/fake.iso",
        )
        for relative in files:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("fixture:" + relative).encode())
        self.binary = self.repo / "build/ARM/gem5.opt"
        self.tools = {}
        for role in ("gcc", "cpp", "as"):
            tool = self.base / ("fixture-arm-" + role)
            tool.write_bytes(("tool:" + role).encode())
            self.tools[role] = tool
        self.calls = []
        self.behavior = "passed"
        self.run_dir = self.base / "fresh-evidence"

    def fake_command(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, b"fixture ARM tool\n", b"")
        if argv[0] == str(self.binary):
            if self.behavior == "timeout":
                raise subprocess.TimeoutExpired(
                    argv, kwargs["timeout"], output=b"started\n", stderr=b"stalled\n"
                )
            directory = Path(
                next(
                    item.split("=", 1)[1]
                    for item in argv
                    if item.startswith("--outdir=")
                )
            )
            directory.mkdir(parents=True)
            if self.behavior != "missing_terminal":
                content = (
                    b"FAIL_CASE_4\n"
                    if self.behavior == "guest_failure"
                    else VERIFY.EXPECTED_BYTES
                )
                if self.behavior == "oversized_terminal":
                    content = b"x" * (VERIFY.MAX_TERMINAL_BYTES + 1)
                (directory / "system.terminal").write_bytes(content)
            if self.behavior == "source_drift":
                (self.repo / "benchmarks/common/syscalls.c").write_text("changed\n")
            reason = (
                b"Exiting because unexpected event\n"
                if self.behavior == "wrong_exit"
                else b"Exiting @ tick 1000 because m5_exit instruction encountered\n"
            )
            if self.behavior == "misleading_exit_mention":
                reason = (
                    b"Earlier expected text: m5_exit instruction encountered\n"
                    b"Exiting @ tick 1000 because simulation time limit reached\n"
                )
            elif self.behavior == "multiple_exit_lines":
                reason += b"Exiting @ tick 2000 because unexpected event\n"
            elif self.behavior == "malformed_final_exit":
                reason += b"Exiting because unexpected event\n"
            elif self.behavior == "warning_after_exit":
                reason += b"warn: ordinary teardown warning after the exit line\n"
            code = 3 if self.behavior == "simulator_failure" else 0
            return subprocess.CompletedProcess(
                argv, code, reason, b"simulator stderr\n"
            )
        if self.behavior == "compiler_failure" and argv[0] == str(self.tools["cpp"]):
            return subprocess.CompletedProcess(argv, 2, b"", b"compiler failed\n")
        if "-o" in argv:
            output = Path(argv[argv.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(("built:" + output.name).encode())
        return subprocess.CompletedProcess(argv, 0, b"built\n", b"")

    def verify(self, outdir=None, **kwargs):
        with (
            patch.object(VERIFY, "_tools", return_value=self.tools),
            patch.object(VERIFY.subprocess, "run", side_effect=self.fake_command),
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu-24.04"}),
        ):
            return VERIFY.run_verification(
                self.repo, self.run_dir if outdir is None else outdir, **kwargs
            )

    def receipt_on_disk(self, directory=None):
        return json.loads(
            (
                (directory or self.run_dir) / "guest_uart_regression_receipt.json"
            ).read_text()
        )

    def test_success_is_source_bound_and_builds_outside_source(self):
        before = {
            str(p.relative_to(self.repo)): p.read_bytes()
            for p in self.repo.rglob("*")
            if p.is_file()
        }
        receipt = self.verify()
        self.assertEqual(receipt["state"], "passed", receipt["errors"])
        self.assertEqual(receipt, self.receipt_on_disk())
        self.assertEqual(receipt["wsl_distribution"], "Ubuntu-24.04")
        self.assertTrue(receipt["checks"]["recorded_inputs_unchanged"])
        self.assertFalse(receipt["guest_assertions"]["independent_host_observations"])
        self.assertEqual(receipt["guest_assertions"]["state"], "completed")
        self.assertEqual(
            Path(receipt["guest_test_binary"]["path"]).parent,
            self.run_dir / "build",
        )
        after = {
            str(p.relative_to(self.repo)): p.read_bytes()
            for p in self.repo.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        self.assertIn("guest_regression", receipt["source_files"])
        self.assertIn("linker_script", receipt["source_files"])

    def test_existing_output_is_rejected_before_any_command(self):
        self.run_dir.mkdir()
        old = self.run_dir / "system.terminal"
        old.write_bytes(VERIFY.EXPECTED_BYTES)
        with self.assertRaises(FileExistsError):
            self.verify()
        self.assertEqual(self.calls, [])
        self.assertEqual(old.read_bytes(), VERIFY.EXPECTED_BYTES)
        self.assertFalse((self.run_dir / "guest_uart_regression_receipt.json").exists())

    def test_relative_outdir_is_resolved_in_caller_context_once(self):
        caller = self.base / "caller"
        caller.mkdir()
        before = Path.cwd()
        try:
            os.chdir(caller)
            receipt = self.verify("relative-output")
        finally:
            os.chdir(before)
        directory = caller / "relative-output"
        self.assertEqual(receipt["state"], "passed", receipt["errors"])
        self.assertEqual(receipt["evidence_directory"], str(directory))
        self.assertEqual(
            Path(receipt["terminal_output"]["path"]),
            directory / "simulator/system.terminal",
        )
        simulation = [c for c in self.calls if c[0][0] == str(self.binary)][0]
        self.assertIn("--outdir=" + str(directory / "simulator"), simulation[0])
        self.assertEqual(simulation[1]["cwd"], str(self.repo))
        self.assertFalse((self.repo / "relative-output").exists())

    def test_paths_are_argv_data_without_shell_or_pipeline_interpretation(self):
        self.verify()
        cpp = [
            argv
            for argv, _ in self.calls
            if argv[0] == str(self.tools["cpp"]) and argv[-1] != "--version"
        ][0]
        self.assertIn(str(self.repo / "benchmarks/sys_validation/gemm/sw/boot.s"), cpp)
        self.assertIn(";", cpp[1])
        for argv, options in self.calls:
            self.assertIsInstance(argv, list)
            self.assertFalse(options.get("shell", False))
            self.assertNotIn("|", argv)
        labels = [c["label"] for c in self.receipt_on_disk()["commands"]]
        self.assertIn("boot-cpp", labels)
        self.assertIn("boot-as", labels)

    def test_timeout_saves_partial_logs_and_nonpassing_receipt(self):
        self.behavior = "timeout"
        receipt = self.verify(timeout_seconds=0.25)
        self.assertEqual(receipt["state"], "timed_out")
        self.assertEqual(receipt, self.receipt_on_disk())
        command = receipt["commands"][-1]
        self.assertEqual(command["state"], "timed_out")
        self.assertEqual(command["timeout_seconds"], 0.25)
        self.assertEqual(Path(command["stdout"]).read_bytes(), b"started\n")
        self.assertEqual(Path(command["stderr"]).read_bytes(), b"stalled\n")
        self.assertIn("guest_test_binary", receipt)

    def test_compile_failure_keeps_logs_and_stops_before_simulation(self):
        self.behavior = "compiler_failure"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertEqual(receipt["commands"][-1]["label"], "boot-cpp")
        self.assertEqual(
            Path(receipt["commands"][-1]["stderr"]).read_bytes(),
            b"compiler failed\n",
        )
        self.assertFalse(any(argv[0] == str(self.binary) for argv, _ in self.calls))

    def test_guest_failure_with_zero_simulator_status_fails(self):
        self.behavior = "guest_failure"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertFalse(receipt["checks"]["exact_bytes_match"])
        self.assertFalse(receipt["checks"]["contains_passed_marker"])
        self.assertEqual(receipt["guest_assertions"]["state"], "not_completed")

    def test_missing_terminal_does_not_reuse_any_passed_bytes(self):
        self.behavior = "missing_terminal"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertNotIn("terminal_output", receipt)
        self.assertTrue(receipt["errors"])

    def test_unexpected_exit_fails_even_with_exact_uart_bytes(self):
        self.behavior = "wrong_exit"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertTrue(receipt["checks"]["exact_bytes_match"])
        self.assertFalse(receipt["checks"]["expected_simulator_exit"])
        self.assertEqual(receipt["guest_assertions"]["state"], "not_completed")

    def test_nonzero_simulator_status_fails_despite_valid_marker(self):
        self.behavior = "simulator_failure"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertEqual(receipt["commands"][-1]["returncode"], 3)

    def test_changed_recorded_inputs_invalidate_successful_output(self):
        self.behavior = "source_drift"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertFalse(receipt["checks"]["recorded_inputs_unchanged"])
        self.assertIn("syscalls", receipt["errors"][-1])

    def test_oversized_terminal_fails_without_expanding_receipt_data(self):
        self.behavior = "oversized_terminal"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertNotIn("terminal_output", receipt)
        self.assertIn("bounded", receipt["errors"][-1])

    def test_optional_binary_and_board_configuration_are_recorded(self):
        alternative = self.repo / "configs/SALAM/generated/native_uart.py"
        alternative.write_text("# Different selected wrapper\n")
        receipt = self.verify(simulator=self.binary, config_script=alternative)
        self.assertEqual(receipt["state"], "passed", receipt["errors"])
        self.assertEqual(
            receipt["source_files"]["board_configuration"]["path"],
            str(alternative),
        )

    def test_invalid_timeout_does_not_create_a_study(self):
        for timeout in (0, -1, False, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    self.verify(timeout_seconds=timeout)
                self.assertFalse(self.run_dir.exists())
        self.assertEqual(self.calls, [])

    def test_modern_default_and_explicit_legacy_cpu_select_argv_and_receipt(self):
        for cpu in ("ArmO3CPU", "DerivO3CPU"):
            with self.subTest(cpu=cpu):
                options = {} if cpu == "ArmO3CPU" else {"cpu_type": cpu}
                receipt = self.verify(outdir=self.base / ("cpu-" + cpu), **options)
                self.assertEqual(receipt["state"], "passed", receipt["errors"])
                self.assertEqual(receipt["requested_cpu_type"], cpu)
                argv, _ = self.calls[-1]
                self.assertIn("--cpu-type=" + cpu, argv)
                self.assertEqual(
                    len([arg for arg in argv if arg.startswith("--cpu-type=")]),
                    1,
                )

    def test_cpu_identifier_validation_precedes_study_creation(self):
        for value in (
            None,
            True,
            12,
            "",
            "Arm O3CPU",
            "ArmO3CPU;touch",
            "--ArmO3CPU",
        ):
            with self.subTest(cpu=value):
                with self.assertRaisesRegex(ValueError, "CPU identifier"):
                    self.verify(cpu_type=value)
                self.assertFalse(self.run_dir.exists())
        self.assertEqual(self.calls, [])

    def test_cli_forwards_explicit_cpu_selection(self):
        arguments = [
            "verify_guest_uart.py",
            "--repo-root",
            str(self.repo),
            "--outdir",
            str(self.run_dir),
            "--cpu-type",
            "DerivO3CPU",
        ]
        with (
            patch.object(VERIFY.sys, "argv", arguments),
            patch.object(
                VERIFY, "run_verification", return_value={"state": "passed"}
            ) as run,
            patch("builtins.print"),
        ):
            self.assertEqual(VERIFY.main(), 0)
        self.assertEqual(run.call_args.kwargs["cpu_type"], "DerivO3CPU")

    def test_expected_phrase_before_wrong_actual_exit_cannot_pass(self):
        self.behavior = "misleading_exit_mention"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "failed")
        self.assertTrue(receipt["checks"]["exact_bytes_match"])
        self.assertFalse(receipt["checks"]["expected_simulator_exit"])
        self.assertEqual(
            receipt["simulator_exit"]["reason"], "simulation time limit reached"
        )
        self.assertEqual(receipt["simulator_exit"]["exit_line_count"], 1)

    def test_multiple_or_malformed_final_exit_lines_cannot_pass(self):
        for behavior in ("multiple_exit_lines", "malformed_final_exit"):
            with self.subTest(behavior=behavior):
                self.behavior = behavior
                receipt = self.verify(outdir=self.base / behavior)
                self.assertEqual(receipt["state"], "failed")
                self.assertFalse(receipt["checks"]["expected_simulator_exit"])
                self.assertEqual(receipt["simulator_exit"]["exit_line_count"], 2)

    def test_ordinary_warnings_after_one_valid_exit_are_allowed(self):
        self.behavior = "warning_after_exit"
        receipt = self.verify()
        self.assertEqual(receipt["state"], "passed", receipt["errors"])
        self.assertEqual(receipt["simulator_exit"]["tick"], 1000)
        self.assertEqual(receipt["simulator_exit"]["exit_line_count"], 1)


if __name__ == "__main__":
    unittest.main()
