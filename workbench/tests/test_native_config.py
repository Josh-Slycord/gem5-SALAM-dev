# SPDX-License-Identifier: BSD-3-Clause
"""Strict configuration tests; no simulator execution is implied."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from salam_workbench.native_config import (
    DEFAULT_BASE_ADDRESS,
    ConfigurationError,
    normalize_configuration,
)

REPO = Path(__file__).resolve().parents[2]
ABI_FILES = (
    "configs/SALAM/HWAccConfig.py",
    "src/hwacc/FunctionalUnits.py",
    "src/hwacc/InstConfig.py",
    "src/hwacc/CycleCounts.py",
    "src/hwacc/CommInterface.py",
    "src/hwacc/NoncoherentDma.py",
)
GEMM_CONFIG = "benchmarks/sys_validation/gemm/config.yml"


class NativeConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in ABI_FILES + (GEMM_CONFIG,):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, destination)
        self.config = self.root / GEMM_CONFIG
        self.original = self.config.read_text()
        for name in ("top", "gemm"):
            target = self.config.parent / "hw" / (name + ".ll")
            target.parent.mkdir(exist_ok=True)
            target.write_text(
                "; Synthetic parser fixture, not a numerical workload.\n"
                "define void @{}() {{ ret void }}\n".format(name)
            )

    def normalize(self, text=None, **kwargs):
        if text is not None:
            self.config.write_text(text)
        return normalize_configuration(self.config, self.root, **kwargs)

    def reject(self, text, code, **kwargs):
        with self.assertRaises(ConfigurationError) as caught:
            self.normalize(text, **kwargs)
        error = caught.exception
        self.assertEqual(error.code, code, str(error))
        self.assertEqual(error.source, str(self.config))
        self.assertGreaterEqual(error.line, 1)
        self.assertIn(str(self.config), str(error))
        return error

    def test_full_gemm_retains_exact_allocator_and_defaults(self):
        model = self.normalize()
        document = model.to_dict()
        cluster = document["clusters"][0]
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(cluster["name"], "gemm_clstr")
        self.assertEqual(cluster["base_address"], DEFAULT_BASE_ADDRESS)
        self.assertEqual(cluster["top_address"], 0x10038180)
        dma = cluster["dmas"][0]
        self.assertEqual(dma["pio_addr"], 0x10020000)
        self.assertEqual(dma["pio_size"], 21)
        self.assertEqual(dma["interrupt_num"], 95)
        top, gemm = cluster["accelerators"]
        self.assertEqual(
            (top["name"], top["pio_addr"], top["pio_size"]),
            ("top", 0x10020040, 64),
        )
        self.assertEqual(
            (gemm["name"], gemm["pio_addr"], gemm["pio_size"]),
            ("gemm", 0x10020080, 64),
        )
        self.assertEqual(gemm["interrupt_num"], -1)
        self.assertEqual(len(gemm["hardware"]["instructions"]), 49)
        self.assertEqual(gemm["hardware"]["instructions"]["add"]["runtime_cycles"], 0)
        first = gemm["memories"][0]
        self.assertEqual(first["address"], 0x100200C0)
        self.assertEqual(first["range_end"], 0x100280C0)
        self.assertEqual(gemm["memories"][1]["address"], 0x10028100)
        self.assertEqual(first["connections"], [{"accelerator": "gemm", "ports": 2}])
        self.assertFalse(first["ready_mode"])
        self.assertTrue(first["reset_on_read"])
        self.assertFalse(first["read_on_invalid"])
        self.assertTrue(first["write_on_valid"])

    def test_aligned_mmio_keeps_retained_extra_cache_line(self):
        model = self.normalize(
            self.original.replace("PIOSize: 25", "PIOSize: 64")
        ).to_dict()
        top, gemm = model["clusters"][0]["accelerators"]
        self.assertEqual(top["pio_size"], 128)
        self.assertEqual(gemm["pio_addr"], 0x100200C0)

    def test_dma_omitted_irq_has_native_default_200(self):
        model = self.normalize(
            self.original.replace("      InterruptNum: 95\n", "")
        ).to_dict()
        self.assertEqual(model["clusters"][0]["dmas"][0]["interrupt_num"], 200)
        record = next(
            p
            for p in model["provenance"]
            if p["field"] == "clusters[0].dmas[0].interrupt_num"
        )
        self.assertEqual(record["origin"], "default")
        self.assertEqual(record["value"], 200)

    def test_deterministic_detached_model_and_no_input_writes(self):
        before = {
            p.relative_to(self.root)
            .as_posix(): hashlib.sha256(p.read_bytes())
            .hexdigest()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        first = self.normalize()
        second = self.normalize()
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.sha256, second.sha256)
        detached = first.to_dict()
        detached["clusters"][0]["name"] = "changed"
        self.assertEqual(first.to_dict()["clusters"][0]["name"], "gemm_clstr")
        self.assertEqual(json.loads(first.to_json(indent=None))["schema_version"], 1)
        after = {
            p.relative_to(self.root)
            .as_posix(): hashlib.sha256(p.read_bytes())
            .hexdigest()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_source_locations_and_all_input_dependency_hashes(self):
        model = self.normalize().to_dict()
        self.assertEqual(len(model["dependencies"]), 9)
        for dependency in model["dependencies"]:
            data = (self.root / dependency["path"]).read_bytes()
            self.assertEqual(dependency["sha256"], hashlib.sha256(data).hexdigest())
        record = next(
            p
            for p in model["provenance"]
            if p["field"] == "hw_config.gemm.instructions.add.runtime_cycles"
        )
        self.assertEqual(record["origin"], "explicit")
        self.assertEqual(record["consumer"], "active_scalar_latency")
        self.assertEqual(
            self.original.splitlines()[record["line"] - 1].strip(),
            "runtime_cycles: 0",
        )

    def test_zero_and_finite_fu_limits_preserve_neutral_instruction_caps(self):
        for limit in (0, 1, 2):
            text = self.original + (
                "    functional_units:\n"
                "      integer_multiplier:\n"
                "        limit: {}\n".format(limit)
            )
            model = self.normalize(text).to_dict()
            hw = model["clusters"][0]["accelerators"][1]["hardware"]
            self.assertEqual(
                hw["functional_units"]["integer_multiplier"]["limit"], limit
            )
            self.assertEqual(hw["instructions"]["mul"]["functional_unit_limit"], 0)

    def test_parser_does_not_import_configuration_python(self):
        source = self.root / ABI_FILES[0]
        source.write_text(
            "raise RuntimeError('This file must never execute')\n" + source.read_text()
        )
        self.assertEqual(
            self.normalize().to_dict()["clusters"][0]["name"], "gemm_clstr"
        )

    def test_duplicate_key_has_second_authored_line(self):
        text = self.original.replace(
            "      Type: NonCoherent",
            "      Type: NonCoherent\n      Type: NonCoherent",
        )
        error = self.reject(text, "duplicate_key")
        self.assertEqual(text.splitlines()[error.line - 1].strip(), "Type: NonCoherent")
        self.assertIn("first occurrence is line", str(error))

    def test_repeated_field_across_accelerator_list_is_rejected(self):
        text = self.original.replace(
            "    - Var:\n", "    - Debug: false\n    - Var:\n", 1
        )
        self.reject(text, "duplicate_field")

    def test_unknown_field_is_not_silently_discarded(self):
        text = self.original.replace(
            "      Type: NonCoherent",
            "      Type: NonCoherent\n      ReadyMode: true",
        )
        error = self.reject(text, "unknown_field")
        self.assertEqual(text.splitlines()[error.line - 1].strip(), "ReadyMode: true")

    def test_unknown_instruction_and_fu_id_are_rejected(self):
        self.reject(
            self.original.replace("      add:", "      invented:", 1),
            "unknown_instructions",
        )
        self.reject(
            self.original.replace(
                "        functional_unit: 1", "        functional_unit: 999", 1
            ),
            "unknown_fu_id",
        )

    def test_nonzero_instruction_limit_is_preinstantiation_error(self):
        error = self.reject(
            self.original.replace(
                "functional_unit_limit: 0", "functional_unit_limit: 1", 1
            ),
            "unsupported_instruction_cap",
        )
        self.assertIn("zero is neutral", error.message)

    def test_opcode_mapping_cannot_change_typed_llvm_abi(self):
        self.reject(
            self.original.replace("opcode_num: 13", "opcode_num: 14", 1),
            "unsupported_opcode_remap",
        )

    def test_load_store_latency_does_not_override_memory_system(self):
        self.reject(
            self.original.replace(
                "      load:\n"
                "        functional_unit: 0\n"
                "        functional_unit_limit: 0\n"
                "        opcode_num: 32\n"
                "        runtime_cycles: 0",
                "      load:\n"
                "        functional_unit: 0\n"
                "        functional_unit_limit: 0\n"
                "        opcode_num: 32\n"
                "        runtime_cycles: 1",
            ),
            "unsupported_memory_latency",
        )

    def test_booleans_are_not_unsigned_integers(self):
        self.reject(
            self.original.replace("        Ports: 2", "        Ports: true", 1),
            "invalid_uint32",
        )

    def test_device_types_and_external_config_paths_are_explicitly_unsupported(self):
        self.reject(
            self.original.replace("        Type: SPM", "        Type: Cache", 1),
            "unsupported_memory_type",
        )
        self.reject(
            self.original.replace("      Type: NonCoherent", "      Type: Stream"),
            "unsupported_dma_type",
        )
        self.reject(
            self.original.replace(
                "    - Name: Top",
                "    - Name: Top\n      ConfigPath: configs/external.yml",
            ),
            "unsupported_config_path",
        )

    def test_missing_pio_master_is_not_defaulted_to_a_fictitious_edge(self):
        self.reject(
            self.original.replace("      PIOMaster: LocalBus\n", "", 1),
            "missing_field",
        )

    def test_invalid_connection_is_rejected(self):
        self.reject(
            self.original.replace(
                "      PIOMaster: LocalBus", "      PIOMaster: missing", 1
            ),
            "unsupported_dma_master",
        )

    def test_case_insensitive_component_collision_is_rejected(self):
        self.reject(
            self.original.replace("      - Name: MATRIX2", "      - Name: matrix1", 1),
            "duplicate_name",
        )

    def test_paths_cannot_escape_or_use_ambiguous_separators(self):
        for value in (
            "../elsewhere.ll",
            "/tmp/elsewhere.ll",
            "benchmarks/../elsewhere.ll",
            "C:\\elsewhere.ll",
            "benchmarks//elsewhere.ll",
        ):
            self.reject(
                self.original.replace(
                    "benchmarks/sys_validation/gemm/hw/top.ll", value
                ),
                "unsafe_path",
            )

    def test_symlink_to_outside_file_is_not_read(self):
        external = Path(self.temporary.name).parent / (self.root.name + "-outside.ll")
        external.write_text("; fixture\n")
        self.addCleanup(external.unlink)
        target = self.root / "escape.ll"
        target.symlink_to(external)
        self.reject(
            self.original.replace(
                "benchmarks/sys_validation/gemm/hw/top.ll", "escape.ll"
            ),
            "unsafe_path",
        )

    def test_multiple_documents_and_aliases_are_rejected(self):
        self.reject(self.original + "\n---\nacc_cluster: []\n", "unsupported_documents")
        self.reject(
            self.original.replace("acc_cluster:\n", "acc_cluster: &cluster\n", 1)
            + "\nalias: *cluster\n",
            "yaml_alias",
        )

    def test_base_address_bounds_are_checked_before_instantiation(self):
        for address in (True, 0, 0x10020001, 0x14000000):
            with self.assertRaises(ConfigurationError) as caught:
                self.normalize(base_address=address)
            self.assertEqual(caught.exception.code, "invalid_base_address")

    def test_model_changes_when_requested_cycles_change(self):
        first = self.normalize()
        changed = self.original.replace(
            "      mul:\n"
            "        functional_unit: 2\n"
            "        functional_unit_limit: 0\n"
            "        opcode_num: 17\n"
            "        runtime_cycles: 1",
            "      mul:\n"
            "        functional_unit: 2\n"
            "        functional_unit_limit: 0\n"
            "        opcode_num: 17\n"
            "        runtime_cycles: 3",
        )
        self.assertNotEqual(changed, self.original)
        second = self.normalize(changed)
        self.assertNotEqual(first.sha256, second.sha256)
        self.assertEqual(
            second.to_dict()["clusters"][0]["accelerators"][1]["hardware"][
                "instructions"
            ]["mul"]["runtime_cycles"],
            3,
        )

    def test_finite_fu_on_special_path_is_rejected_before_instantiation(self):
        changed = self.original.replace(
            "      br:\n        functional_unit: 0",
            "      br:\n        functional_unit: 1",
        ) + ("    functional_units:\n" "      integer_adder:\n" "        limit: 1\n")
        self.reject(changed, "unsupported_special_fu")

    def test_unknown_pipeline_controls_are_not_silently_accepted(self):
        self.reject(
            self.original
            + (
                "    functional_units:\n"
                "      integer_multiplier:\n"
                "        fu_pipelined: true\n"
            ),
            "unknown_field",
        )

    def test_provenance_distinguishes_resolved_values_and_metadata(self):
        model = self.normalize(
            self.original
            + (
                "    functional_units:\n"
                "      integer_multiplier:\n"
                "        cycles: 3\n"
                "        limit: 0\n"
            )
        ).to_dict()
        provenance = {p["field"]: p for p in model["provenance"]}
        top = provenance["clusters[0].accelerators[0].name"]
        self.assertEqual(top["authored_value"], "Top")
        self.assertEqual(top["value"], "top")
        masters = provenance["clusters[0].dmas[0].pio_masters"]
        self.assertEqual(masters["authored_value"], "LocalBus")
        self.assertEqual(masters["value"], ["LocalBus"])
        self.assertEqual(
            provenance["hw_config.gemm.functional_units.integer_multiplier.cycles"][
                "consumer"
            ],
            "stored_metadata",
        )
        self.assertEqual(
            provenance["hw_config.gemm.functional_units.integer_multiplier.limit"][
                "consumer"
            ],
            "unlimited_fu_capacity",
        )
        self.assertEqual(
            provenance["hw_config.gemm.instructions.addrspacecast.runtime_cycles"][
                "consumer"
            ],
            "stored_without_current_dispatch",
        )
        default = model["typed_abi"]["functional_units"]["integer_multiplier"][
            "parameters"
        ]["limit"]
        self.assertEqual(default["origin"], "typed_default")
        self.assertEqual(default["source"], "src/hwacc/FunctionalUnits.py")

    def test_ir_content_is_a_model_dependency(self):
        first = self.normalize()
        ir = self.config.parent / "hw/gemm.ll"
        ir.write_text(ir.read_text() + "; a changed dependency\n")
        self.assertNotEqual(first.sha256, self.normalize().sha256)

    def test_unknown_spm_peer_points_to_its_authored_connection(self):
        text = self.original.replace(
            "        Ports: 2",
            "        Ports: 2\n        Connections: missing:1",
            1,
        )
        error = self.reject(text, "unknown_connection")
        self.assertEqual(
            text.splitlines()[error.line - 1].strip(),
            "Connections: missing:1",
        )

    def test_derived_address_range_overflow_is_rejected(self):
        self.reject(
            self.original.replace("Size: 32768", "Size: 4294967295", 1),
            "address_range_exceeded",
        )

    def test_simobject_protocol_names_are_reserved(self):
        self.reject(
            self.original.replace("    - Name: Top", "    - Name: path", 1),
            "invalid_name",
        )

    def test_comm_irq_respects_signed_native_param_bounds(self):
        for value in (-1, 0, 2147483647):
            model = self.normalize(
                self.original.replace(
                    "      InterruptNum: 68",
                    "      InterruptNum: {}".format(value),
                )
            ).to_dict()
            self.assertEqual(
                model["clusters"][0]["accelerators"][0]["interrupt_num"], value
            )
        for value in (-2, 2147483648, 4294967295):
            with self.assertRaises(ConfigurationError):
                self.normalize(
                    self.original.replace(
                        "      InterruptNum: 68",
                        "      InterruptNum: {}".format(value),
                    )
                )

    def test_scalar_pio_rejects_multiple_masters(self):
        text = self.original.replace(
            "      LocalSlaves: LocalBus",
            "      LocalSlaves: LocalBus",
        ).replace(
            "      PIOMaster: LocalBus\n      # Local to PIO",
            "      PIOMaster: LocalBus,gemm\n      # Local to PIO",
            1,
        )
        self.assertNotEqual(text, self.original)
        self.reject(text, "unsupported_pio_fan_in")

    def test_scalar_hardware_error_retains_its_yaml_source_line(self):
        text = self.original.split("hw_config:", 1)[0] + (
            "hw_config:\n  top:\n  gemm: false\n"
        )
        error = self.reject(text, "wrong_type")
        self.assertEqual(error.key_path, "hw_config.gemm")
        self.assertEqual(text.splitlines()[error.line - 1].strip(), "gemm: false")

    def test_named_pio_networks_are_explicitly_outside_first_slice(self):
        self.reject(
            self.original.replace(
                "      LocalSlaves: LocalBus", "      LocalSlaves: gemm", 1
            ),
            "unsupported_local_peer",
        )
        text = self.original.replace(
            "      PIOMaster: LocalBus\n      # Local to PIO",
            "      PIOMaster: Top\n      # Local to PIO",
            1,
        )
        self.assertNotEqual(text, self.original)
        self.reject(text, "unsupported_pio_master")

    def future_ir_config(self):
        return self.original.replace("/hw/", "/hw/future/")

    def test_default_mode_still_requires_ir_before_instantiation(self):
        self.reject(self.future_ir_config(), "missing_dependency")
        self.reject(self.future_ir_config(), "missing_dependency", require_ir=True)

    def test_preparation_records_unbuilt_ir_without_hashes_or_writes(self):
        self.config.write_text(self.future_ir_config())
        before = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        model = self.normalize(require_ir=False).to_dict()
        unresolved = [d for d in model["dependencies"] if d["kind"] == "llvm_ir"]
        self.assertEqual(len(unresolved), 2)
        self.assertEqual(
            {d["path"] for d in unresolved},
            {
                "benchmarks/sys_validation/gemm/hw/future/top.ll",
                "benchmarks/sys_validation/gemm/hw/future/gemm.ll",
            },
        )
        for dependency in unresolved:
            self.assertEqual(dependency["state"], "unbuilt")
            self.assertNotIn("sha256", dependency)
            self.assertNotIn("bytes", dependency)
        after = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        self.assertFalse((self.config.parent / "hw/future").exists())

    def test_preparation_and_finished_ir_share_layout_not_full_identity(self):
        self.config.write_text(self.future_ir_config())
        prepared = self.normalize(require_ir=False)
        directory = self.config.parent / "hw/future"
        directory.mkdir()
        for name in ("top", "gemm"):
            (directory / (name + ".ll")).write_text(
                "define void @{}() {{ ret void }}\n".format(name)
            )
        finished = self.normalize()
        self.assertEqual(prepared.layout_dict(), finished.layout_dict())
        self.assertEqual(prepared.layout_sha256, finished.layout_sha256)
        self.assertEqual(prepared.layout_json(), finished.layout_json())
        self.assertNotEqual(prepared.sha256, finished.sha256)
        for dependency in finished.to_dict()["dependencies"]:
            if dependency["kind"] == "llvm_ir":
                self.assertNotIn("state", dependency)
                self.assertEqual(
                    dependency["sha256"],
                    hashlib.sha256(
                        (self.root / dependency["path"]).read_bytes()
                    ).hexdigest(),
                )

    def test_preparation_of_built_ir_keeps_existing_strict_model_identity(self):
        strict = self.normalize()
        prepared = self.normalize(require_ir=False)
        self.assertEqual(strict.to_json(), prepared.to_json())
        self.assertEqual(strict.sha256, prepared.sha256)
        for dependency in prepared.to_dict()["dependencies"]:
            self.assertIn("sha256", dependency)
            self.assertIn("bytes", dependency)
            self.assertNotIn("state", dependency)

    def test_layout_excludes_changed_ir_bytes_but_full_identity_detects_them(self):
        first = self.normalize()
        ir = self.config.parent / "hw/gemm.ll"
        ir.write_text(ir.read_text() + "; changed build output\n")
        second = self.normalize()
        self.assertEqual(first.layout_sha256, second.layout_sha256)
        self.assertNotEqual(first.sha256, second.sha256)

    def test_layout_retains_configuration_hardware_and_type_identity(self):
        original = self.normalize(require_ir=False)
        moved = self.normalize(
            self.original.replace("PIOSize: 25", "PIOSize: 64"),
            require_ir=False,
        )
        self.assertNotEqual(original.layout_sha256, moved.layout_sha256)
        hardware = self.normalize(
            self.original
            + (
                "    functional_units:\n"
                "      integer_multiplier:\n"
                "        limit: 1\n"
            ),
            require_ir=False,
        )
        self.assertNotEqual(original.layout_sha256, hardware.layout_sha256)
        self.config.write_text(self.original)
        declaration = self.root / "src/hwacc/FunctionalUnits.py"
        declaration.write_text(
            "# An explicit declaration-source change.\n" + declaration.read_text()
        )
        changed_type = self.normalize(require_ir=False)
        self.assertNotEqual(original.layout_sha256, changed_type.layout_sha256)

    def test_layout_retains_normalized_paths_and_is_detached(self):
        original = self.normalize()
        redirected = self.normalize(self.future_ir_config(), require_ir=False)
        self.assertNotEqual(original.layout_sha256, redirected.layout_sha256)
        projection = redirected.layout_dict()
        projection["clusters"][0]["name"] = "modified"
        self.assertEqual(redirected.layout_dict()["clusters"][0]["name"], "gemm_clstr")
        self.assertEqual(
            json.loads(redirected.layout_json(indent=None)),
            redirected.layout_dict(),
        )
        self.assertEqual(
            redirected.layout_dict()["source"],
            redirected.to_dict()["source"],
        )
        self.assertEqual(
            redirected.layout_dict()["typed_abi"],
            redirected.to_dict()["typed_abi"],
        )

    def test_preparation_still_rejects_unsafe_future_ir_paths(self):
        for value in (
            "../future.ll",
            "/tmp/future.ll",
            "benchmarks/../future.ll",
        ):
            self.reject(
                self.original.replace(
                    "benchmarks/sys_validation/gemm/hw/top.ll", value
                ),
                "unsafe_path",
                require_ir=False,
            )
        link = self.config.parent / "hw/future_link"
        link.symlink_to(
            self.root.parent / (self.root.name + "-absent"),
            target_is_directory=True,
        )
        self.reject(
            self.original.replace("hw/top.ll", "hw/future_link/top.ll"),
            "unsafe_path",
            require_ir=False,
        )

    def test_preparation_rejects_non_file_targets_and_blocked_ancestors(self):
        directory_target = self.config.parent / "hw/directory.ll"
        directory_target.mkdir()
        self.reject(
            self.original.replace("hw/top.ll", "hw/directory.ll"),
            "missing_dependency",
            require_ir=False,
        )
        blocker = self.config.parent / "hw/not_a_directory"
        blocker.write_text("A regular file cannot be a future IR directory.\n")
        self.reject(
            self.original.replace("hw/top.ll", "hw/not_a_directory/top.ll"),
            "unreadable_dependency",
            require_ir=False,
        )

    def test_preparation_does_not_bypass_configuration_validation(self):
        self.reject(
            self.future_ir_config().replace(
                "functional_unit_limit: 0", "functional_unit_limit: 2", 1
            ),
            "unsupported_instruction_cap",
            require_ir=False,
        )
        for invalid in (None, "false", 0, 1):
            with self.assertRaises(ConfigurationError) as caught:
                self.normalize(require_ir=invalid)
            self.assertEqual(caught.exception.code, "invalid_ir_requirement")


if __name__ == "__main__":
    unittest.main()
