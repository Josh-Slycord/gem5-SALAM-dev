# SPDX-License-Identifier: BSD-3-Clause
"""Unit binding guards; fake m5 construction is not simulator qualification."""

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from salam_workbench import native_config
from salam_workbench.native_config import NormalizedConfiguration

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bound_model_native_factory", REPO / "configs/SALAM/native_factory.py"
)
FACTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FACTORY)


class NativeBoundModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.snapshot = self.root / "configs/SALAM/generated/native_gemm.json"
        self.snapshot.parent.mkdir(parents=True)
        self.config = self.root / "benchmarks/sys_validation/gemm/config.yml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text("configuration_revision: 1\n")
        self.ir = self.config.parent / "hw/gemm.ll"
        self.ir.parent.mkdir()
        self.ir.write_text("; unit guard fixture; no simulation\n")
        self.factory_source = self.root / "configs/SALAM/native_factory.py"
        self.hardware_source = self.factory_source.with_name("HWAccConfig.py")
        self.normalizer_source = (
            self.root / "workbench/salam_workbench/native_config.py"
        )
        for source in (
            self.factory_source,
            self.hardware_source,
            self.normalizer_source,
        ):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# Unit source-affinity fixture only.\n")
        self.model = self.fresh_model()
        self.snapshot.write_text(self.model.to_json())
        self.binding = {
            "expected_model_path": str(self.snapshot),
            "expected_model_sha256": self.model.sha256,
            "expected_layout_sha256": self.model.layout_sha256,
        }

    def fresh_model(self, *args, **kwargs):
        """A small canonical model with freshly read input identities.

        This fixture isolates binding/call-order behavior. Real normalizer,
        topology and numerical checks live in their separate test layers.
        """

        def dependency(path, kind):
            content = path.read_bytes()
            return {
                "path": path.relative_to(self.root).as_posix(),
                "kind": kind,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }

        config = dependency(self.config, "configuration")
        document = {
            "schema_version": 1,
            "kind": "salam_native_configuration",
            "engine_root": str(self.root),
            "base_address": 0x10020000,
            "source": config,
            "dependencies": [config, dependency(self.ir, "llvm_ir")],
            "clusters": [{"name": "unit_fixture"}],
        }
        return NormalizedConfiguration(
            json.dumps(document, sort_keys=True, separators=(",", ":"))
        )

    def verify(self, model=None, **overrides):
        values = dict(self.binding, **overrides)
        return FACTORY._verify_expected_model(
            model or self.fresh_model(), self.root, **values
        )

    def factory_context(self):
        """Provide source affinity and a construction sentinel for public entry."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        fake_m5 = types.ModuleType("m5")
        fake_m5.options = types.SimpleNamespace(outdir=str(self.root / "out"))
        fake_hardware = types.ModuleType("HWAccConfig")
        fake_hardware.__file__ = str(self.hardware_source)
        stack.enter_context(
            patch.dict(
                sys.modules,
                {"m5": fake_m5, "HWAccConfig": fake_hardware},
            )
        )
        stack.enter_context(patch.object(sys, "path", list(sys.path)))
        stack.enter_context(
            patch.dict(os.environ, {"M5_PATH": str(self.root), "SALAM_EXPORT_CDFG": ""})
        )
        stack.enter_context(patch.object(FACTORY, "__file__", str(self.factory_source)))
        stack.enter_context(
            patch.object(native_config, "__file__", str(self.normalizer_source))
        )
        normalize = stack.enter_context(
            patch.object(
                native_config,
                "normalize_configuration",
                side_effect=self.fresh_model,
            )
        )
        construct = stack.enter_context(
            patch.object(FACTORY, "_build_clusters", return_value={})
        )
        options = types.SimpleNamespace(
            salam_config=str(self.config), salam_base_address=0x10020000
        )
        system = types.SimpleNamespace(untouched=True)
        return stack, normalize, construct, options, system

    def reject_before_construction(
        self, *, message=None, exception=ValueError, **overrides
    ):
        values = dict(self.binding, **overrides)
        stack, normalize, construct, options, system = self.factory_context()
        with stack:
            if message is None:
                with self.assertRaises(exception):
                    FACTORY.makeHWAcc(options, system, **values)
            else:
                with self.assertRaisesRegex(exception, message):
                    FACTORY.makeHWAcc(options, system, **values)
            normalize.assert_called_once()
            construct.assert_not_called()
            self.assertEqual(vars(system), {"untouched": True})
            self.assertFalse((self.root / "out").exists())

    def test_exact_fresh_snapshot_and_identities_pass(self):
        record = self.verify()
        self.assertTrue(record["verified_against_fresh_sources"])
        self.assertEqual(record["semantic_sha256"], self.model.sha256)
        self.assertEqual(record["layout_sha256"], self.model.layout_sha256)
        self.assertEqual(
            record["file_sha256"],
            hashlib.sha256(self.snapshot.read_bytes()).hexdigest(),
        )

    def test_equivalent_json_formatting_preserves_semantic_binding(self):
        self.snapshot.write_text(self.model.to_json(indent=None))
        self.assertEqual(self.verify()["semantic_sha256"], self.model.sha256)

    def test_complete_binding_reaches_construction_once_after_guard(self):
        stack, normalize, construct, options, system = self.factory_context()
        with stack:
            receipt = FACTORY.makeHWAcc(options, system, **self.binding)
            normalize.assert_called_once_with(
                self.config, self.root, base_address=0x10020000
            )
            construct.assert_called_once_with(
                options, system, self.fresh_model().to_dict()
            )
            self.assertTrue(
                receipt["generation_binding"]["verified_against_fresh_sources"]
            )

    def test_manual_unbound_entry_is_explicitly_optional(self):
        self.assertIsNone(
            FACTORY._verify_expected_model(self.model, self.root, None, None, None)
        )

    def test_each_partial_binding_fails_before_construction(self):
        for key in self.binding:
            with self.subTest(missing=key):
                self.reject_before_construction(message="requires path", **{key: None})

    def test_missing_snapshot_does_not_construct(self):
        self.reject_before_construction(
            expected_model_path=str(self.snapshot.with_name("missing.json")),
            exception=FileNotFoundError,
        )

    def test_relative_snapshot_is_not_a_bound_input(self):
        self.reject_before_construction(
            expected_model_path="configs/SALAM/generated/native_gemm.json",
            message="regular contained path",
        )

    def test_outside_snapshot_is_rejected_before_construction(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        outside = Path(other.name).resolve() / "native_gemm.json"
        outside.write_text(self.model.to_json())
        self.reject_before_construction(expected_model_path=str(outside))

    def test_symlink_snapshot_is_rejected_before_construction(self):
        alias = self.snapshot.with_name("alias.json")
        alias.symlink_to(self.snapshot)
        self.reject_before_construction(
            expected_model_path=str(alias), message="regular contained path"
        )

    def test_symlink_parent_is_rejected_before_reading_snapshot(self):
        alias = self.root / "alias_generated"
        alias.symlink_to(self.snapshot.parent, target_is_directory=True)
        target = alias / self.snapshot.name
        with patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("Binding must reject before reading"),
        ):
            with self.assertRaisesRegex(ValueError, "regular contained path"):
                self.verify(model=self.model, expected_model_path=str(target))

    def test_nonregular_snapshot_is_rejected_before_construction(self):
        self.reject_before_construction(
            expected_model_path=str(self.snapshot.parent),
            message="bounded regular data",
        )

    def test_oversized_snapshot_is_not_parsed_or_constructed(self):
        oversized = self.snapshot.with_name("oversized.json")
        with oversized.open("wb") as output:
            output.seek(16 * 1024**2)
            output.write(b"0")
        self.reject_before_construction(
            expected_model_path=str(oversized), message="bounded regular data"
        )

    def test_duplicate_json_keys_fail_before_construction(self):
        text = self.model.to_json()
        self.snapshot.write_text(text.replace("{\n", '{\n  "schema_version": 1,\n', 1))
        self.reject_before_construction(message="Duplicate native model")

    def test_nested_duplicate_json_keys_are_also_rejected(self):
        self.snapshot.write_text('{"outer":{"value":1,"value":1}}')
        self.reject_before_construction(message="Duplicate native model")

    def test_nonfinite_json_is_rejected_before_construction(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                self.snapshot.write_text('{"number":' + value + "}")
                self.reject_before_construction(message="Nonfinite")

    def test_invalid_expected_hashes_are_rejected(self):
        for value in ("", "0" * 63, "G" * 64, "A" * 64, 123):
            with self.subTest(hash=value):
                self.reject_before_construction(
                    expected_model_sha256=value,
                    message="Invalid expected",
                )

    def test_wrong_semantic_hash_fails_before_construction(self):
        self.reject_before_construction(
            expected_model_sha256="0" * 64, message="semantic hash"
        )

    def test_current_configuration_drift_fails_before_construction(self):
        self.config.write_text("configuration_revision: 2\n")
        self.assertNotEqual(self.fresh_model().sha256, self.model.sha256)
        self.reject_before_construction(
            message="Fresh normalized configuration differs"
        )

    def test_current_ir_drift_fails_even_when_layout_is_unchanged(self):
        self.ir.write_text("; different built IR\n")
        self.assertEqual(self.fresh_model().layout_sha256, self.model.layout_sha256)
        self.assertNotEqual(self.fresh_model().sha256, self.model.sha256)
        self.reject_before_construction(
            message="Fresh normalized configuration differs"
        )

    def test_layout_mismatch_fails_before_construction(self):
        self.reject_before_construction(
            expected_layout_sha256="0" * 64, message="Fresh normalized layout"
        )

    def test_rehashed_foreign_snapshot_never_becomes_authority(self):
        document = self.model.to_dict()
        document["base_address"] += 64
        foreign = NormalizedConfiguration(
            json.dumps(document, sort_keys=True, separators=(",", ":"))
        )
        self.snapshot.write_text(foreign.to_json())
        self.reject_before_construction(
            expected_model_sha256=foreign.sha256,
            expected_layout_sha256=foreign.layout_sha256,
            message="Fresh normalized configuration differs",
        )


if __name__ == "__main__":
    unittest.main()
