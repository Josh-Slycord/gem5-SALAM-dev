"""Unsupported modern reference routes fail before paths, writes or subprocesses."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from salam_workbench import checks, gemm, regression, toolchain_profile, variant


class LegacyHarnessGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        (self.project / "workspace.json").write_text(
            json.dumps(
                {
                    "configuration_engine": {
                        "toolchain_profile": "gem5-26-retained-salam"
                    }
                }
            )
        )

    def test_absent_profile_keeps_legacy_harness_available(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(
                toolchain_profile.require_legacy_harness(Path(directory), "reproduce")
            )

    def test_modern_reproduce_rejects_before_resolving_or_writing(self):
        with mock.patch.object(gemm, "PROJECT", self.project), self.assertRaisesRegex(
            ValueError, "reproduce is unavailable"
        ):
            gemm.reproduce(object(), object())

    def test_modern_regression_rejects_before_catalog_or_source_access(self):
        with mock.patch.object(regression, "PROJECT", self.project), mock.patch.object(
            regression,
            "load_catalog",
            side_effect=AssertionError("catalog must not be read"),
        ), self.assertRaisesRegex(ValueError, "regression is unavailable"):
            regression.run_regression(object())

    def test_modern_compare_rejects_before_source_or_git_access(self):
        with mock.patch.object(gemm, "PROJECT", self.project), mock.patch.object(
            gemm, "git", side_effect=AssertionError("git must not run")
        ), self.assertRaisesRegex(ValueError, "compare is unavailable"):
            variant.run_study(object(), object())

    def test_modern_gemm_tier_rejects_before_engine_access(self):
        with self.assertRaisesRegex(ValueError, "checks --tier gemm is unavailable"):
            checks.build_plan(
                "gemm",
                self.project,
                self.project / "evidence",
                engine=object(),
                allow_simulation=True,
            )

    def test_source_only_modern_check_tiers_remain_available(self):
        for tier in ("fast", "config", "gui"):
            with self.subTest(tier=tier):
                plan = checks.build_plan(tier, self.project, self.project / "evidence")
                self.assertEqual(plan[0]["name"], "unit-" + tier)
