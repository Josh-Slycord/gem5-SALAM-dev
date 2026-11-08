# SPDX-License-Identifier: BSD-3-Clause
"""Normalized generation seam tests using a real temporary typed catalogue.

The IR payloads are synthetic parser fixtures. No compiler, simulator, legacy
generator or generated topology module executes in these tests.
"""
import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_native_config as config_fixtures

from salam_workbench import configurator, native_config, native_generation

REPO = Path(__file__).resolve().parents[2]


def _factory_module():
    spec = importlib.util.spec_from_file_location(
        "native_generation_factory_checks", REPO / "configs/SALAM/native_factory.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeGenerationIntegrationTests(unittest.TestCase):
    def setUp(self):
        fixture = config_fixtures.NativeConfigurationTests(
            "test_full_gemm_retains_exact_allocator_and_defaults"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.workspace = fixture.root
        self.config = fixture.config
        self.directory = self.workspace / "preparation-evidence"
        self.directory.mkdir()
        self.spec = {
            "schema_version": 1,
            "name": "native_fixture",
            "builder": "native",
            "benchmark": "benchmarks/sys_validation/gemm",
            "base_address": "0x10020000",
            "system": {},
            "parameters": {},
        }
        for relative in (
            "workbench/salam_workbench/native_config.py",
            "configs/SALAM/native_factory.py",
            "SALAM-Configurator/fs_template.py",
        ):
            target = self.workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        self.generated = self.workspace / "configs/SALAM/generated"
        self.header = self.config.parent / "gemm_clstr_hw_defines.h"
        self.factory = _factory_module()

    def prepare(self):
        return native_generation.prepare_headers(
            self.workspace, self.spec, self.directory
        )

    def finalize(self, generation):
        return native_generation.finalize_wrapper(
            self.workspace, self.spec, self.directory, generation
        )

    def inspect(self, generation, *, final=False):
        return native_generation.inspect_outputs(
            self.workspace, self.spec, self.directory, generation, final=final
        )

    def wire(self, generation):
        # Only host-toolchain policy is substituted. The actual runtime
        # copying, request serialization and wrapper rewriting run unchanged.
        profile = {
            "effective": {"cpu-type": "ArmO3CPU"},
            "requested": {},
            "normalizations": [],
            "toolchain_profile": {"name": "unit-test-policy"},
        }
        with patch.object(
            configurator, "effective_system_configuration", return_value=profile
        ):
            return native_generation.bind_runtime(
                self.workspace, self.spec, self.directory, generation
            )

    def complete(self):
        prepared = self.prepare()
        final = self.finalize(prepared)
        return self.wire(final)

    def test_absent_ir_can_prepare_headers_then_bind_final_built_payloads(self):
        old_ir = []
        for name in ("top", "gemm"):
            path = self.config.parent / "hw" / (name + ".ll")
            path.rename(path.with_suffix(".prior"))
            old_ir.append(path)
        with patch(
            "subprocess.run", side_effect=AssertionError("No generator process")
        ):
            prepared = self.prepare()
            self.assertEqual(prepared["state"], "headers_prepared")
            self.assertFalse(prepared["legacy_generator_executed"])
            self.assertFalse(prepared["topology_module_generated"])
            self.assertFalse((self.generated / "native_fixture.py").exists())
            self.assertFalse((self.generated / "fs_native_fixture.py").exists())
            header = self.header.read_bytes()
            for path in old_ir:
                path.write_text(
                    "; synthetic post-build fixture\n"
                    "define void @{}() {{ ret void }}\n".format(path.stem)
                )
            final = self.finalize(prepared)
            self.assertEqual(final["state"], "wrapper_prepared")
            self.assertEqual(final["layout_sha256"], prepared["layout_sha256"])
            self.assertEqual(self.header.read_bytes(), header)
            final = self.wire(final)
            inspected = self.inspect(final, final=True)
        self.assertEqual(inspected["state"], "generated")
        self.assertFalse((self.generated / "native_fixture.py").exists())
        self.assertEqual(len(inspected["outputs"]), 3)

    def test_final_inspection_requires_actual_runtime_hook_not_bare_wrapper(self):
        generation = self.finalize(self.prepare())
        with self.assertRaises(ValueError):
            self.inspect(generation, final=True)
        generation = self.wire(generation)
        self.assertEqual(self.inspect(generation, final=True)["state"], "generated")
        wrapper = Path(generation["wrapper"]["path"]).read_text()
        self.assertEqual(
            wrapper.count("from workbench_runtime import configure_system"), 1
        )
        self.assertIn(repr(str(self.directory / "runtime-request.json")), wrapper)

    def test_address_or_hardware_yaml_drift_during_build_is_rejected(self):
        generation = self.prepare()
        self.config.write_text(
            self.config.read_text().replace("PIOSize: 25", "PIOSize: 64", 1)
        )
        with self.assertRaisesRegex(ValueError, "layout changed"):
            self.finalize(generation)
        self.assertFalse((self.generated / "fs_native_fixture.py").exists())

    def test_header_change_during_build_is_rejected_before_wrapper_write(self):
        generation = self.prepare()
        self.header.write_text(self.header.read_text() + "// changed during build\n")
        with self.assertRaisesRegex(ValueError, "header changed"):
            self.finalize(generation)
        self.assertFalse((self.generated / "fs_native_fixture.py").exists())

    def test_header_change_after_finalization_is_rejected(self):
        generation = self.complete()
        self.header.write_text(
            self.header.read_text().replace(
                "#define TOP 0x10020040", "#define TOP 0x10024040", 1
            )
        )
        with self.assertRaisesRegex(ValueError, "header changed"):
            self.inspect(generation, final=True)

    def test_missing_header_receipts_cannot_omit_required_header(self):
        generation = self.prepare()
        generation["headers"] = []
        with self.assertRaisesRegex(ValueError, "header set differs"):
            self.finalize(generation)

    def test_model_snapshot_tamper_is_rejected(self):
        generation = self.complete()
        path = Path(generation["model"]["path"])
        value = json.loads(path.read_text())
        value["base_address"] += 64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "model snapshot changed"):
            self.inspect(generation, final=True)

    def test_wrapper_tamper_and_duplicate_runtime_hook_are_rejected(self):
        generation = self.complete()
        path = Path(generation["wrapper"]["path"])
        original = path.read_text()
        for text in (
            original + "\nprint('unreviewed wrapper mutation')\n",
            native_generation._with_runtime(
                original, self.directory / "runtime-request.json"
            ),
        ):
            with self.subTest(text=text[-80:]):
                path.write_text(text)
                with self.assertRaisesRegex(ValueError, "renderer/runtime hook"):
                    self.inspect(generation, final=True)
        path.write_text(original)
        self.assertEqual(self.inspect(generation, final=True)["state"], "generated")

    def test_post_final_ir_change_requires_new_snapshot(self):
        generation = self.complete()
        path = self.config.parent / "hw/gemm.ll"
        path.write_text(path.read_text() + "; artifact changed\n")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.inspect(generation, final=True)

    def test_generated_topology_module_is_never_accepted(self):
        self.generated.mkdir(parents=True, exist_ok=True)
        path = self.generated / "native_fixture.py"
        path.write_text("raise RuntimeError('legacy topology must not execute')\n")
        with self.assertRaisesRegex(ValueError, "topology module"):
            self.prepare()
        self.assertFalse(self.header.exists())

    def test_initial_staged_frontend_mismatch_fails_without_header_writes(self):
        for relative in (
            "workbench/salam_workbench/native_config.py",
            "configs/SALAM/native_factory.py",
        ):
            path = self.workspace / relative
            original = path.read_bytes()
            path.write_bytes(original + b"\n# stale frontend\n")
            with self.subTest(relative=relative), self.assertRaisesRegex(
                ValueError, "frontend differs"
            ):
                self.prepare()
            self.assertFalse(self.header.exists())
            path.write_bytes(original)

    def test_staged_frontend_drift_during_build_is_rejected(self):
        generation = self.prepare()
        for relative in (
            "workbench/salam_workbench/native_config.py",
            "configs/SALAM/native_factory.py",
        ):
            path = self.workspace / relative
            original = path.read_bytes()
            path.write_bytes(original + b"\n# frontend drift after headers\n")
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.finalize(generation)
            path.write_bytes(original)

    def test_staged_frontend_drift_after_finalization_is_rejected(self):
        generation = self.complete()
        path = self.workspace / "configs/SALAM/native_factory.py"
        path.write_bytes(path.read_bytes() + b"\n# late frontend change\n")
        with self.assertRaises(ValueError):
            self.inspect(generation, final=True)

    def test_template_drift_during_build_is_rejected(self):
        generation = self.prepare()
        path = self.workspace / "SALAM-Configurator/fs_template.py"
        path.write_bytes(path.read_bytes() + b"\n# template drift\n")
        with self.assertRaises(ValueError):
            self.finalize(generation)

    def test_runtime_request_drift_is_rejected(self):
        generation = self.complete()
        path = self.directory / "runtime-request.json"
        value = json.loads(path.read_text())
        value["parameters"] = {"system.gemm_clstr.gemm": {"clock_period": 999}}
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.inspect(generation, final=True)

    def test_staged_runtime_adapter_drift_is_rejected(self):
        generation = self.complete()
        for name in ("workbench_runtime.py", "workbench_system_witness.py"):
            path = self.workspace / "configs/SALAM" / name
            original = path.read_bytes()
            path.write_bytes(original + b"\\n# changed after trusted runtime wiring\\n")
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.inspect(generation, final=True)
            path.write_bytes(original)

    def test_preserves_custom_header_text_and_records_before_image(self):
        prefix = "#pragma once\n// preserved authored preamble\n"
        self.header.write_text(prefix)
        generation = self.prepare()
        self.assertTrue(self.header.read_text().startswith(prefix))
        self.assertEqual(len(generation["header_before_images"]), 1)
        before = Path(generation["header_before_images"][0]["path"])
        self.assertEqual(before.read_text(), prefix)

    def test_factory_binding_verifies_fresh_model_before_construction(self):
        generation = self.complete()
        fresh = native_config.normalize_configuration(
            self.config, self.workspace, base_address=0x10020000
        )
        result = self.factory._verify_expected_model(
            fresh,
            self.workspace,
            generation["model"]["path"],
            generation["model_sha256"],
            generation["layout_sha256"],
        )
        self.assertTrue(result["verified_against_fresh_sources"])
        module = ast.parse((REPO / "configs/SALAM/native_factory.py").read_text())
        entry = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "makeHWAcc"
        )
        calls = [
            node.value.func.id
            for node in entry.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ]
        self.assertLess(
            calls.index("_verify_expected_model"), calls.index("_build_clusters")
        )

    def test_factory_cannot_use_tampered_snapshot_as_construction_authority(self):
        generation = self.complete()
        fresh = native_config.normalize_configuration(
            self.config, self.workspace, base_address=0x10020000
        )
        path = Path(generation["model"]["path"])
        payload = fresh.to_dict()
        payload["base_address"] += 64
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "semantic hash differs"):
            self.factory._verify_expected_model(
                fresh,
                self.workspace,
                path,
                generation["model_sha256"],
                generation["layout_sha256"],
            )
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        edited_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Fresh normalized configuration"):
            self.factory._verify_expected_model(
                fresh, self.workspace, path, edited_hash, generation["layout_sha256"]
            )

    def test_factory_rejects_duplicate_snapshot_json_and_partial_bindings(self):
        generation = self.complete()
        fresh = native_config.normalize_configuration(
            self.config, self.workspace, base_address=0x10020000
        )
        path = Path(generation["model"]["path"])
        original = path.read_text()
        path.write_text(
            original.replace(
                '"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1
            )
        )
        with self.assertRaisesRegex(ValueError, "Duplicate native model"):
            self.factory._verify_expected_model(
                fresh,
                self.workspace,
                path,
                generation["model_sha256"],
                generation["layout_sha256"],
            )
        path.write_text(original)
        with self.assertRaisesRegex(ValueError, "requires path"):
            self.factory._verify_expected_model(
                fresh, self.workspace, path, None, generation["layout_sha256"]
            )

    def capture_schema_fixture(self, generation):
        # Synthetic receipt fixture tests the post-run witness parser only.
        # It is explicitly not evidence that a simulator executed.
        simulator = self.workspace / "synthetic-capture-fixture"
        simulator.mkdir()
        fresh = native_config.normalize_configuration(
            self.config, self.workspace, base_address=0x10020000
        )
        snapshot = Path(generation["model"]["path"])
        emitted = simulator / "native_configuration.json"
        emitted.write_bytes(snapshot.read_bytes())
        binding = self.factory._verify_expected_model(
            fresh,
            self.workspace,
            snapshot,
            generation["model_sha256"],
            generation["layout_sha256"],
        )
        source_paths = {
            "factory": self.workspace / "configs/SALAM/native_factory.py",
            "hardware_adapter": self.workspace / "configs/SALAM/HWAccConfig.py",
            "normalizer": self.workspace / "workbench/salam_workbench/native_config.py",
        }
        receipt = {
            "generation_binding": binding,
            "model_sha256": generation["model_sha256"],
            "model_file_sha256": hashlib.sha256(emitted.read_bytes()).hexdigest(),
            "source_files": {
                name: {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for name, path in source_paths.items()
            },
        }
        path = simulator / "native_factory.json"
        path.write_text(json.dumps(receipt))
        return simulator, path, receipt

    def test_captured_source_identity_roles_cannot_be_omitted_or_rebound(self):
        generation = self.complete()
        simulator, path, receipt = self.capture_schema_fixture(generation)
        witness = native_generation.witness_factory_binding(
            self.workspace, generation, simulator
        )
        self.assertEqual(witness["state"], "passed")
        for changed in (
            {},
            {"factory": receipt["source_files"]["factory"]},
            dict(
                receipt["source_files"],
                normalizer=receipt["source_files"]["hardware_adapter"],
            ),
        ):
            value = dict(receipt, source_files=changed)
            path.write_text(json.dumps(value))
            with self.subTest(changed=list(changed)), self.assertRaises(ValueError):
                native_generation.witness_factory_binding(
                    self.workspace, generation, simulator
                )

    def test_captured_model_bytes_must_equal_prepared_snapshot(self):
        generation = self.complete()
        simulator, path, receipt = self.capture_schema_fixture(generation)
        emitted = simulator / "native_configuration.json"
        emitted.write_bytes(emitted.read_bytes() + b"\\n")
        receipt["model_file_sha256"] = hashlib.sha256(emitted.read_bytes()).hexdigest()
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "Constructed native model differs"):
            native_generation.witness_factory_binding(
                self.workspace, generation, simulator
            )

    def test_snapshot_symbolic_link_is_not_accepted(self):
        generation = self.complete()
        fresh = native_config.normalize_configuration(
            self.config, self.workspace, base_address=0x10020000
        )
        link = self.generated / "linked-snapshot.json"
        link.symlink_to(Path(generation["model"]["path"]))
        with self.assertRaisesRegex(ValueError, "regular contained path"):
            self.factory._verify_expected_model(
                fresh,
                self.workspace,
                link,
                generation["model_sha256"],
                generation["layout_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
