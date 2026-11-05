"""Portable publication paths and existing-engine binding contracts."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from salam_workbench import bootstrap_existing, gui_hook
from salam_workbench.hardware_variants import _SKIP_COPY
from salam_workbench.runner import file_hash


class PortabilityTests(unittest.TestCase):
    def test_gui_hook_replaces_legacy_tail_and_is_idempotent(self):
        legacy = (
            "from pathlib import Path\nclass ConfigGeneratorDialog:\n"
            "    pass\n\n" + gui_hook.OLD_MARKER + "\n"
            'if Path(__file__).resolve().parents[3].name == "configurator-engine":\n'
            "    pass\n"
        )
        result = gui_hook.render_hook(legacy)
        self.assertIn("SALAM_WORKBENCH_ROOT", result)
        self.assertNotIn("configurator-engine", result)
        self.assertEqual(gui_hook.render_hook(result), result)
        self.assertIn("workbench", _SKIP_COPY)

    def test_gui_hook_install_preserves_before_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = root / "engine"
            engine.mkdir()
            (engine / "SConstruct").write_text("", encoding="utf-8")
            gui = engine / gui_hook.GUI_RELATIVE
            gui.parent.mkdir(parents=True)
            original = "class ConfigGeneratorDialog:\n    pass\n"
            gui.write_text(original, encoding="utf-8")
            result = gui_hook.install_hook(engine, root / "evidence")
            self.assertEqual(result["state"], "installed")
            self.assertEqual(
                (root / "evidence/config_generator.py.before").read_text(),
                original,
            )
            self.assertIn(gui_hook.NEW_MARKER, gui.read_text())
            self.assertEqual(file_hash(gui), result["after_sha256"])

    def test_bootstrap_copies_exact_receipts_and_never_reuses_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, project, engine = (
                root / name for name in ("old", "new", "external")
            )
            for path in (source / "evidence", project, engine):
                path.mkdir(parents=True)
            toolchain = source / "evidence/toolchain.json"
            toolchain.write_text('{"schema_version":1}\n', encoding="utf-8")
            build_relative = "evidence/build/build.json"
            generation_relative = "evidence/generation/hardware-codegen.json"
            build = source / build_relative
            generation = source / generation_relative
            build.parent.mkdir(parents=True)
            generation.parent.mkdir(parents=True)
            sidecar = build.parent / "source-inputs.json"
            source_files = {"SConstruct": "a" * 64}
            source_digest = hashlib.sha256(
                json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            sidecar.write_text(
                json.dumps({"sha256": source_digest, "files": source_files}),
                encoding="utf-8",
            )
            build.write_text(
                json.dumps(
                    {
                        "kind": "configured_engine_build",
                        "state": "built",
                        "engine": str(engine),
                        "compiled_source_sha256": source_digest,
                        "source_inputs_sha256": file_hash(sidecar),
                        "toolchain_record": {"sha256": file_hash(toolchain)},
                        "toolchain": [
                            {
                                "path": sys.executable,
                                "sha256": file_hash(sys.executable),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            generation.write_text(
                '{"state":"generated","valid":true}', encoding="utf-8"
            )
            self.assertEqual(
                bootstrap_existing.verify_build_inputs_receipt(build),
                sidecar.resolve(strict=True),
            )
            workspace = source / "workspace.json"
            workspace.write_text(
                json.dumps(
                    {
                        "engine": {
                            "distribution": "Ubuntu-20.04",
                            "path": str(root / "fixed"),
                        },
                        "configuration_engine": {
                            "distribution": "Ubuntu-20.04",
                            "path": str(engine),
                            "build_receipt": build_relative,
                            "generation_receipt": generation_relative,
                            "toolchain_profile": {
                                "id": "gem5-26-retained-salam",
                                "python": "/opt/salam/bin/python",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                bootstrap_existing, "verify_engine"
            ) as verify_build, patch.object(
                bootstrap_existing, "_verify_generated_outputs"
            ), patch.object(
                bootstrap_existing,
                "inspect_fu_capability",
                return_value={
                    "supported": True,
                    "build_verified": True,
                    "feature": "salam_fu_scheduler_v1",
                    "reason": None,
                },
            ):
                result = bootstrap_existing.bootstrap_existing(workspace, project)
            self.assertEqual(result["state"], "bound_existing")
            from salam_workbench.toolchain_profile import load_toolchain

            verify_build.assert_called_once_with(
                engine,
                build,
                toolchain_profile=load_toolchain(
                    manifest=json.loads(workspace.read_text())
                ),
            )
            self.assertEqual(
                (project / build_relative).read_bytes(), build.read_bytes()
            )
            self.assertEqual(
                (project / generation_relative).read_bytes(),
                generation.read_bytes(),
            )
            self.assertEqual(
                (project / "evidence/build/source-inputs.json").read_bytes(),
                sidecar.read_bytes(),
            )
            self.assertEqual(
                (project / "evidence/toolchain.json").read_bytes(),
                toolchain.read_bytes(),
            )
            selected = json.loads((project / "workspace.json").read_text())
            self.assertEqual(selected["configuration_engine"]["path"], str(engine))
            self.assertEqual(
                selected["configuration_engine"]["toolchain_profile"],
                {"id": "gem5-26-retained-salam", "python": "/opt/salam/bin/python"},
            )
            with self.assertRaisesRegex(ValueError, "new workbench binding"):
                bootstrap_existing.bootstrap_existing(workspace, project)

            saved = sidecar.with_name("source-inputs.saved.json")
            sidecar.rename(saved)
            missing_target = root / "missing-target"
            missing_target.mkdir()
            with self.assertRaisesRegex(
                ValueError, "missing or symlinked"
            ), patch.object(bootstrap_existing, "verify_engine"), patch.object(
                bootstrap_existing, "_verify_generated_outputs"
            ), patch.object(
                bootstrap_existing, "inspect_fu_capability"
            ):
                bootstrap_existing.bootstrap_existing(workspace, missing_target)
            self.assertFalse((missing_target / "workspace.json").exists())
            saved.rename(sidecar)
            sidecar.write_text('{"sha256":"corrupt","files":{}}', encoding="utf-8")
            corrupt_target = root / "corrupt-target"
            corrupt_target.mkdir()
            with self.assertRaisesRegex(ValueError, "sidecar differs"), patch.object(
                bootstrap_existing, "verify_engine"
            ), patch.object(
                bootstrap_existing, "_verify_generated_outputs"
            ), patch.object(
                bootstrap_existing, "inspect_fu_capability"
            ):
                bootstrap_existing.bootstrap_existing(workspace, corrupt_target)
            self.assertFalse((corrupt_target / "workspace.json").exists())


class GitHygieneTests(unittest.TestCase):
    engine = Path(__file__).resolve().parents[2]

    def config(self):
        return yaml.safe_load((self.engine / ".pre-commit-config.yaml").read_text())

    def eligible(self, path, hook=None):
        config = self.config()
        if not re.search(config["files"], path) or re.search(config["exclude"], path):
            return False
        return hook is None or re.search(hook.get("files", ""), path) is not None

    def test_filters_cover_real_paths_and_reject_prefix_lookalikes(self):
        for path in (
            "workbench/salam_workbench/gui.py",
            "workbench/tests/test_portability.py",
            "workbench/scripts/verify.py",
            "workbench/visualizer/__init__.py",
            "workbench/docs/planning/project.json",
            "workbench/experiments/gemm/example.yml",
            "workbench/requirements-gui-gem5-26-validated.txt",
            "workbench/README.md",
            "docker/export_salam_visualizer.py",
            ".github/workflows/ci.yml",
            ".github/requirements-ci-gem5-26.txt",
            "docs/CI.md",
            "util/pre-commit-install.sh",
            "src/hwacc/AccCluster.py",
            "src/hwacc/tests/verify_native_stats.py",
            "configs/SALAM/HWAccConfig.py",
            "SALAM-Configurator/parser.py",
            "tools/SALAM-Configurator/systembuilder.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.eligible(path))
        for path in (
            "workbench/salam_workbench/vendor/old.py",
            "workbench/experiments/regression/overlays/foo.py",
            "workbench/docs/patches/before.py",
            "workbench/docs/ci/legacy-workflow.yml",
            "workbench/salam_workbench_backup/gui.py",
            "workbench/docs_extra/file.md",
            "workbench/README.md.bak",
            "other/workbench/tests/test.py",
            ".github/workflows/ci.yml.extra",
            "configs/SALAM/generated/old.py",
            "src/hwacc/HWModeling/generated/old.py",
            "src/hwacc/Scripts/statParser.py",
            "src/hwacc/instruction.cc",
            "MAINTAINERS.yaml",
        ):
            with self.subTest(path=path):
                self.assertFalse(self.eligible(path))

    def test_workbench_checks_are_preserved_and_salam_syntax_is_separate(self):
        hooks = {item["id"]: item for item in self.config()["repos"][0]["hooks"]}
        for name in ("workbench-black", "workbench-isort", "workbench-python-syntax"):
            for path in (
                "workbench/salam_workbench/gui.py",
                "workbench/tests/test_portability.py",
                "workbench/visualizer/export.py",
                "docker/export_salam_visualizer.py",
            ):
                with self.subTest(hook=name, path=path):
                    self.assertTrue(self.eligible(path, hooks[name]))
            self.assertFalse(self.eligible("src/hwacc/AccCluster.py", hooks[name]))
        for name in ("maintained-eof", "maintained-trailing-whitespace"):
            self.assertTrue(self.eligible("workbench/docs/notes.md", hooks[name]))
            self.assertFalse(self.eligible("src/hwacc/AccCluster.py", hooks[name]))
        self.assertTrue(
            self.eligible("src/hwacc/AccCluster.py", hooks["salam-python-syntax"])
        )
        self.assertTrue(
            self.eligible(
                "workbench/docs/planning/a.json", hooks["workbench-json-syntax"]
            )
        )
        self.assertTrue(
            self.eligible("workbench/experiments/a.yml", hooks["workbench-yaml-syntax"])
        )
        self.assertEqual(hooks["gem5-commit-msg-checker"]["stages"], ["commit-msg"])

    def fixture(self, base):
        repo = base / "repo with spaces"
        repo.mkdir()
        util = repo / "util"
        util.mkdir()
        shutil.copyfile(
            self.engine / "util/pre-commit-install.sh", util / "pre-commit-install.sh"
        )
        bin_dir = base / "bin"
        bin_dir.mkdir()
        executable = bin_dir / "pre-commit"
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SALAM_HOOK_LOG"\n')
        executable.chmod(0o755)
        env = os.environ.copy()
        for key in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env.pop(key, None)
        env.update(
            PATH=str(bin_dir) + os.pathsep + "/usr/bin:/bin",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_NOSYSTEM="1",
            SALAM_HOOK_LOG=str(base / "hook-invocation.txt"),
        )
        subprocess.run(["git", "init", "--quiet", str(repo)], env=env, check=True)
        return repo, env

    def install(self, repo, env, *args):
        return subprocess.run(
            ["bash", str(repo / "util/pre-commit-install.sh"), *args],
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installer_requires_explicit_install_and_delegates_to_precommit(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo, env = self.fixture(base)
            for args in ((), ("--help",), ("--unknown",), ("--install", "extra")):
                result = self.install(repo, env, *args)
                self.assertEqual(
                    result.returncode, 0 if not args or args == ("--help",) else 2
                )
                self.assertFalse(Path(env["SALAM_HOOK_LOG"]).exists())
            result = self.install(repo, env, "--install")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                Path(env["SALAM_HOOK_LOG"]).read_text().splitlines(),
                ["install", "--hook-type", "pre-commit", "--hook-type", "commit-msg"],
            )

    def test_installer_preserves_custom_hooks_symlinks_and_hookspath(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo, env = self.fixture(base)
            hooks = repo / ".git/hooks"
            custom = hooks / "commit-msg"
            custom.write_bytes(b"#!/bin/sh\nexit 0\n")
            for kind in ("regular", "dangling_symlink"):
                if kind == "dangling_symlink":
                    custom.unlink()
                    custom.symlink_to(base / "missing")
                before = (
                    custom.read_bytes() if custom.is_file() else os.readlink(custom)
                )
                result = self.install(repo, env, "--install")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(Path(env["SALAM_HOOK_LOG"]).exists())
                self.assertEqual(
                    custom.read_bytes() if custom.is_file() else os.readlink(custom),
                    before,
                )
            subprocess.run(
                ["git", "config", "core.hooksPath", str(base / "custom")],
                cwd=repo,
                env=env,
                check=True,
            )
            result = self.install(repo, env, "--install")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("core.hooksPath", result.stderr)
            self.assertFalse(Path(env["SALAM_HOOK_LOG"]).exists())

    def test_installer_checks_common_hook_directory_for_linked_worktrees(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo, env = self.fixture(base)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "--quiet",
                    "--allow-empty",
                    "-m",
                    "fixture",
                ],
                cwd=repo,
                env=env,
                check=True,
            )
            linked = base / "linked checkout"
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "worktree",
                    "add",
                    "--quiet",
                    "--detach",
                    str(linked),
                ],
                cwd=repo,
                env=env,
                check=True,
            )
            (linked / "util").mkdir()
            shutil.copyfile(
                repo / "util/pre-commit-install.sh",
                linked / "util/pre-commit-install.sh",
            )
            custom = repo / ".git/hooks/pre-commit"
            custom.write_bytes(b"custom common hook\n")
            result = self.install(linked, env, "--install")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(custom.read_bytes(), b"custom common hook\n")
            self.assertFalse(Path(env["SALAM_HOOK_LOG"]).exists())


if __name__ == "__main__":
    unittest.main()
