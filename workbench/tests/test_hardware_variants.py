"""Focused safety tests for isolated GUI hardware variants."""
from contextlib import ExitStack
import json
from pathlib import Path
from unittest import mock
import tempfile
import unittest

from salam_workbench.hardware_codegen import _normalize_profile_overrides
from salam_workbench.hardware_variants import (
    _copy_engine, _fingerprint, _link_plan, _profile_hashes,
    ensure_hardware_variant,
)


class HardwareVariantsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_profile_override_fields_are_checked_and_numeric(self):
        got = _normalize_profile_overrides({
            "integer_multiplier": {"internal_power": "0.0125", "area": 7.25,
                                   "fu_latency": 6, "limit": 0}})
        self.assertEqual(got["integer_multiplier"]["internal_power"], 0.0125)
        self.assertEqual(got["integer_multiplier"]["area"], 7.25)
        self.assertEqual(got["integer_multiplier"]["fu_latency"], 6)
        for invalid in ({"integer_multiplier": {"limit": 1}},
                        {"integer_multiplier": {"functional_unit_limit": 1}},
                        {"integer_multiplier": {"area": "NaN"}},
                        {"../unit": {"area": 1}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _normalize_profile_overrides(invalid)
        self.assertEqual(_normalize_profile_overrides(
            {"integer_adder": {"limit": 2}}, allow_fu_limit=True),
            {"integer_adder": {"limit": 2}})

    def test_fingerprint_changes_with_requested_coefficients(self):
        inputs = {"profile_overrides": {"integer_multiplier": {"area": 7.25}}}
        same = {"profile_overrides": {"integer_multiplier": {"area": 7.25}}}
        changed = {"profile_overrides": {"integer_multiplier": {"area": 8.0}}}
        self.assertEqual(_fingerprint(inputs), _fingerprint(same))
        self.assertNotEqual(_fingerprint(inputs), _fingerprint(changed))

    def test_absolute_build_link_is_retargeted_to_variant(self):
        base = self.root / "base"
        source = base / "src"
        build = base / "build"
        source.mkdir(parents=True)
        build.mkdir()
        (source / "file.cc").write_text("base", encoding="utf-8")
        (build / "file.cc").symlink_to(source / "file.cc")
        variant = self.root / "variant"
        links = _link_plan(base)
        self.assertTrue(links["build/file.cc"]["absolute"])
        _copy_engine(base, variant, links)
        self.assertEqual((variant / "build/file.cc").resolve(),
                         variant / "src/file.cc")
        (variant / "build/file.cc").write_text("variant", encoding="utf-8")
        self.assertEqual((source / "file.cc").read_text(), "base")

    def test_link_outside_base_fails_preflight(self):
        base = self.root / "base"
        base.mkdir()
        (base / "external").symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "leaves base"):
            _link_plan(base)

    def test_profile_hashes_pin_selected_files(self):
        base = self.root / "base"
        profile = (base / "benchmarks/sys_validation/gemm/configs/hw_interface/"
                   "functional_units/40nm_model/5ns/default_profile/unit")
        profile.mkdir(parents=True)
        (profile / "unit.yml").write_text("value: 1\n", encoding="utf-8")
        instructions = (base / "benchmarks/sys_validation/gemm/configs/"
                        "hw_interface/instructions/inst_list.yml")
        instructions.parent.mkdir(parents=True)
        instructions.write_text("instructions: {}\n", encoding="utf-8")
        for name in ("HWProfileGenerator.py", "SALAMClassGenerator.py",
                     "SALAMArgs.py"):
            (base / name).write_text("# source\n", encoding="utf-8")
        first = _profile_hashes(base, "gemm", "40nm_model", "5ns",
                                "default_profile")
        (profile / "unit.yml").write_text("value: 2\n", encoding="utf-8")
        second = _profile_hashes(base, "gemm", "40nm_model", "5ns",
                                 "default_profile")
        self.assertNotEqual(first, second)

    def test_prior_fingerprint_does_not_reuse_without_current_helpers(self):
        base = self.root / "base"
        base.mkdir()
        receipt = self.root / "base-build.json"
        receipt.write_text("{}", encoding="utf-8")
        variants = self.root / "variants"
        old = variants / "old-fingerprint"
        old.mkdir(parents=True)
        current_inputs = {
            "base_engine": str(base), "base_build_receipt": {"path": str(receipt)},
            "base_compiled_source_sha256": "source",
            "selected_profile_inputs": {"profile.yml": "digest"},
            "selection": {"benchmark": "gemm", "period": "5ns"},
            "profile_overrides": {}, "toolchain_and_adapter": {"build_engine": "current"},
        }
        prior = dict(current_inputs)
        prior["toolchain_and_adapter"] = {"build_engine": "missing"}
        (old / ".workbench-variant.json").write_text(
            json.dumps({"state": "built", "fingerprint": "old-fingerprint",
                        "fingerprint_inputs": prior}), encoding="utf-8")
        with ExitStack() as stack:
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants.verify_engine"))
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants._fingerprint_inputs",
                return_value=current_inputs))
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants._fingerprint",
                return_value="current-fingerprint"))
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants._link_plan",
                return_value={}))
            generate = stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants.hardware_codegen.generate_hardware_code",
                return_value={"state": "failed", "valid": False,
                              "errors": ["expected test stop"],
                              "build_consumer_issues": []}))
            result = ensure_hardware_variant(
                base, variants, self.root / "evidence", "gemm",
                base_build_receipt=receipt)
        self.assertEqual(result["state"], "failed")
        generate.assert_called_once()
        self.assertFalse((variants / "current-fingerprint").exists())

    def test_exact_fingerprint_reuses_verified_variant(self):
        base = self.root / "base"
        base.mkdir()
        receipt = self.root / "base-build.json"
        receipt.write_text("{}", encoding="utf-8")
        variants = self.root / "variants"
        existing = variants / "current-fingerprint"
        existing.mkdir(parents=True)
        (existing / ".workbench-variant.json").write_text(
            json.dumps({"state": "built", "fingerprint": "current-fingerprint",
                        "engine_path": str(existing)}), encoding="utf-8")
        with ExitStack() as stack:
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants.verify_engine"))
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants._fingerprint_inputs",
                return_value={"selected_profile_inputs": {}}))
            stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants._fingerprint",
                return_value="current-fingerprint"))
            verify = stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants._verify_variant"))
            generate = stack.enter_context(mock.patch(
                "salam_workbench.hardware_variants.hardware_codegen.generate_hardware_code"))
            result = ensure_hardware_variant(
                base, variants, self.root / "evidence", "gemm",
                base_build_receipt=receipt)
        self.assertEqual(result["state"], "reused")
        verify.assert_called_once()
        generate.assert_not_called()



if __name__ == "__main__":
    unittest.main()
