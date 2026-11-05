"""Focused safety tests for isolated GUI hardware variants."""
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from salam_workbench.hardware_codegen import _normalize_profile_overrides
from salam_workbench.hardware_variants import (
    _configuration_hashes,
    _copy_engine,
    _fingerprint,
    _fingerprint_inputs,
    _link_plan,
    _profile_hashes,
    _verify_variant,
    ensure_hardware_variant,
)


class HardwareVariantsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_profile_override_fields_are_checked_and_numeric(self):
        got = _normalize_profile_overrides(
            {
                "integer_multiplier": {
                    "internal_power": "0.0125",
                    "area": 7.25,
                    "fu_latency": 6,
                    "limit": 0,
                }
            }
        )
        self.assertEqual(got["integer_multiplier"]["internal_power"], 0.0125)
        self.assertEqual(got["integer_multiplier"]["area"], 7.25)
        self.assertEqual(got["integer_multiplier"]["fu_latency"], 6)
        for invalid in (
            {"integer_multiplier": {"limit": 1}},
            {"integer_multiplier": {"functional_unit_limit": 1}},
            {"integer_multiplier": {"area": "NaN"}},
            {"../unit": {"area": 1}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _normalize_profile_overrides(invalid)
        self.assertEqual(
            _normalize_profile_overrides(
                {"integer_adder": {"limit": 2}}, allow_fu_limit=True
            ),
            {"integer_adder": {"limit": 2}},
        )

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
        self.assertEqual((variant / "build/file.cc").resolve(), variant / "src/file.cc")
        (variant / "build/file.cc").write_text("variant", encoding="utf-8")
        self.assertEqual((source / "file.cc").read_text(), "base")

    def test_link_outside_base_fails_preflight(self):
        base = self.root / "base"
        base.mkdir()
        (base / "external").symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "leaves base"):
            _link_plan(base)

    def test_preserved_link_history_stays_in_base_and_is_not_a_live_build_input(self):
        base = self.root / "base"
        history = base / ".workbench-link-history/build"
        history.mkdir(parents=True)
        archived = history / "old-source"
        archived.symlink_to(self.root / "previous-engine/source")
        (base / "SConstruct").write_text("# current source\n")
        links = _link_plan(base)
        self.assertEqual(links, {})
        variant = self.root / "variant"
        _copy_engine(base, variant, links)
        self.assertTrue(archived.is_symlink())
        self.assertFalse((variant / ".workbench-link-history").exists())
        self.assertEqual((variant / "SConstruct").read_text(), "# current source\n")

    def test_profile_hashes_pin_selected_files(self):
        base = self.root / "base"
        profile = (
            base / "benchmarks/sys_validation/gemm/configs/hw_interface/"
            "functional_units/40nm_model/5ns/default_profile/unit"
        )
        profile.mkdir(parents=True)
        (profile / "unit.yml").write_text("value: 1\n", encoding="utf-8")
        instructions = (
            base / "benchmarks/sys_validation/gemm/configs/"
            "hw_interface/instructions/inst_list.yml"
        )
        instructions.parent.mkdir(parents=True)
        instructions.write_text("instructions: {}\n", encoding="utf-8")
        for name in (
            "HWProfileGenerator.py",
            "SALAMClassGenerator.py",
            "SALAMArgs.py",
        ):
            (base / name).write_text("# source\n", encoding="utf-8")
        first = _profile_hashes(base, "gemm", "40nm_model", "5ns", "default_profile")
        (profile / "unit.yml").write_text("value: 2\n", encoding="utf-8")
        second = _profile_hashes(base, "gemm", "40nm_model", "5ns", "default_profile")
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
            "base_engine": str(base),
            "base_build_receipt": {"path": str(receipt)},
            "base_compiled_source_sha256": "source",
            "selected_profile_inputs": {"profile.yml": "digest"},
            "selection": {"benchmark": "gemm", "period": "5ns"},
            "profile_overrides": {},
            "toolchain_and_adapter": {"build_engine": "current"},
        }
        prior = dict(current_inputs)
        prior["toolchain_and_adapter"] = {"build_engine": "missing"}
        (old / ".workbench-variant.json").write_text(
            json.dumps(
                {
                    "state": "built",
                    "fingerprint": "old-fingerprint",
                    "fingerprint_inputs": prior,
                }
            ),
            encoding="utf-8",
        )
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch("salam_workbench.hardware_variants.verify_engine")
            )
            stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants._fingerprint_inputs",
                    return_value=current_inputs,
                )
            )
            stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants._fingerprint",
                    return_value="current-fingerprint",
                )
            )
            stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants._link_plan",
                    return_value={},
                )
            )
            generate = stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants.hardware_codegen.generate_hardware_code",
                    return_value={
                        "state": "failed",
                        "valid": False,
                        "errors": ["expected test stop"],
                        "build_consumer_issues": [],
                    },
                )
            )
            result = ensure_hardware_variant(
                base,
                variants,
                self.root / "evidence",
                "gemm",
                base_build_receipt=receipt,
            )
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
            json.dumps(
                {
                    "state": "built",
                    "fingerprint": "current-fingerprint",
                    "engine_path": str(existing),
                    "fingerprint_inputs": {"selected_profile_inputs": {}},
                }
            ),
            encoding="utf-8",
        )
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch("salam_workbench.hardware_variants.verify_engine")
            )
            stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants._fingerprint_inputs",
                    return_value={"selected_profile_inputs": {}},
                )
            )
            stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants._fingerprint",
                    return_value="current-fingerprint",
                )
            )
            verify = stack.enter_context(
                mock.patch("salam_workbench.hardware_variants._verify_variant")
            )
            generate = stack.enter_context(
                mock.patch(
                    "salam_workbench.hardware_variants.hardware_codegen.generate_hardware_code"
                )
            )
            result = ensure_hardware_variant(
                base,
                variants,
                self.root / "evidence",
                "gemm",
                base_build_receipt=receipt,
            )
        self.assertEqual(result["state"], "reused")
        verify.assert_called_once()
        generate.assert_not_called()

    def configuration_fixture(self):
        base = self.root / "config-engine"
        for relative in (
            "configs/common/Simulation.py",
            "configs/SALAM/HWAccConfig.py",
            "SALAM-Configurator/fs_template.py",
            "SALAM-Configurator/systembuilder.py",
            "SALAM-Configurator/parser.py",
        ):
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# actual configuration fixture\n")
        return base

    def test_runtime_configuration_change_invalidates_variant_fingerprint(self):
        base = self.configuration_fixture()
        receipt = self.root / "build.json"
        receipt.write_text("{}")
        with mock.patch(
            "salam_workbench.hardware_variants.compiled_identity",
            return_value={"sha256": "unchanged-compiled-source"},
        ), mock.patch(
            "salam_workbench.hardware_variants._profile_hashes", return_value={}
        ), mock.patch(
            "salam_workbench.hardware_variants._toolchain_hashes", return_value={}
        ):
            before = _fingerprint_inputs(
                base, "gemm", "40nm_model", "5ns", "default_profile", {}, receipt
            )
            (base / "configs/common/Simulation.py").write_text(
                "# changed final native clock adapter\n"
            )
            after = _fingerprint_inputs(
                base, "gemm", "40nm_model", "5ns", "default_profile", {}, receipt
            )
        self.assertEqual(
            before["base_compiled_source_sha256"], after["base_compiled_source_sha256"]
        )
        self.assertNotEqual(_fingerprint(before), _fingerprint(after))

    def test_configuration_identity_requires_runtime_and_builder_sources(self):
        base = self.configuration_fixture()
        (base / "configs/common/Simulation.py").rename(
            base / "configs/common/Simulation.py.saved"
        )
        with self.assertRaisesRegex(
            ValueError, "Missing hardware variant configuration"
        ):
            _configuration_hashes(base)

    def test_generated_configuration_outputs_do_not_invalidate_source_identity(self):
        base = self.configuration_fixture()
        before = _configuration_hashes(base)
        generated = base / "configs/SALAM/generated/fs_gemm.py"
        generated.parent.mkdir()
        generated.write_text("# generated per request\n")
        self.assertEqual(before, _configuration_hashes(base))
        helper = base / "configs/common/new_runtime_helper.py"
        helper.write_text("# newly imported runtime helper\n")
        self.assertNotEqual(before, _configuration_hashes(base))

    def test_variant_configuration_tampering_is_rejected_on_reuse(self):
        variant = self.configuration_fixture()
        sources = _configuration_hashes(variant)
        generation = self.root / "generation.json"
        generation.write_text(
            json.dumps({"state": "generated", "valid": True, "outputs": []})
        )
        build = self.root / "build.json"
        build.write_text("{}")
        manifest = {
            "state": "built",
            "fingerprint": "key",
            "build_receipt": str(build),
            "generation_receipt": str(generation),
            "fingerprint_inputs": {"configuration_source_inputs": sources},
        }
        with mock.patch("salam_workbench.hardware_variants.verify_engine"):
            self.assertEqual(_verify_variant(variant, manifest, "key", {}), manifest)
            (variant / "configs/common/Simulation.py").write_text(
                "# stale/corrupted cached runtime\n"
            )
            with self.assertRaisesRegex(ValueError, "configuration source identity"):
                _verify_variant(variant, manifest, "key", {})

    def test_symlinked_runtime_configuration_is_rejected(self):
        base = self.configuration_fixture()
        path = base / "configs/common/Simulation.py"
        preserved = path.with_suffix(".saved")
        path.rename(preserved)
        path.symlink_to(preserved)
        with self.assertRaisesRegex(
            ValueError, "Symlinked hardware variant configuration"
        ):
            _configuration_hashes(base)


if __name__ == "__main__":
    unittest.main()
