"""Synthetic subprocess acceptance tests; none establish gem5 correctness."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from salam_workbench.runner import file_hash, run_experiment

FIXTURE = r"""
import argparse, pathlib, sys, time
p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('mode');p.add_argument('--change-input');p.add_argument('--change-snapshot',action='store_true');a=p.parse_args()
out=pathlib.Path(a.outdir);out.mkdir(exist_ok=True)
print('synthetic fixture started',flush=True)
print('fixture stderr',file=sys.stderr,flush=True)
if a.mode=='timeout':
 time.sleep(30)
elif a.mode not in ('missing','stdout_only'):
 text={'good':'Check Passed\n','bad':'Check Failed\n','contradictory':'Check Passed\nCheck Failed\n','no_marker':'Job complete\n','crash':'Check Passed\n','wrong_exit':'Check Passed\n','no_exit':'Check Passed\n'}[a.mode]
 (out/'system.terminal').write_text(text)
if a.mode=='stdout_only':print('Check Passed')
if a.change_input:pathlib.Path(a.change_input).write_text('changed')
if a.change_snapshot:next((out.parent/'inputs').iterdir()).write_text('changed snapshot')
if a.mode!='no_exit':print('Exiting @ tick 1234 because '+('simulate() limit reached' if a.mode=='wrong_exit' else 'm5_exit instruction encountered'))
(out/'stats.txt').write_text('simTicks 1234\n')
if a.mode=='crash':sys.exit(3)
"""


class FileHashIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="salam-hash-fixture-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "fixture.bin"
        self.path.write_bytes(b"0123456789" * 1000)

    class Reader:
        """Keep a real descriptor while simulating the stream's read behavior."""

        def __init__(self, handle, *, early_eof=False, read_error=False):
            self.handle = handle
            self.early_eof = early_eof
            self.read_error = read_error
            self.calls = 0

        def fileno(self):
            return self.handle.fileno()

        def read(self, requested):
            self.calls += 1
            if self.read_error:
                raise OSError("synthetic read failure")
            if self.early_eof and self.calls > 1:
                return b""
            return self.handle.read(min(37, requested))

        def __enter__(self):
            return self

        def __exit__(self, *arguments):
            self.handle.close()

    def test_complete_file_keeps_standard_sha256_contract(self):
        for payload in (b"", b"abc", b"x" * (1024 * 1024 + 43)):
            with self.subTest(size=len(payload)):
                self.path.write_bytes(payload)
                self.assertEqual(
                    file_hash(self.path), hashlib.sha256(payload).hexdigest()
                )

    def test_early_eof_with_unchanged_real_descriptor_is_rejected(self):
        reader = self.Reader(self.path.open("rb"), early_eof=True)
        with mock.patch.object(Path, "open", return_value=reader):
            with self.assertRaisesRegex(OSError, r"expected 10000 bytes, read 37"):
                file_hash(self.path)
        self.assertEqual(reader.calls, 2)
        self.assertTrue(reader.handle.closed)
        self.assertEqual(self.path.stat().st_size, 10000)

    def test_short_reads_that_cover_the_whole_file_are_valid(self):
        expected = hashlib.sha256(self.path.read_bytes()).hexdigest()
        reader = self.Reader(self.path.open("rb"))
        with mock.patch.object(Path, "open", return_value=reader):
            self.assertEqual(file_hash(self.path), expected)
        self.assertGreater(reader.calls, 2)
        self.assertTrue(reader.handle.closed)

    def test_descriptor_identity_size_and_nanosecond_times_must_remain_stable(
        self,
    ):
        observed = self.path.stat()
        fields = (
            "st_mode",
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        before = {field: getattr(observed, field) for field in fields}
        for changed_field in fields[1:]:
            with self.subTest(changed=changed_field):
                after = dict(before)
                after[changed_field] += 1
                with mock.patch(
                    "salam_workbench.runner.os.fstat",
                    side_effect=[
                        SimpleNamespace(**before),
                        SimpleNamespace(**after),
                    ],
                ) as fstat:
                    with self.assertRaisesRegex(OSError, "File changed while hashing"):
                        file_hash(self.path)
                self.assertEqual(fstat.call_count, 2)

    def test_read_error_propagates_without_retry_or_digest(self):
        reader = self.Reader(self.path.open("rb"), read_error=True)
        with mock.patch.object(Path, "open", return_value=reader):
            with self.assertRaisesRegex(OSError, "synthetic read failure"):
                file_hash(self.path)
        self.assertEqual(reader.calls, 1)
        self.assertTrue(reader.handle.closed)

    def test_nonregular_descriptor_is_rejected_before_reading(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        reader = self.Reader(os.fdopen(read_fd, "rb"))
        with mock.patch.object(Path, "open", return_value=reader):
            with self.assertRaisesRegex(OSError, "nonregular file"):
                file_hash(self.path)
        self.assertEqual(reader.calls, 0)
        self.assertTrue(reader.handle.closed)


class RunnerAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="salam-runner-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.fixture = self.base / "fake_gem5.py"
        self.fixture.write_text(FIXTURE, encoding="utf-8")

    def run_fixture(self, mode, **kwargs):
        defaults = dict(
            cwd=self.base,
            runs_root=self.base / "runs",
            experiment={
                "evidence_kind": "synthetic-subprocess-fixture",
                "mode": mode,
            },
            input_paths=[self.fixture],
            timeout_seconds=10,
        )
        defaults.update(kwargs)
        result = run_experiment([sys.executable, str(self.fixture)], [mode], **defaults)
        self.assertEqual(
            result,
            json.loads((Path(result["run_directory"]) / "run.json").read_text()),
        )
        return result

    def test_success_has_complete_provenance_and_hashes(self):
        result = self.run_fixture("good", env_overrides={"M5_PATH": str(self.base)})
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["simulator_exit"]["tick"], 1234)
        self.assertEqual(result["correctness"]["passed_markers"], 1)
        self.assertTrue(result["inputs"][0]["unchanged_after_run"])
        self.assertTrue(result["executable"]["unchanged_after_run"])
        self.assertEqual(result["environment"]["M5_PATH"], str(self.base))
        self.assertIn(
            "--outdir=" + str(Path(result["run_directory"]) / "simulator"),
            result["argv"],
        )
        for artifact in result["artifacts"]:
            self.assertEqual(
                artifact["sha256"],
                file_hash(Path(result["run_directory"]) / artifact["path"]),
            )

    def test_explicit_fail_and_contradiction_are_failed(self):
        for mode in ["bad", "contradictory"]:
            with self.subTest(mode=mode):
                self.assertEqual(self.run_fixture(mode)["state"], "failed")

    def test_zero_exit_without_guest_evidence_is_incomplete(self):
        for mode in ["missing", "stdout_only", "no_marker", "no_exit"]:
            with self.subTest(mode=mode):
                self.assertEqual(self.run_fixture(mode)["state"], "incomplete")

    def test_exit_code_and_reason_are_required(self):
        for mode in ["crash", "wrong_exit"]:
            with self.subTest(mode=mode):
                self.assertEqual(self.run_fixture(mode)["state"], "failed")

    def test_timeout_keeps_output(self):
        result = self.run_fixture("timeout", timeout_seconds=1)
        self.assertEqual(result["state"], "timed_out")
        self.assertIn(
            "fixture started",
            (Path(result["run_directory"]) / "stdout.txt").read_text(),
        )
        self.assertIn(
            "fixture stderr",
            (Path(result["run_directory"]) / "stderr.txt").read_text(),
        )

    def test_automatically_unique_and_explicit_collision_preserves_old_run(
        self,
    ):
        first = self.run_fixture("good")
        second = self.run_fixture("good")
        self.assertNotEqual(first["run_id"], second["run_id"])
        previous = (Path(first["run_directory"]) / "run.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_fixture("good", run_id=first["run_id"])
        self.assertEqual(
            previous, (Path(first["run_directory"]) / "run.json").read_bytes()
        )

    def test_preflight_failure_still_has_run_record(self):
        result = self.run_fixture("good", input_paths=[self.base / "missing-input"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["stage"], "validation")
        self.assertIsNone(result["return_code"])

    def test_supplied_output_directory_is_rejected(self):
        for option in [
            "--outdir=/tmp/wrong",
            "--outdir",
            "-d",
            "-d/tmp/wrong",
        ]:
            with self.subTest(option=option):
                result = run_experiment(
                    [sys.executable, str(self.fixture)],
                    [option, "good"],
                    cwd=self.base,
                    runs_root=self.base / "runs",
                    experiment={},
                )
                self.assertEqual(result["state"], "failed")
                self.assertEqual(result["stage"], "validation")

    def test_unknown_environment_not_captured_or_forwarded(self):
        result = self.run_fixture(
            "good", env_overrides={"NOT_ALLOWED_SECRET": "fixture-value"}
        )
        self.assertEqual(result["state"], "failed")
        self.assertNotIn("fixture-value", json.dumps(result))

    def test_mutated_input_prevents_success(self):
        payload = self.base / "input.txt"
        payload.write_text("original")
        result = run_experiment(
            [sys.executable, str(self.fixture)],
            ["good", "--change-input", str(payload)],
            cwd=self.base,
            runs_root=self.base / "runs",
            experiment={},
            input_paths=[payload],
        )
        self.assertEqual(result["state"], "incomplete")
        self.assertFalse(result["inputs"][0]["unchanged_after_run"])

    def test_missing_required_output_prevents_success_despite_pass_marker(
        self,
    ):
        result = self.run_fixture(
            "good",
            required_artifacts=["simulator/stats.txt", "simulator/config.ini"],
        )
        self.assertEqual(result["correctness"]["outcome"], "passed")
        self.assertEqual(result["state"], "incomplete")
        self.assertEqual(
            result["required_artifact_checks"],
            [
                {"path": "simulator/stats.txt", "available": True},
                {"path": "simulator/config.ini", "available": False},
            ],
        )

    def test_existing_required_files_allow_success_but_directory_does_not(
        self,
    ):
        result = self.run_fixture(
            "good",
            required_artifacts=[
                "simulator\\stats.txt",
                "simulator/system.terminal",
            ],
        )
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["required_artifacts"][0], "simulator/stats.txt")
        self.assertEqual(
            self.run_fixture("good", required_artifacts=["simulator"])["state"],
            "incomplete",
        )

    def test_required_paths_reject_traversal_and_platform_escapes_before_launch(
        self,
    ):
        for path in [
            "../outside",
            "/absolute",
            "C:\\absolute",
            "C:relative",
            "simulator/../stats.txt",
            "simulator\\..\\stats.txt",
            "simulator/stats.txt:payload",
            "./stdout.txt",
            "",
            "run.json",
        ]:
            with self.subTest(path=path):
                result = self.run_fixture("good", required_artifacts=[path])
                self.assertEqual(result["state"], "failed")
                self.assertEqual(result["stage"], "validation")
                self.assertIsNone(result["return_code"])

    def test_snapshot_retains_original_when_live_input_changes(self):
        payload = self.base / "input.txt"
        payload.write_text("original")
        result = run_experiment(
            [sys.executable, str(self.fixture)],
            ["good", "--change-input", str(payload)],
            cwd=self.base,
            runs_root=self.base / "runs",
            experiment={},
            input_paths=[payload],
            snapshot_inputs=True,
        )
        self.assertEqual(result["state"], "incomplete")
        item = result["inputs"][0]
        snapshot = item["snapshot"]
        stored = Path(result["run_directory"]) / snapshot["path"]
        self.assertEqual(stored.read_text(), "original")
        self.assertFalse(item["unchanged_after_run"])
        self.assertTrue(snapshot["unchanged_after_run"])
        self.assertEqual(snapshot["sha256"], item["sha256"])
        self.assertEqual(snapshot["sha256"], file_hash(stored))
        self.assertIn(
            snapshot["path"], [entry["path"] for entry in result["artifacts"]]
        )

    def test_modified_snapshot_prevents_success_even_when_original_is_unchanged(
        self,
    ):
        result = run_experiment(
            [sys.executable, str(self.fixture)],
            ["good", "--change-snapshot"],
            cwd=self.base,
            runs_root=self.base / "runs",
            experiment={},
            input_paths=[self.fixture],
            snapshot_inputs=True,
        )
        self.assertEqual(result["state"], "incomplete")
        self.assertTrue(result["inputs"][0]["unchanged_after_run"])
        self.assertFalse(result["inputs"][0]["snapshot"]["unchanged_after_run"])

    def test_numbered_snapshots_preserve_same_basename_inputs_without_collision(
        self,
    ):
        payloads = []
        for name in ["first", "second"]:
            folder = self.base / name
            folder.mkdir()
            payload = folder / "input.txt"
            payload.write_text(name)
            payloads.append(payload)
        result = self.run_fixture("good", input_paths=payloads, snapshot_inputs=True)
        self.assertEqual(result["state"], "passed")
        snapshots = [item["snapshot"]["path"] for item in result["inputs"]]
        self.assertEqual(snapshots, ["inputs/0001-input.txt", "inputs/0002-input.txt"])
        self.assertEqual(
            [(Path(result["run_directory"]) / path).read_text() for path in snapshots],
            ["first", "second"],
        )
        self.assertNotIn("snapshot", result["executable"])

    def test_oversized_snapshot_is_explicit_preflight_failure(self):
        with mock.patch("salam_workbench.runner.MAX_SNAPSHOT_BYTES", 1):
            result = self.run_fixture("good", snapshot_inputs=True)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["stage"], "validation")
        self.assertIsNone(result["return_code"])
        self.assertTrue(any("snapshot limit" in error for error in result["errors"]))

    def test_snapshot_collision_preserves_existing_bytes_and_does_not_launch(
        self,
    ):
        payloads = []
        for name in ["first", "second"]:
            folder = self.base / name
            folder.mkdir()
            payload = folder / "input.txt"
            payload.write_text(name)
            payloads.append(payload)
        from salam_workbench import runner

        copy = runner.shutil.copyfileobj

        def introduce_collision(source, target, **kwargs):
            collision = Path(target.name).parent / "0002-input.txt"
            collision.write_text("existing evidence")
            return copy(source, target, **kwargs)

        with mock.patch(
            "salam_workbench.runner.shutil.copyfileobj",
            side_effect=introduce_collision,
        ):
            result = self.run_fixture(
                "good", input_paths=payloads, snapshot_inputs=True
            )
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["return_code"])
        self.assertEqual(
            (Path(result["run_directory"]) / "inputs/0002-input.txt").read_text(),
            "existing evidence",
        )

    @unittest.skipIf(
        os.name == "nt", "Windows does not allow a separator inside a filename"
    )
    def test_snapshot_basename_cannot_inject_windows_style_traversal(self):
        payload = self.base / "part\\..\\..\\escape.txt"
        payload.write_text("input")
        result = self.run_fixture("good", input_paths=[payload], snapshot_inputs=True)
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["return_code"])
        self.assertFalse((Path(result["run_directory"]) / "escape.txt").exists())

    @unittest.skipIf(
        os.name == "nt",
        "Windows locks running executables; use a POSIX script executable",
    )
    def test_changed_executable_prevents_success(self):
        executable = self.base / "mutable_simulator"
        executable.write_text("#!" + sys.executable + "\n" + FIXTURE, encoding="utf-8")
        executable.chmod(0o700)
        result = run_experiment(
            [str(executable)],
            ["good", "--change-input", str(executable)],
            cwd=self.base,
            runs_root=self.base / "runs",
            experiment={},
        )
        self.assertEqual(result["correctness"]["outcome"], "passed")
        self.assertEqual(result["state"], "incomplete")
        self.assertFalse(result["executable"]["unchanged_after_run"])
        self.assertTrue(
            any("Executable changed" in error for error in result["errors"])
        )


if __name__ == "__main__":
    unittest.main()
