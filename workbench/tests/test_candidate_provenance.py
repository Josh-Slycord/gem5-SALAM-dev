# SPDX-License-Identifier: BSD-3-Clause
"""Regression checks for pinned bytes, dirty trees and non-authoritative hints."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_candidate_provenance.py"
SPEC = importlib.util.spec_from_file_location("candidate_provenance_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class CandidateProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pinned-provenance-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        subprocess.run(
            ["git", "init", "--quiet", "-b", "main", str(self.root)],
            check=True,
            capture_output=True,
        )
        # Use ordinary committed LF bytes on either Linux or Windows.
        (self.root / ".gitattributes").write_bytes(b"* -text\n")
        self.path = "src/hwacc/example.py"
        self.original = (
            b"# SPDX-License-Identifier: (MIT OR Apache-2.0)\n"
            b"# Copyright (c) 2020 Original Organization\n"
            b"# SALAM integration file; authorship is not a Git author name.\n"
        )
        self.write(self.path, self.original)
        self.write("SALAM-Configurator/template.py", b"# same committed template\n")
        self.write(
            "tools/SALAM-Configurator/template.py", b"# same committed template\n"
        )
        self.git("add", ".")
        self.commit("initial | fixture")
        self.pin = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args, input=None):
        return subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(self.root),
                *args,
            ],
            input=input,
            check=True,
            capture_output=True,
        ).stdout

    def commit(self, subject):
        self.git(
            "-c",
            "user.name=Josh Example",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            subject,
        )

    def write(self, path, payload):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination

    def row(self, report, path=None):
        return next(
            item for item in report["files"] if item["path"] == (path or self.path)
        )

    def test_dirty_deleted_and_untracked_files_cannot_change_pinned_inventory(self):
        before = AUDIT.audit_files(self.root, self.pin)
        self.write(self.path, b"# SPDX-License-Identifier: Uncommitted-Wrong-Tag\n")
        source = self.root / "tools/SALAM-Configurator/template.py"
        source.rename(source.with_name("untracked-elsewhere.py"))
        self.write("src/hwacc/new-untracked.py", b"# not in the selected commit\n")
        after = AUDIT.audit_files(self.root, self.pin)
        self.assertEqual(before, after)
        row = self.row(after)
        self.assertEqual(row["sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(row["bytes"], len(self.original))
        self.assertNotIn(
            "src/hwacc/new-untracked.py", [r["path"] for r in after["files"]]
        )

    def test_content_does_not_use_path_read_methods(self):
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("No worktree byte reads")
        ), patch.object(
            Path, "read_text", side_effect=AssertionError("No worktree text reads")
        ):
            report = AUDIT.audit_files(self.root, self.pin)
        self.assertEqual(
            self.row(report)["sha256"], hashlib.sha256(self.original).hexdigest()
        )

    def test_old_commit_remains_exact_after_later_commit(self):
        self.write(self.path, b"# committed later\n")
        self.write("src/hwacc/later.py", b"# new later file\n")
        self.git("add", ".")
        self.commit("later revision")
        old = AUDIT.audit_files(self.root, self.pin)
        head = AUDIT.audit_files(self.root, "HEAD")
        self.assertEqual(
            self.row(old)["sha256"], hashlib.sha256(self.original).hexdigest()
        )
        self.assertNotEqual(self.row(old)["sha256"], self.row(head)["sha256"])
        self.assertEqual(
            head["summary"]["pinned_commit"],
            self.git("rev-parse", "HEAD").decode().strip(),
        )

    def test_moving_requested_ref_during_audit_cannot_mix_revisions(self):
        real_tree = AUDIT._tree_entries

        def moved_tree(repo_root, selected):
            self.assertEqual(selected, self.pin)
            self.write(self.path, b"# branch moves after commit resolution\n")
            self.git("add", self.path)
            self.commit("moved requested HEAD")
            return real_tree(repo_root, selected)

        with patch.object(AUDIT, "_tree_entries", side_effect=moved_tree):
            report = AUDIT.audit_files(self.root, "HEAD")
        self.assertEqual(report["summary"]["pinned_commit"], self.pin)
        self.assertEqual(
            self.row(report)["sha256"], hashlib.sha256(self.original).hexdigest()
        )
        self.assertEqual(self.row(report)["git_log"]["latest_commit"]["hash"], self.pin)

    def test_duplicate_copy_facts_come_from_pinned_tree(self):
        report = AUDIT.audit_files(self.root, self.pin)
        pair = report["summary"]["corresponding_tree_paths"][0]
        self.assertTrue(pair["same_git_object"])
        self.write(
            "tools/SALAM-Configurator/template.py", b"# different but uncommitted\n"
        )
        self.assertEqual(report, AUDIT.audit_files(self.root, self.pin))
        self.git("add", ".")
        self.commit("change corresponding path")
        changed = AUDIT.audit_files(self.root, "HEAD")
        self.assertFalse(
            changed["summary"]["corresponding_tree_paths"][0]["same_git_object"]
        )

    def test_symlink_is_hashed_as_link_blob_without_filesystem_target(self):
        target = b"/outside/never-read-this-target.py"
        blob = self.git("hash-object", "-w", "--stdin", input=target).decode().strip()
        name = "src/hwacc/link.py"
        self.git("update-index", "--add", "--cacheinfo", "120000," + blob + "," + name)
        self.commit("record symlink without a worktree target")
        report = AUDIT.audit_files(self.root, "HEAD")
        row = self.row(report, name)
        self.assertEqual(row["git_mode"], "120000")
        self.assertEqual(row["git_blob"], blob)
        self.assertEqual(row["sha256"], hashlib.sha256(target).hexdigest())
        self.assertEqual(row["notice_scan"], "not_scanned_symlink_or_nonregular")
        self.assertIsNone(row["spdx_expression"])

    def test_bare_repository_needs_no_worktree_candidate_files(self):
        bare = Path(self.temporary.name) / "bare.git"
        subprocess.run(
            ["git", "clone", "--quiet", "--bare", str(self.root), str(bare)],
            check=True,
            capture_output=True,
        )
        report = AUDIT.audit_files(bare, self.pin)
        self.assertEqual(
            self.row(report)["sha256"], hashlib.sha256(self.original).hexdigest()
        )

    def test_hints_do_not_assign_copyright_ownership(self):
        report = AUDIT.audit_files(self.root, self.pin)
        row = self.row(report)
        self.assertEqual(row["git_log"]["earliest_commit"]["author"], "Josh Example")
        self.assertEqual(row["provenance_hint"], "fork_author_name_hint")
        self.assertEqual(row["attribution_status"], "unverified")
        self.assertEqual(row["rights_status"], "not_evaluated")
        self.assertIn("Original Organization", row["copyright_notices"][0])
        self.assertNotIn("provenance_class", row)
        self.assertEqual(
            report["validation_status"]["legal_clearance"], "not_performed"
        )

    def test_complete_spdx_expression_and_git_subject_are_retained(self):
        row = self.row(AUDIT.audit_files(self.root, self.pin))
        self.assertEqual(row["spdx_expression"], "(MIT OR Apache-2.0)")
        self.assertEqual(
            row["git_log"]["earliest_commit"]["subject"], "initial | fixture"
        )
        self.assertFalse(row["git_log"]["original_authorship_established"])
        self.assertFalse(row["git_log"]["renames_followed"])

    def test_empty_commit_subject_preserves_record_framing(self):
        self.write(self.path, b"# changed with an empty commit subject\\n")
        self.git("add", self.path)
        self.git(
            "-c",
            "user.name=Josh Example",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--allow-empty-message",
            "-m",
            "",
        )
        row = self.row(AUDIT.audit_files(self.root, "HEAD"))
        self.assertEqual(row["git_log"]["latest_commit"]["subject"], "")
        self.assertEqual(row["git_log"]["commit_count"], 2)

    def test_binary_blob_is_hashed_but_not_misreported_as_notice_scanned(self):
        payload = b"\xff\x00Copyright (c) fake binary token\n"
        name = "src/hwacc/not-text.bin"
        self.write(name, payload)
        self.git("add", ".")
        self.commit("record binary candidate")
        row = self.row(AUDIT.audit_files(self.root, "HEAD"), name)
        self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(row["notice_scan"], "not_scanned_non_utf8")
        self.assertEqual(row["copyright_notices"], [])

    def test_bracket_and_star_filenames_have_literal_git_history(self):
        # Construct entries directly so the wildcard-name case also works
        # on hosts that cannot create an asterisk in an OS filename.
        for literal, decoy in (
            ("src/hwacc/array[0].py", "src/hwacc/array0.py"),
            ("src/hwacc/vector*.py", "src/hwacc/vector-decoy.py"),
        ):
            blob = (
                self.git(
                    "hash-object", "-w", "--stdin", input=b"# initial candidate\\n"
                )
                .decode()
                .strip()
            )
            for name in (literal, decoy):
                self.git(
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    "100644," + blob + "," + name,
                )
            self.commit("introduce literal and decoy paths")
            literal_commit = self.git("rev-parse", "HEAD").decode().strip()
            changed = (
                self.git(
                    "hash-object", "-w", "--stdin", input=b"# only decoy changes\\n"
                )
                .decode()
                .strip()
            )
            self.git("update-index", "--cacheinfo", "100644," + changed + "," + decoy)
            self.commit("update decoy without changing literal filename")
            decoy_commit = self.git("rev-parse", "HEAD").decode().strip()
            report = AUDIT.audit_files(self.root, "HEAD")
            literal_history = self.row(report, literal)["git_log"]
            decoy_history = self.row(report, decoy)["git_log"]
            with self.subTest(literal=literal):
                self.assertEqual(
                    literal_history["latest_commit"]["hash"], literal_commit
                )
                self.assertEqual(literal_history["commit_count"], 1)
                self.assertEqual(decoy_history["latest_commit"]["hash"], decoy_commit)
                self.assertEqual(decoy_history["commit_count"], 2)

    def test_invalid_commit_fails_instead_of_using_worktree(self):
        with self.assertRaises(subprocess.CalledProcessError):
            AUDIT.audit_files(self.root, "no-such-commit")

    def test_rendered_report_distinguishes_hints_from_rights(self):
        report = AUDIT.audit_files(self.root, self.pin)
        text = AUDIT.render_markdown_report(report, "corrected.json")
        self.assertIn(self.pin, text)
        self.assertIn("unverified", text)
        self.assertIn("original source authorship", text)
        self.assertNotIn("New files authored in this fork", text)
        self.assertNotIn("Original UNC Charlotte SALAM research files", text)
        self.assertIn("[corrected.json](corrected.json)", text)


if __name__ == "__main__":
    unittest.main()
