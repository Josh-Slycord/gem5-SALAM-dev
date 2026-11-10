# SPDX-License-Identifier: BSD-3-Clause
"""Real temporary Git repositories exercise metadata-only hygiene checks."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench import repository_hygiene as hygiene


class RepositoryHygieneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="salam-git-hygiene-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.git("init", "--quiet")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("config", "user.name", "Hygiene Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write(".gitattributes", b"* -text\n")
        self.write("README.md", b"source\n")
        self.git("add", "--", ".gitattributes", "README.md")
        self.base = self.commit("base")

    def git(self, *args, env=None):
        return (
            subprocess.run(
                [
                    "git",
                    "--no-optional-locks",
                    "-c",
                    "core.fsmonitor=false",
                    "-C",
                    str(self.repo),
                    *args,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            .stdout.decode("utf-8")
            .strip()
        )

    def write(self, name, data=b"fixture\n"):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def commit(self, subject="change"):
        self.git("commit", "--quiet", "--allow-empty", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def add_commit(self, *paths):
        self.git("add", "-f", "--", *paths)
        return self.commit()

    def audit(self, head=None, base=None, **kwargs):
        return hygiene.audit_repository(
            self.repo,
            base=self.base if base is None else base,
            head=head or self.git("rev-parse", "HEAD"),
            **kwargs,
        )

    def assert_passed(self, report):
        self.assertEqual(report["state"], "passed", report)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["violations"], [])

    def test_required_generated_ir_golden_and_authored_inputs_are_allowed(self):
        paths = [
            "src/hwacc/HWModeling/generated/functionalunits/base.hh",
            "src/hwacc/HWModeling/generated/instructions/add.cc",
            "benchmarks/example/hw/fixture.ll",
            "src/systemc/tests/example/golden/reference.log",
            "benchmarks/legacy/example/config.ini",
        ]
        for name in paths:
            self.write(name)
        result = self.audit(self.add_commit(*paths))
        self.assert_passed(result)
        self.assertEqual({row["path"] for row in result["checked_files"]}, set(paths))

    def test_unchanged_large_historical_blob_is_not_retroactively_rejected(self):
        self.write("historical/large.dat", b"x" * (hygiene.MAX_BLOB_BYTES + 1))
        self.base = self.add_commit("historical/large.dat")
        self.write("README.md", b"new source\n")
        report = self.audit(self.add_commit("README.md"))
        self.assert_passed(report)
        self.assertEqual(
            [row["path"] for row in report["checked_files"]], ["README.md"]
        )

    def test_changed_large_blob_fails_and_exact_limit_passes(self):
        self.write("new.dat", b"x" * hygiene.MAX_BLOB_BYTES)
        self.assert_passed(self.audit(self.add_commit("new.dat")))
        self.write("new.dat", b"x" * (hygiene.MAX_BLOB_BYTES + 1))
        report = self.audit(self.add_commit("new.dat"))
        self.assertEqual(report["state"], "failed")
        self.assertEqual(report["violations"][0]["rule"], "blob-size")
        self.assertEqual(
            report["checked_files"][0]["bytes"], hygiene.MAX_BLOB_BYTES + 1
        )

    def test_forced_ignored_runtime_outputs_fail(self):
        paths = [
            "workbench/evidence/run/output.json",
            "workbench/workspace.json",
            "workbench/runs/run/stdout",
            "workbench/results/run/stats.txt",
            "workbench/releases/private.zip",
            "workbench/gui-variants/local/config.py",
            "build/ARM/gem5.opt",
            "m5out/stats.txt",
        ]
        self.write(".gitignore", b"/workbench/evidence/\n/workbench/workspace.json\n")
        for name in paths:
            self.write(name)
        report = self.audit(self.add_commit(".gitignore", *paths))
        self.assertEqual(report["state"], "failed")
        self.assertEqual({item["path"] for item in report["violations"]}, set(paths))

    def test_rename_into_runtime_directory_is_caught(self):
        self.write("source.txt")
        self.base = self.add_commit("source.txt")
        target = self.repo / "workbench/evidence/renamed.txt"
        target.parent.mkdir(parents=True)
        self.git("mv", "--", "source.txt", "workbench/evidence/renamed.txt")
        report = self.audit(self.commit())
        self.assertEqual(report["state"], "failed")
        self.assertEqual(
            report["violations"][0]["path"], "workbench/evidence/renamed.txt"
        )

    def test_nested_cache_and_compiled_payloads_fail(self):
        paths = ["pkg/__pycache__/a.pyc", "kernel.elf", "result.bc", "backup.bundle"]
        for name in paths:
            self.write(name)
        report = self.audit(self.add_commit(*paths))
        self.assertEqual(report["state"], "failed")
        self.assertEqual({item["path"] for item in report["violations"]}, set(paths))

    def test_dirty_untracked_and_ignored_bytes_cannot_change_commit_scan(self):
        self.write("docs/new.md", b"committed\n")
        head = self.add_commit("docs/new.md")
        expected = self.audit(head)
        self.write("docs/new.md", b"dirty\n" * 100)
        self.write("workbench/workspace.json")
        self.write("untracked.elf")
        self.assertEqual(expected, self.audit(head))

    def test_spaces_newlines_and_leading_dash_are_literal_paths(self):
        paths = ["docs/a b.md", "docs/line\nbreak.md", "-literal.md"]
        for name in paths:
            self.write(name)
        report = self.audit(self.add_commit(*paths))
        self.assert_passed(report)
        self.assertEqual({row["path"] for row in report["checked_files"]}, set(paths))

    def test_dangling_symlink_is_not_followed(self):
        (self.repo / "source-link.md").symlink_to(self.directory / "nonexistent")
        report = self.audit(self.add_commit("source-link.md"))
        self.assert_passed(report)
        self.assertEqual(report["checked_files"][0]["mode"], "120000")
        self.assertEqual(report["checked_files"][0]["object_kind"], "blob")

    def test_missing_or_symbolic_revision_never_passes_as_empty_diff(self):
        for base in ("f" * 40, "HEAD", "--all", None):
            with self.subTest(base=base):
                report = hygiene.audit_repository(self.repo, base=base, head=self.base)
                self.assertEqual(report["state"], "failed")
                self.assertTrue(report["errors"])

    def test_unrelated_histories_fail_closed(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        unrelated = self.git("commit-tree", tree, "-m", "unrelated")
        report = self.audit(unrelated)
        self.assertEqual(report["state"], "failed")
        self.assertTrue(report["errors"])

    def test_shallow_checkout_with_unavailable_base_fails_closed(self):
        self.write("README.md", b"second\n")
        head = self.add_commit("README.md")
        target = self.directory / "shallow"
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--no-local",
                self.repo.as_uri(),
                str(target),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        report = hygiene.audit_repository(target, base=self.base, head=head)
        self.assertEqual(report["state"], "failed")
        self.assertTrue(report["errors"])

    def test_staged_mode_checks_index_bytes_not_unstaged_files(self):
        self.write("docs/staged.md", b"index bytes\n")
        self.git("add", "--", "docs/staged.md")
        self.write("docs/staged.md", b"x" * (hygiene.MAX_BLOB_BYTES + 1))
        report = hygiene.audit_repository(self.repo, staged=True)
        self.assert_passed(report)
        self.assertEqual(report["checked_files"][0]["bytes"], len(b"index bytes\n"))

    def test_staged_mode_catches_forced_output_and_rejects_mixed_selection(self):
        self.write("workbench/workspace.json")
        self.git("add", "-f", "--", "workbench/workspace.json")
        self.assertEqual(
            hygiene.audit_repository(self.repo, staged=True)["state"], "failed"
        )
        mixed = hygiene.audit_repository(self.repo, staged=True, base=self.base)
        self.assertEqual(mixed["state"], "failed")
        self.assertTrue(mixed["errors"])

    def test_hook_selected_alternate_index_is_respected(self):
        alternate = self.directory / "selected-index"
        env = dict(os.environ, GIT_INDEX_FILE=str(alternate))
        self.git("read-tree", "HEAD", env=env)
        self.write("workbench/workspace.json")
        self.git("add", "-f", "--", "workbench/workspace.json", env=env)
        self.assert_passed(hygiene.audit_repository(self.repo, staged=True))
        with patch.dict(os.environ, {"GIT_INDEX_FILE": str(alternate)}):
            report = hygiene.audit_repository(self.repo, staged=True)
        self.assertEqual(report["state"], "failed")
        self.assertEqual(report["violations"][0]["path"], "workbench/workspace.json")

    def test_deletions_are_allowed_and_do_not_read_worktree(self):
        self.write("workbench/evidence/old.json")
        self.base = self.add_commit("workbench/evidence/old.json")
        self.git("rm", "--", "workbench/evidence/old.json")
        report = self.audit(self.commit())
        self.assert_passed(report)
        self.assertEqual(report["checked_files"], [])

    def test_pull_request_event_uses_actual_head_and_base(self):
        event = {
            "pull_request": {"base": {"sha": self.base}, "head": {"sha": self.base}}
        }
        self.assertEqual(
            hygiene.revision_pair_for_event(self.repo, "pull_request", event, "e" * 40),
            (self.base, self.base),
        )

    def test_new_branch_and_manual_event_resolve_recorded_remote_main(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        event = {"before": "0" * 40, "after": self.base}
        self.assertEqual(
            hygiene.revision_pair_for_event(self.repo, "push", event, self.base),
            (self.base, self.base),
        )
        self.assertEqual(
            hygiene.revision_pair_for_event(
                self.repo, "workflow_dispatch", {}, self.base
            ),
            (self.base, self.base),
        )

    def test_ordinary_push_does_not_need_remote_main_and_mismatch_fails(self):
        event = {"before": self.base, "after": self.base}
        self.assertEqual(
            hygiene.revision_pair_for_event(self.repo, "push", event, self.base),
            (self.base, self.base),
        )
        with self.assertRaises(hygiene.HygieneError):
            hygiene.revision_pair_for_event(self.repo, "push", event, "e" * 40)

    def test_missing_new_branch_base_and_malformed_events_fail(self):
        events = [
            ("push", {"before": "0" * 40, "after": self.base}),
            ("pull_request", {}),
            ("pull_request", {"pull_request": []}),
            (
                "pull_request",
                {"pull_request": {"base": {"sha": 17}, "head": {"sha": self.base}}},
            ),
            ("unsupported", {}),
        ]
        for name, event in events:
            with self.subTest(name=name, event=event):
                with self.assertRaises(hygiene.HygieneError):
                    hygiene.revision_pair_for_event(self.repo, name, event, self.base)

    def test_cli_reports_failure_and_does_not_claim_simulation(self):
        output = self.directory / "report.json"
        process = subprocess.run(
            [
                sys.executable,
                str(Path(hygiene.__file__)),
                "--repo",
                str(self.repo),
                "--base",
                "f" * 40,
                "--head",
                self.base,
                "--report",
                str(output),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["state"], "failed")
        self.assertFalse(report["simulator_run"])
        self.assertFalse(report["simulator_built"])

    def test_cli_event_file_errors_are_nonzero_and_structured(self):
        event = self.directory / "event.json"
        event.write_text("[]", encoding="utf-8")
        process = subprocess.run(
            [
                sys.executable,
                str(Path(hygiene.__file__)),
                "--repo",
                str(self.repo),
                "--github-event",
                str(event),
                "--event-name",
                "pull_request",
                "--current-sha",
                self.base,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        self.assertEqual(json.loads(process.stdout)["state"], "failed")

    def test_subdirectory_is_not_silently_another_repo_root(self):
        folder = self.repo / "subdirectory"
        folder.mkdir()
        report = hygiene.audit_repository(folder, base=self.base, head=self.base)
        self.assertEqual(report["state"], "failed")
        self.assertTrue(report["errors"])

    def test_multiple_merge_bases_fail_closed(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        left = self.git("commit-tree", tree, "-p", self.base, "-m", "left")
        right = self.git("commit-tree", tree, "-p", self.base, "-m", "right")
        first = self.git("commit-tree", tree, "-p", left, "-p", right, "-m", "first")
        second = self.git("commit-tree", tree, "-p", right, "-p", left, "-m", "second")
        report = self.audit(first, base=second)
        self.assertEqual(report["state"], "failed")
        self.assertTrue(report["errors"])

    def test_push_event_uses_direct_range_even_when_head_moves_backwards(self):
        self.write("workbench/workspace.json")
        old = self.add_commit("workbench/workspace.json")
        self.git("rm", "--", "workbench/workspace.json")
        current = self.commit()
        event = self.directory / "push.json"
        event.write_text(
            json.dumps({"before": current, "after": old}), encoding="utf-8"
        )
        process = subprocess.run(
            [
                sys.executable,
                str(Path(hygiene.__file__)),
                "--repo",
                str(self.repo),
                "--github-event",
                str(event),
                "--event-name",
                "push",
                "--current-sha",
                old,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        report = json.loads(process.stdout)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(report["comparison_kind"], "direct")
        self.assertEqual(report["comparison_base"], current)
        self.assertEqual(report["violations"][0]["path"], "workbench/workspace.json")

    def test_cli_never_overwrites_an_existing_report(self):
        output = self.directory / "preserved.json"
        output.write_bytes(b"preserve these bytes")
        process = subprocess.run(
            [
                sys.executable,
                str(Path(hygiene.__file__)),
                "--repo",
                str(self.repo),
                "--base",
                self.base,
                "--head",
                self.base,
                "--report",
                str(output),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        self.assertEqual(output.read_bytes(), b"preserve these bytes")
        self.assertEqual(json.loads(process.stdout)["state"], "failed")

    def test_local_output_case_variants_are_rejected(self):
        self.write("WORKBENCH/EVIDENCE/output.json")
        report = self.audit(self.add_commit("WORKBENCH/EVIDENCE/output.json"))
        self.assertEqual(report["state"], "failed")
        self.assertEqual(report["violations"][0]["rule"], "local-output")

    def test_declared_promisor_repository_fails_without_contacting_remote(self):
        self.git("config", "remote.unavailable.promisor", "true")
        report = self.audit(self.base)
        self.assertEqual(report["state"], "failed")
        self.assertTrue(report["errors"])
        self.assertIn("partial/promisor", report["errors"][0])
        self.assertEqual(report["checked_files"], [])

    def test_known_generated_docs_and_analysis_results_fail_when_force_added(self):
        paths = [
            "docs/_build/html/index.html",
            "src/doxygen/html/index.html",
            "cacti-SALAM/results/report.csv",
            "ext/mcpat/results/output.log",
        ]
        self.write(
            ".gitignore",
            b"docs/_build/\nsrc/doxygen/\ncacti-SALAM/results/\next/mcpat/results/\n",
        )
        for name in paths:
            self.write(name)
        report = self.audit(self.add_commit(".gitignore", *paths))
        self.assertEqual(report["state"], "failed")
        failures = {row["path"]: row["rule"] for row in report["violations"]}
        self.assertEqual(set(failures), set(paths))
        for name in paths:
            with self.subTest(path=name):
                self.assertEqual(failures[name], "local-output")


if __name__ == "__main__":
    unittest.main()
