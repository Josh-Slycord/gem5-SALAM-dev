"""Release fixtures are temporary; no real engine bundle/package is created."""
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from salam_workbench import release

COMMIT = "a" * 40
SELECTION = {
    "schema_version": 1,
    "session_directories": [],
    "run_directories": [],
    "run_expectations": {},
    "evidence_files": [],
    "workloads": [
        {
            "id": "fixture",
            "status": "deferred",
            "evidence": [],
            "limitations": ["fixture has no executed workload"],
        }
    ],
}


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="salam-release-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.engine = self.root / "engine"
        self.project.mkdir()
        self.engine.mkdir()
        for tree in release.CURATED_TREES:
            (self.project / tree).mkdir()
            (self.project / tree / "fixture.txt").write_text(
                "source " + tree, encoding="utf-8"
            )
        (self.project / "evidence").mkdir()
        for name, data in (
            ("toolchain.json", {"profile": "fixture"}),
            ("receipt.json", {"state": "completed"}),
            (
                "build.json",
                {"state": "completed", "return_code": 0, "log": "build.log"},
            ),
        ):
            (self.project / "evidence" / name).write_text(
                json.dumps(data), encoding="utf-8"
            )
        (self.project / "evidence/build.log").write_text(
            "fixture build success", encoding="utf-8"
        )
        (self.project / "README.md").write_text("fixture", encoding="utf-8")
        self.model = self.engine / release.MODEL
        self.model.parent.mkdir(parents=True)
        self.model.write_text(
            "model fixture bytes; not a characterization", encoding="utf-8"
        )
        self.selection = copy.deepcopy(SELECTION)
        self.git_state = {
            "commit": COMMIT,
            "tree": "b" * 40,
            "status_porcelain": "",
        }
        self.receipt_paths = [
            "evidence/receipt.json",
            "evidence/build.json",
            "evidence/build.log",
        ]
        self.receipt = {
            "path": "evidence/receipt.json",
            "record": {"state": "completed"},
            "engine_source_sha256": "c" * 64,
        }
        patches = [
            mock.patch.object(
                release,
                "_git_info",
                side_effect=lambda root: dict(self.git_state),
            ),
            mock.patch.object(
                release,
                "_receipt_sources",
                side_effect=lambda *args: (self.receipt, self.receipt_paths),
            ),
            mock.patch.object(
                release,
                "_model_info",
                side_effect=lambda *args: {
                    "path": "engine-assets/" + release.MODEL,
                    "sha256": release._sha(self.model),
                    "characterization_verified": False,
                    "source_confidence": "repository_claim_unverified",
                    "declared_model": {
                        "technology_node": "40nm",
                        "units": {"power": "mW"},
                    },
                },
            ),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def inspect(self, **kwargs):
        return release.inspect_release(
            self.project, self.engine, self.selection, **kwargs
        )

    def build(self, **kwargs):
        return release.build_release(
            self.project,
            self.engine,
            self.selection,
            release_id="fixture-release",
            **kwargs,
        )

    def manifest(self, directory):
        return json.loads((Path(directory) / "release.json").read_text())

    def save_manifest(self, directory, manifest):
        (Path(directory) / "release.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_inspect_does_not_create_release_and_excludes_build_and_old_releases(
        self,
    ):
        for relative in (
            "releases/old/secret.txt",
            "salam_workbench/__pycache__/cache.pyc",
            "tests/build/gem5.opt",
        ):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not selected", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["kind"], "local_release_plan")
        self.assertEqual(result["rerun"], "not_performed_by_packager")
        self.assertFalse(
            any(
                "secret.txt" in f["path"]
                or "gem5.opt" in f["path"]
                or "cache.pyc" in f["path"]
                for f in result["files"]
            )
        )
        self.assertFalse((self.project / "releases/fixture-release").exists())
        self.assertFalse(result["model"]["characterization_verified"])

    def test_unique_package_verifies_and_has_no_rerun_claim(self):
        result = self.build()
        check = result["validation"]
        self.assertTrue(check["integrity_and_saved_evidence_passed"], check["issues"])
        self.assertEqual(check["rerun"], "not_performed")
        manifest = self.manifest(result["directory"])
        self.assertEqual(manifest["source_restore"], "external_engine_source_required")
        self.assertTrue(manifest["tooling"]["worktree_snapshot"])
        for entry in manifest["files"]:
            self.assertEqual(
                release._sha(Path(result["directory"]) / entry["path"]),
                entry["sha256"],
            )

    def test_existing_target_is_never_overwritten(self):
        target = self.project / "releases/fixture-release"
        target.mkdir(parents=True)
        marker = target / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(release.ReleaseError, "already exists"):
            self.build()
        self.assertEqual(marker.read_text(), "keep")

    def test_tampered_file_and_undeclared_file_are_detected(self):
        result = self.build()
        target = Path(result["directory"])
        (target / "project/README.md").write_text("changed", encoding="utf-8")
        (target / "extra.txt").write_text("extra", encoding="utf-8")
        check = release.verify_release(target)
        self.assertFalse(check["integrity_and_saved_evidence_passed"])
        self.assertTrue(any("hash mismatch" in x for x in check["issues"]))
        self.assertTrue(any("undeclared" in x for x in check["issues"]))

    def test_traversal_and_duplicate_manifest_paths_are_rejected(self):
        result = self.build()
        target = Path(result["directory"])
        original = self.manifest(target)
        for entry in (
            dict(original["files"][0], path="../escape"),
            dict(original["files"][0]),
        ):
            manifest = copy.deepcopy(original)
            manifest["files"].append(entry)
            self.save_manifest(target, manifest)
            check = release.verify_release(target)
            self.assertFalse(check["integrity_and_saved_evidence_passed"])

    def test_selection_rejects_traversal_duplicates_and_missing_expectations(
        self,
    ):
        for selection in (
            dict(SELECTION, session_directories=["../engine"]),
            dict(
                SELECTION,
                evidence_files=["evidence/build.log", "evidence/build.log"],
            ),
            dict(SELECTION, run_directories=["runs/a"]),
            dict(SELECTION, session_directories=["evidence/../releases"]),
        ):
            with self.subTest(selection=selection), self.assertRaises(
                release.ReleaseError
            ):
                release._selection(selection)

    def test_symlink_escape_is_not_followed(self):
        external = self.root / "external.txt"
        external.write_text("outside", encoding="utf-8")
        link = self.project / "docs/link.txt"
        try:
            link.symlink_to(external)
        except OSError as error:
            self.skipTest("symlinks unavailable: " + str(error))
        with self.assertRaisesRegex(release.ReleaseError, "symlink"):
            self.inspect()

    def test_overlapping_evidence_selections_fail(self):
        self.selection["session_directories"] = ["evidence/session"]
        path = self.project / "evidence/session/result.json"
        path.parent.mkdir()
        path.write_text("{}", encoding="utf-8")
        self.selection["evidence_files"] = ["evidence/session/result.json"]
        with self.assertRaisesRegex(release.ReleaseError, "overlapping"):
            self.inspect()

    def test_missing_supported_evidence_fails(self):
        self.selection["workloads"] = [
            {
                "id": "gemm",
                "status": "supported",
                "evidence": ["evidence/absent.json"],
                "limitations": [],
            }
        ]
        with self.assertRaisesRegex(release.ReleaseError, "not an included file"):
            self.inspect()

    def test_output_inside_engine_or_curated_tree_is_rejected(self):
        for output in (
            self.engine,
            self.project / "docs",
            self.project / "runs",
        ):
            with self.subTest(output=str(output)), self.assertRaisesRegex(
                release.ReleaseError, "must not be inside"
            ):
                self.build(output_root=output)

    def test_changed_source_retains_failed_partial_release(self):
        original = shutil.copyfileobj
        changed = False

        def mutate(source, destination, length):
            nonlocal changed
            original(source, destination, length)
            if not changed:
                self.model.write_text("changed during copy", encoding="utf-8")
                changed = True

        with mock.patch.object(release.shutil, "copyfileobj", side_effect=mutate):
            with self.assertRaisesRegex(
                release.ReleaseError, "partial release retained"
            ):
                self.build()
        target = self.project / "releases/fixture-release"
        self.assertTrue(target.exists())
        self.assertEqual(self.manifest(target)["status"], "failed")
        with self.assertRaisesRegex(release.ReleaseError, "incomplete"):
            release.verify_release(target)

    def test_full_bundle_header_and_expected_head_are_pinned(self):
        bundle = self.root / "engine.bundle"
        bundle.write_bytes(
            (
                "# v2 git bundle\n" + COMMIT + " refs/heads/accepted\n\nPACK-fixture"
            ).encode()
        )
        with mock.patch.object(
            release, "_git", return_value="fixture verification"
        ) as git:
            result = self.build(engine_bundle=bundle)
        self.assertTrue(result["validation"]["integrity_and_saved_evidence_passed"])
        manifest = self.manifest(result["directory"])
        self.assertEqual(manifest["bundle"]["git_bundle_verify"], "passed")
        self.assertEqual(
            manifest["bundle"]["fresh_restore"], "not_performed_by_packager"
        )
        self.assertTrue(any("bundle" in call.args for call in git.call_args_list))

    def test_incremental_bundle_and_dirty_engine_are_rejected(self):
        bundle = self.root / "engine.bundle"
        bundle.write_bytes(
            (
                "# v2 git bundle\n-"
                + "b" * 40
                + " prerequisite\n"
                + COMMIT
                + " HEAD\n\nPACK"
            ).encode()
        )
        with self.assertRaisesRegex(release.ReleaseError, "prerequisites"):
            self.inspect(engine_bundle=bundle)
        self.git_state["status_porcelain"] = " M src/file.cc"
        with self.assertRaisesRegex(release.ReleaseError, "omit working bytes"):
            self.inspect(engine_bundle=bundle)

    def test_positive_evidence_is_rechecked_not_accepted_from_workload_label(
        self,
    ):
        path = self.project / "runs/a"
        path.mkdir(parents=True)
        (path / "run.json").write_text("{}", encoding="utf-8")
        self.selection["run_directories"] = ["runs/a"]
        self.selection["run_expectations"] = {"runs/a": "passed"}
        with mock.patch(
            "salam_workbench.report.load_run",
            return_value={
                "correctness_verified": False,
                "issues": ["raw checker missing"],
            },
        ):
            result = self.build()
        self.assertFalse(result["validation"]["integrity_and_saved_evidence_passed"])
        self.assertFalse(result["validation"]["run_checks"][0]["passed"])

    def test_negative_witness_cannot_hide_provenance_failure(self):
        path = self.project / "runs/negative"
        path.mkdir(parents=True)
        (path / "run.json").write_text("{}", encoding="utf-8")
        self.selection["run_directories"] = ["runs/negative"]
        self.selection["run_expectations"] = {"runs/negative": "intentional_failure"}
        loaded = {
            "correctness_verified": False,
            "recorded_state": "failed",
            "record": {"return_code": 0},
            "experiment": {"negative_witness": {"expected_runner_state": "failed"}},
            "issues": [
                "Run state is not passed: failed",
                "Artifact verification failed: inputs/source.c",
            ],
        }
        with mock.patch(
            "salam_workbench.report.load_run", return_value=loaded
        ), mock.patch(
            "salam_workbench.runner._read_correctness",
            return_value={"outcome": "failed"},
        ):
            result = self.build()
        self.assertFalse(result["validation"]["run_checks"][0]["passed"])

    def setup_comparison(self):
        for name in ("a", "b"):
            path = self.project / "runs" / name
            path.mkdir(parents=True)
            (path / "run.json").write_text("{}", encoding="utf-8")
        saved = {
            "kind": "gem5_repeat_comparison",
            "outcome": "matched",
            "repeatability_accepted": True,
            "runs": [{"run_id": "a"}, {"run_id": "b"}],
            "metrics": [],
        }
        record = self.project / "evidence/comparison.json"
        record.write_text(json.dumps(saved), encoding="utf-8")
        self.selection["run_directories"] = ["runs/a", "runs/b"]
        self.selection["run_expectations"] = {
            "runs/a": "passed",
            "runs/b": "passed",
        }
        self.selection["evidence_files"] = ["evidence/comparison.json"]
        self.selection["comparisons"] = [
            {
                "kind": "gem5_repeat_comparison",
                "runs": ["runs/a", "runs/b"],
                "record": "evidence/comparison.json",
            }
        ]
        return record, saved

    def test_comparison_recomputed_from_packaged_run_paths(self):
        record, fresh = self.setup_comparison()
        with mock.patch(
            "salam_workbench.report.load_run",
            return_value={"correctness_verified": True, "issues": []},
        ), mock.patch(
            "salam_workbench.report.compare_runs", return_value=fresh
        ) as compare:
            result = self.build()
        self.assertTrue(
            result["validation"]["integrity_and_saved_evidence_passed"],
            result["validation"]["issues"],
        )
        self.assertTrue(result["validation"]["comparison_checks"][0]["accepted"])
        compare.assert_called_once_with(
            Path(result["directory"]) / "project/runs/a",
            Path(result["directory"]) / "project/runs/b",
        )

    def test_stored_comparison_claim_is_not_trusted(self):
        record, fresh = self.setup_comparison()
        forged = dict(fresh, outcome="different")
        record.write_text(json.dumps(forged), encoding="utf-8")
        with mock.patch(
            "salam_workbench.report.load_run",
            return_value={"correctness_verified": True, "issues": []},
        ), mock.patch("salam_workbench.report.compare_runs", return_value=fresh):
            result = self.build()
        self.assertFalse(result["validation"]["integrity_and_saved_evidence_passed"])
        self.assertFalse(result["validation"]["comparison_checks"][0]["accepted"])

    def test_output_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        output = self.project / "releases"
        try:
            output.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest("symlinks unavailable: " + str(error))
        with self.assertRaisesRegex(release.ReleaseError, "must not traverse symlinks"):
            self.build()
        self.assertEqual(list(outside.iterdir()), [])

    def test_characterization_claim_cannot_be_promoted_by_manifest(self):
        result = self.build()
        target = Path(result["directory"])
        manifest = self.manifest(target)
        manifest["model"]["characterization_verified"] = True
        self.save_manifest(target, manifest)
        check = release.verify_release(target)
        self.assertFalse(check["integrity_and_saved_evidence_passed"])
        self.assertTrue(
            any("characterization boundary" in issue for issue in check["issues"])
        )

    def test_empty_or_incomplete_manifest_fails_closed(self):
        result = self.build()
        target = Path(result["directory"])
        manifest = self.manifest(target)
        manifest["files"] = None
        self.save_manifest(target, manifest)
        with self.assertRaises(release.ReleaseError):
            release.verify_release(target)


class ReleaseGitTests(unittest.TestCase):
    def test_git_commands_are_read_only_and_shell_free(self):
        with mock.patch.object(
            release.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, COMMIT, ""),
        ) as run:
            release._git(Path("/fixture"), "rev-parse", "HEAD")
        args, kwargs = run.call_args
        self.assertIn("--no-optional-locks", args[0])
        self.assertIn("core.fsmonitor=false", args[0])
        self.assertFalse(kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
