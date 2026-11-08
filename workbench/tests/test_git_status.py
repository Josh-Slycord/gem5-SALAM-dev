# SPDX-License-Identifier: BSD-3-Clause
"""Passive-status regressions using real temporary Git histories and bindings."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench import git_status as status


class GitStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="salam-git-status-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.root = self.folder / "repo with spaces"
        self.project = self.root / "workbench"
        self.initialize(self.root)
        self.project.mkdir()
        self.write(
            ".gitignore",
            "build/\nworkbench/workspace.json\nworkbench/evidence/\n"
            "workbench/docs/git-roles.json\n",
        )
        self.write("tracked.txt", "base\n")
        self.git("add", ".")
        self.commit("initial fixture")
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def initialize(self, root):
        root.mkdir()
        self.git("init", "--quiet", ".", root=root)
        # Git 2.25 does not support git init -b.
        self.git("symbolic-ref", "HEAD", "refs/heads/main", root=root)
        self.git("config", "user.name", "Status Fixture", root=root)
        self.git("config", "user.email", "fixture@example.invalid", root=root)
        self.git("config", "commit.gpgsign", "false", root=root)
        self.git("config", "core.autocrlf", "false", root=root)

    def git(self, *args, root=None, check=True):
        result = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(root or self.root),
            ]
            + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )
        return result.stdout if check else result

    def commit(self, message, root=None):
        self.git("commit", "--quiet", "-m", message, root=root)

    def write(self, relative, text, root=None):
        path = (root or self.root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def inspect(self, **kwargs):
        return status.inspect_status(repo=self.root, project=self.project, **kwargs)

    def git_snapshot(self):
        git_dir = Path(self.git("rev-parse", "--absolute-git-dir").decode().strip())
        return {
            p.relative_to(git_dir).as_posix(): (
                hashlib.sha256(p.read_bytes()).hexdigest(),
                p.stat().st_mtime_ns,
            )
            for p in git_dir.rglob("*")
            if p.is_file()
        }

    def role_map(self, branches=None, tags=None):
        self.write(
            "workbench/docs/git-roles.json",
            json.dumps(
                {"schema_version": 1, "branches": branches or {}, "tags": tags or {}}
            ),
        )

    def runtime(self):
        engine = self.folder / "external engine"
        self.initialize(engine)
        self.write(".gitignore", "build/\n", root=engine)
        self.write("SConstruct", "# fixture\n", root=engine)
        self.git("add", ".", root=engine)
        self.commit("engine source", root=engine)
        binary = self.write("build/ARM/gem5.opt", "dummy binary bytes", root=engine)
        receipt = {
            "kind": "configured_engine_build",
            "state": "built",
            "engine": str(engine),
            "compiled_source_sha256": "a" * 64,
            "binary": {
                "path": str(binary),
                "sha256": "b" * 64,
                "bytes": binary.stat().st_size,
            },
        }
        receipt_path = self.write(
            "workbench/evidence/current-build/build.json", json.dumps(receipt)
        )
        manifest = {
            "configuration_engine": {
                "distribution": "Fixture-WSL",
                "path": str(engine),
                "build_receipt": "evidence/current-build/build.json",
                "toolchain_profile": {
                    "id": "fixture-profile",
                    "synthetic_secret": "DO_NOT_ECHO",
                },
            },
            "unrelated_secret": "ALSO_DO_NOT_ECHO",
        }
        self.write("workbench/workspace.json", json.dumps(manifest))
        return engine, binary, receipt_path, manifest

    def test_staged_unstaged_untracked_and_no_git_state_writes(self):
        self.write("tracked.txt", "staged\n")
        self.git("add", "tracked.txt")
        self.write("tracked.txt", "staged and unstaged\n")
        self.write("loose file.txt", "untracked\n")
        before = self.git_snapshot()
        report = self.inspect()
        self.assertEqual(report["state"], "observed")
        self.assertEqual(report["repository"]["worktree"]["staged"], 1)
        self.assertEqual(report["repository"]["worktree"]["unstaged"], 1)
        self.assertEqual(report["repository"]["worktree"]["untracked_entries"], 1)
        self.assertEqual(before, self.git_snapshot())
        self.assertEqual(report["runtime"]["state"], "unbound")

    def test_cached_branch_counts_and_topic_are_explicitly_offline(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.git("checkout", "--quiet", "-b", "topic")
        self.write("tracked.txt", "topic\n")
        self.git("add", ".")
        self.commit("topic change")
        self.git("update-ref", "refs/remotes/origin/topic", self.base)
        report = self.inspect()
        branch = report["selected_branches"]["topic"]
        self.assertEqual(
            (branch["comparison"]["ahead_by"], branch["comparison"]["behind_by"]),
            (1, 0),
        )
        self.assertEqual(branch["comparison_basis"], "cached_remote_tracking")
        self.assertEqual(report["remote"]["live_state"], "not_requested")
        self.assertIsNone(report["remote"]["live_heads"])

    def test_divergence_is_counted_against_selected_cached_remote(self):
        self.git("checkout", "--quiet", "-b", "remote-line")
        self.write("remote.txt", "remote\n")
        self.git("add", ".")
        self.commit("remote")
        remote_sha = self.git("rev-parse", "HEAD").decode().strip()
        self.git("checkout", "--quiet", "main")
        self.write("local.txt", "local\n")
        self.git("add", ".")
        self.commit("local")
        self.git("update-ref", "refs/remotes/origin/main", remote_sha)
        comparison = self.inspect()["selected_branches"]["main"]["comparison"]
        self.assertEqual(comparison["state"], "diverged")
        self.assertEqual((comparison["ahead_by"], comparison["behind_by"]), (1, 1))

    def test_detached_and_unborn_checkouts_are_not_fabricated_branches(self):
        self.git("checkout", "--quiet", "--detach", self.base)
        report = self.inspect()
        self.assertTrue(report["repository"]["detached"])
        self.assertIsNone(report["topic"])
        unborn = self.folder / "unborn"
        self.initialize(unborn)
        report = status.inspect_status(repo=unborn)
        self.assertIsNone(report["repository"]["head"])
        self.assertFalse(report["repository"]["detached"])
        self.assertEqual(report["repository"]["branch"], "main")

    def test_linked_worktree_scan_is_opt_in_and_counts_real_changes(self):
        other = self.folder / "linked worktree"
        self.git("worktree", "add", "--quiet", "-b", "other", str(other))
        self.write("tracked.txt", "dirty linked\n", root=other)
        report = self.inspect()
        entry = next(w for w in report["worktrees"] if Path(w["path"]) == other)
        self.assertFalse(entry["status"]["checked"])
        report = self.inspect(all_worktrees=True)
        entry = next(w for w in report["worktrees"] if Path(w["path"]) == other)
        self.assertEqual(entry["status"]["unstaged"], 1)

    def test_real_rename_counts_once_and_nul_names_do_not_add_entries(self):
        self.git("mv", "tracked.txt", "renamed \u03b1 file.txt")
        dirty = self.inspect()["repository"]["worktree"]
        self.assertEqual(dirty["dirty_entries"], 1)
        self.assertEqual(dirty["staged"], 1)
        fake = unittest.mock.Mock()
        fake.partial_clone.return_value = False
        fake.run.return_value.stdout = (
            b"R  destination\nwith newline\0old\nname\0?? loose\nname\0"
        )
        dirty = status._dirty(fake)
        self.assertEqual(dirty["dirty_entries"], 2)
        self.assertEqual(dirty["untracked_entries"], 1)

    def test_actual_merge_conflict_is_reported(self):
        self.git("checkout", "--quiet", "-b", "topic")
        self.write("tracked.txt", "topic\n")
        self.git("add", ".")
        self.commit("topic")
        self.git("checkout", "--quiet", "main")
        self.write("tracked.txt", "main\n")
        self.git("add", ".")
        self.commit("main")
        merged = self.git("merge", "--no-commit", "topic", check=False)
        self.assertNotEqual(merged.returncode, 0)
        self.assertEqual(self.inspect()["repository"]["worktree"]["conflicts"], 1)

    def test_role_pins_and_annotated_tag_object_identity_remain_separate(self):
        self.git("branch", "legacy/saved", self.base)
        self.git("tag", "-a", "checkpoint", "-m", "fixture checkpoint")
        object_sha = self.git("rev-parse", "refs/tags/checkpoint").decode().strip()
        self.assertNotEqual(object_sha, self.base)
        self.role_map(
            {
                "main": {"role": "active"},
                "legacy/saved": {"role": "legacy", "expected_sha": "c" * 40},
            },
            {"checkpoint": {"role": "checkpoint", "expected_object_sha": object_sha}},
        )
        report = self.inspect()
        legacy = next(
            b for b in report["local_branches"] if b["name"] == "legacy/saved"
        )
        tag = next(t for t in report["tags"] if t["name"] == "checkpoint")
        self.assertFalse(legacy["role"]["expected_sha_matches"])
        self.assertTrue(tag["role"]["expected_object_sha_matches"])
        self.assertEqual(tag["object_sha"], object_sha)
        self.assertEqual(tag["sha"], self.base)
        self.assertIn("expected identity differs", status.format_human(report))

    def test_missing_role_map_is_graceful_but_malformed_present_map_is_partial(self):
        self.assertEqual(self.inspect()["role_mapping"]["state"], "absent")
        self.write(
            "workbench/docs/git-roles.json", '{"schema_version":1,"branches":[]}'
        )
        report = self.inspect()
        self.assertEqual(report["state"], "partial")
        self.assertEqual(report["role_mapping"]["state"], "unavailable")

    def test_runtime_head_build_identity_and_profile_metadata_are_separate(self):
        engine, binary, _, _ = self.runtime()
        old_head = self.git("rev-parse", "HEAD", root=engine).decode().strip()
        self.write("README.md", "documentation only\n", root=engine)
        self.git("add", ".", root=engine)
        self.commit("docs only", root=engine)
        new_head = self.git("rev-parse", "HEAD", root=engine).decode().strip()
        original_read = Path.read_bytes

        def guarded(path):
            self.assertNotEqual(path, binary, "Status must not hash/execute binary")
            return original_read(path)

        with patch.object(Path, "read_bytes", guarded):
            report = self.inspect()
        runtime = report["runtime"]
        self.assertNotEqual(old_head, new_head)
        self.assertEqual(runtime["source_git"]["head"], new_head)
        self.assertEqual(runtime["binary"]["recorded_sha256"], "b" * 64)
        self.assertEqual(
            runtime["build_receipt"]["recorded_compiled_source_sha256"], "a" * 64
        )
        self.assertFalse(runtime["binary_integrity_verified"])
        self.assertFalse(runtime["compiled_sources_verified"])
        self.assertFalse(runtime["head_is_binary_identity"])
        self.assertEqual(runtime["toolchain_profile"], "fixture-profile")
        self.assertNotIn("DO_NOT_ECHO", json.dumps(report))
        self.assertNotIn("ALSO_DO_NOT_ECHO", json.dumps(report))
        self.assertIn("NOT verified", status.format_human(report))

    def test_project_override_keeps_source_checkout_and_its_role_authority(self):
        _, _, receipt_path, manifest = self.runtime()
        binding = self.folder / "other workspace"
        binding.mkdir()
        (binding / "workspace.json").write_text(json.dumps(manifest))
        target = binding / "evidence/current-build/build.json"
        target.parent.mkdir(parents=True)
        target.write_text(receipt_path.read_text())
        self.role_map({"main": {"role": "active"}})
        with patch.object(status, "PROJECT", self.project):
            report = status.inspect_status(project=binding)
        self.assertEqual(Path(report["repository"]["path"]), self.root)
        self.assertEqual(report["selected_branches"]["main"]["role"]["role"], "active")
        self.assertEqual(
            Path(report["runtime"]["workspace"]), binding / "workspace.json"
        )
        self.assertEqual(report["runtime"]["state"], "metadata_only")

    def test_missing_binary_and_size_mismatch_are_explicit_metadata(self):
        _, binary, receipt_path, _ = self.runtime()
        receipt = json.loads(receipt_path.read_text())
        receipt["binary"]["bytes"] += 1
        receipt_path.write_text(json.dumps(receipt))
        report = self.inspect()
        self.assertFalse(report["runtime"]["binary"]["size_matches"])
        # Rename only a self-created temporary fixture to simulate missing data.
        binary.rename(binary.with_name("gem5.opt.saved"))
        report = self.inspect()
        self.assertFalse(report["runtime"]["binary"]["exists"])
        self.assertIn("Binary present: False", status.format_human(report))

    def test_receipt_escape_is_rejected_before_outside_contents_are_read(self):
        _, _, _, manifest = self.runtime()
        outside = self.folder / "outside.json"
        outside.write_text('{"synthetic_secret":"NOT_READ"}')
        manifest["configuration_engine"]["build_receipt"] = str(outside)
        self.write("workbench/workspace.json", json.dumps(manifest))
        original = Path.read_text

        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path, outside)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", guarded):
            report = self.inspect()
        self.assertEqual(report["runtime"]["state"], "unavailable")
        self.assertNotIn("NOT_READ", json.dumps(report))

    def test_symlinked_json_is_rejected_without_reading_target(self):
        self.write("workbench/workspace.json", '{"configuration_engine":{}}')
        with patch.object(Path, "is_symlink", return_value=True), patch.object(
            Path, "read_text", side_effect=AssertionError("Must not read symlink")
        ):
            with self.assertRaises(status.StatusError):
                status._json_file(self.project / "workspace.json", self.project)

    def test_incomplete_workspace_is_not_reported_as_ready(self):
        self.write(
            "workbench/workspace.json",
            '{"configuration_engine":{"toolchain_profile":"x"}}',
        )
        report = self.inspect()
        self.assertEqual(report["state"], "partial")
        self.assertEqual(report["runtime"]["state"], "unavailable")

    def test_unsafe_recorded_binary_path_is_rejected(self):
        _, _, receipt_path, _ = self.runtime()
        receipt = json.loads(receipt_path.read_text())
        receipt["binary"]["path"] = str(self.folder / "outside-private-file")
        receipt_path.write_text(json.dumps(receipt))
        report = self.inspect()
        self.assertEqual(report["runtime"]["state"], "unavailable")

    def test_offline_never_queries_remote_urls_or_executes_a_simulator(self):
        self.git(
            "remote",
            "add",
            "origin",
            "https://fixture:FAKE_SECRET@example.invalid/repo.git",
        )
        self.runtime()
        calls = []
        original = subprocess.run

        def record(command, **kwargs):
            calls.append(command)
            return original(command, **kwargs)

        with patch.object(status.subprocess, "run", side_effect=record):
            report = self.inspect()
        self.assertTrue(calls)
        for command in calls:
            self.assertEqual(command[0], "git")
            self.assertNotIn("ls-remote", command)
            self.assertNotIn("fetch", command)
            self.assertNotIn("get-url", command)
            self.assertNotIn("--list", command)
        self.assertNotIn("FAKE_SECRET", json.dumps(report))

    def test_live_unknown_object_does_not_fetch_or_invent_counts(self):
        self.git("remote", "add", "origin", "https://example.invalid/repo.git")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        calls = []
        original = subprocess.run

        def route(command, **kwargs):
            calls.append(command)
            if "ls-remote" in command:
                return subprocess.CompletedProcess(
                    command, 0, ("f" * 40 + "\trefs/heads/main\n").encode(), b""
                )
            return original(command, **kwargs)

        before = self.git_snapshot()
        with patch.object(status.subprocess, "run", side_effect=route):
            report = self.inspect(live_remote=True)
        comparison = report["selected_branches"]["main"]["comparison"]
        self.assertEqual(comparison["state"], "unknown")
        self.assertIsNone(comparison["ahead_by"])
        self.assertEqual(
            report["selected_branches"]["main"]["comparison_basis"], "live"
        )
        self.assertFalse(report["remote"]["cached_matches_live"])
        self.assertEqual(before, self.git_snapshot())
        self.assertFalse(any("fetch" in command for command in calls))

    def test_live_failure_never_echoes_credential_bearing_stderr(self):
        self.git("remote", "add", "origin", "https://example.invalid/repo.git")
        original = subprocess.run

        def route(command, **kwargs):
            if "ls-remote" in command:
                return subprocess.CompletedProcess(
                    command,
                    128,
                    b"",
                    b"fatal https://user:FAKE_TOKEN@example.invalid/private\n",
                )
            return original(command, **kwargs)

        with patch.object(status.subprocess, "run", side_effect=route):
            report = self.inspect(live_remote=True)
        self.assertEqual(report["remote"]["live_state"], "unavailable")
        self.assertEqual(report["state"], "partial")
        self.assertNotIn("FAKE_TOKEN", json.dumps(report))
        self.assertNotIn("example.invalid", status.format_human(report))

    def test_partial_clone_never_traverses_objects_or_inspects_content(self):
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "extensions.partialClone", "origin")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.write("tracked.txt", "changed\n")
        self.git("add", ".")
        self.commit("local extra")
        calls = []
        original = subprocess.run

        def record(command, **kwargs):
            calls.append(command)
            return original(command, **kwargs)

        before = self.git_snapshot()
        with patch.object(status.subprocess, "run", side_effect=record):
            report = self.inspect()
        self.assertTrue(report["repository"]["partial_clone"])
        self.assertFalse(report["repository"]["worktree"]["checked"])
        self.assertEqual(
            report["selected_branches"]["main"]["comparison"]["state"], "unknown"
        )
        self.assertFalse(
            any(
                value in command
                for command in calls
                for value in ("cat-file", "rev-list", "status", "fetch")
            )
        )
        self.assertEqual(before, self.git_snapshot())

    def test_shallow_unequal_counts_are_unknown_but_same_oid_is_identical(self):

        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.write("tracked.txt", "local extra\n")
        self.git("add", ".")
        self.commit("extra")
        head = self.git("rev-parse", "HEAD").decode().strip()
        shallow_path = Path(
            self.git("rev-parse", "--git-path", "shallow").decode().strip()
        )
        if not shallow_path.is_absolute():
            shallow_path = self.root / shallow_path
        shallow_path.write_text(head + "\n")
        report = self.inspect()
        self.assertTrue(report["repository"]["shallow"])
        self.assertEqual(
            report["selected_branches"]["main"]["comparison"]["state"], "unknown"
        )
        self.git("update-ref", "refs/remotes/origin/main", head)
        comparison = self.inspect()["selected_branches"]["main"]["comparison"]
        self.assertEqual((comparison["ahead_by"], comparison["behind_by"]), (0, 0))

    def test_replace_refs_cannot_hide_topic_history(self):
        self.git("checkout", "--quiet", "-b", "topic")
        self.write("tracked.txt", "topic extra\n")
        self.git("add", ".")
        self.commit("extra")
        topic_sha = self.git("rev-parse", "HEAD").decode().strip()
        self.git("update-ref", "refs/remotes/origin/topic", self.base)
        self.git("replace", topic_sha, self.base)
        comparison = self.inspect()["selected_branches"]["topic"]["comparison"]
        self.assertEqual((comparison["ahead_by"], comparison["behind_by"]), (1, 0))

    def test_git_queries_disable_helpers_lazy_fetch_and_ambient_redirection(self):
        decoy = self.folder / "decoy"
        self.initialize(decoy)
        calls = []
        original = subprocess.run

        def record(command, **kwargs):
            calls.append((command, kwargs["env"]))
            return original(command, **kwargs)

        with patch.dict(
            os.environ, {"GIT_DIR": str(decoy / ".git"), "GIT_WORK_TREE": str(decoy)}
        ), patch.object(status.subprocess, "run", side_effect=record):
            report = self.inspect()
        self.assertEqual(report["repository"]["head"], self.base)
        for command, environment in calls:
            self.assertIn("--no-optional-locks", command)
            self.assertIn("--no-replace-objects", command)
            self.assertIn("core.fsmonitor=false", command)
            self.assertIn("core.hooksPath=" + os.devnull, command)
            self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
            self.assertNotIn("GIT_DIR", environment)
            self.assertNotIn("GIT_WORK_TREE", environment)

    def test_bare_repo_and_timeout_have_explicit_non_ready_states(self):
        bare = self.folder / "bare.git"
        self.git("clone", "--bare", "--quiet", str(self.root), str(bare))
        report = status.inspect_status(repo=bare)
        self.assertTrue(report["repository"]["bare"])
        self.assertFalse(report["repository"]["worktree"]["checked"])
        with patch.object(
            status.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["git", "SYNTHETIC_SECRET"], 1),
        ):
            with self.assertRaisesRegex(status.StatusError, "timed out"):
                status.Git(self.root).run("rev-parse", "HEAD")

    def test_cli_json_and_human_and_invalid_remote_do_not_leak(self):
        for mode in ("json", "human"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = status.main(
                    [
                        "--repo",
                        str(self.root),
                        "--project",
                        str(self.project),
                        "--format",
                        mode,
                    ]
                )
            self.assertEqual(code, 0)
            if mode == "json":
                self.assertEqual(
                    json.loads(output.getvalue())["repository"]["head"], self.base
                )
            else:
                self.assertIn("cached refs may be stale", output.getvalue())
        with patch.object(status.Git, "run", side_effect=AssertionError("No Git")):
            with self.assertRaises(status.StatusError):
                self.inspect(remote="https://user:FAKE_TOKEN@example.invalid")


if __name__ == "__main__":
    unittest.main()
