# SPDX-License-Identifier: BSD-3-Clause
"""Bounds, equivalence and plan-only controls for the generation study."""
import contextlib
import importlib.util
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "tested_native_generation_study",
    ROOT / "workbench/scripts/run_native_generation.py",
)
STUDY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = STUDY
SPEC.loader.exec_module(STUDY)


def elf32(
    payload=b"\x01\x02\x03\x04",
    *,
    debug=b"",
    entry=0x80000000,
    machine=40,
    flags=0x5000200,
    address=0x80000000,
    memory_bytes=16,
    segment_flags=5,
    offset=128,
):
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident,
        2,
        machine,
        1,
        entry,
        52,
        0,
        flags,
        52,
        32,
        1,
        0,
        0,
        0,
    )
    program = struct.pack(
        "<8I",
        1,
        offset,
        address,
        address,
        len(payload),
        memory_bytes,
        segment_flags,
        1,
    )
    return (
        header + program + bytes(offset - len(header) - len(program)) + payload + debug
    )


class LoadImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.left = self.root / "retained.elf"
        self.right = self.root / "native.elf"

    def test_debug_path_changes_do_not_change_loaded_image(self):
        self.left.write_bytes(elf32(debug=b"/legacy/workspace/main.cpp"))
        self.right.write_bytes(elf32(debug=b"/native/workspace/main.cpp"))
        report = STUDY.compare_load_images(self.left, self.right)
        self.assertEqual(report["state"], "passed")
        self.assertNotEqual(
            report["legacy"]["file_sha256"], report["native"]["file_sha256"]
        )
        self.assertEqual(report["legacy"]["segments"][0]["zero_fill_bytes"], 12)

    def test_file_offsets_may_differ_when_loaded_bytes_are_identical(self):
        self.left.write_bytes(elf32(offset=128))
        self.right.write_bytes(elf32(offset=256))
        self.assertEqual(
            STUDY.compare_load_images(self.left, self.right)["state"], "passed"
        )

    def test_loaded_payload_entry_flags_bss_and_addresses_are_not_ignored(self):
        self.left.write_bytes(elf32())
        changes = [
            {"payload": b"\xff\x02\x03\x04"},
            {"entry": 0x80000004},
            {"flags": 0x5000201},
            {"address": 0x80000040},
            {"memory_bytes": 32},
            {"segment_flags": 7},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.right.write_bytes(elf32(**change))
                self.assertEqual(
                    STUDY.compare_load_images(self.left, self.right)["state"],
                    "failed",
                )

    def test_wrong_class_endian_machine_and_short_header_rejected(self):
        variants = [
            b"not ELF",
            elf32(machine=3),
        ]
        for index, value in ((4, 2), (5, 2)):
            data = bytearray(elf32())
            data[index] = value
            variants.append(data)
        for data in variants:
            with self.subTest(data=bytes(data)[:20]):
                self.left.write_bytes(data)
                with self.assertRaises(ValueError):
                    STUDY.elf_load_image(self.left)

    def test_program_header_and_load_spans_are_bounded(self):
        variants = []
        for offset, value in (
            (28, 0xFFFFFFF0),  # e_phoff
            (44, 1025),  # e_phnum (16 bit)
            (68, 1024),  # p_filesz beyond file/memsz
            (72, 2),  # p_memsz smaller than p_filesz
            (60, 0xFFFFFFF8),  # vaddr + memsz overflow
            (80, 3),  # p_align is not a power of two
        ):
            data = bytearray(elf32())
            struct.pack_into("<H" if offset == 44 else "<I", data, offset, value)
            variants.append(data)
        for data in variants:
            self.left.write_bytes(data)
            with self.assertRaises(ValueError):
                STUDY.elf_load_image(self.left)

    def test_elf_without_a_load_segment_is_rejected(self):
        data = bytearray(elf32())
        struct.pack_into("<I", data, 52, 4)
        self.left.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "no PT_LOAD"):
            STUDY.elf_load_image(self.left)

    def test_bounded_reader_rejects_oversized_files_and_symlinks(self):
        self.left.write_bytes(elf32())
        with self.assertRaises(ValueError):
            STUDY.bounded_bytes(self.left, maximum=16)
        link = self.root / "link.elf"
        link.symlink_to(self.left)
        with self.assertRaises(OSError):
            STUDY.elf_load_image(link)


class MacroAndSelectionTests(unittest.TestCase):
    def test_complete_macro_map_preserves_names_and_integer_values(self):
        self.assertEqual(
            STUDY.parse_header_macros(
                "#define TOP 0x10020040\n#define myArray 123\n#define FN(x) x\n"
            ),
            {"TOP": 0x10020040, "myArray": 123},
        )

    def test_duplicate_macros_cannot_be_silently_overwritten(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            STUDY.parse_header_macros("#define TOP 1\n#define TOP 1\n")

    def test_default_matrix_has_eight_factor_cases_and_one_relocation(self):
        cases = STUDY.study_cases()
        self.assertEqual(len(cases), 9)
        self.assertEqual(len({case["name"] for case in cases}), 9)
        ordinary = [case for case in cases if case["base_address"] == 0x10020000]
        self.assertEqual(len(ordinary), 8)
        self.assertEqual(
            {
                (case["period_ns"], case["mul_limit"], case["mul_cycles"])
                for case in ordinary
            },
            {
                (period, limit, cycles)
                for period in (10, 3)
                for limit in (0, 1)
                for cycles in (1, 16)
            },
        )
        self.assertEqual(cases[-1]["base_address"], 0x10024000)

    def test_explicit_subset_and_relocation_only_remain_bounded(self):
        self.assertEqual(len(STUDY.study_cases([(3, 1, 16)])), 1)
        self.assertEqual(len(STUDY.study_cases(relocation_only=True)), 1)
        with self.assertRaises(ValueError):
            STUDY.study_cases([(7, 1, 16)])
        with self.assertRaises(ValueError):
            STUDY.study_cases([(3, 1, 16)], relocation_only=True)


class PlanAndRejectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_plan_mode_never_prepares_builds_or_launches(self):
        output = self.root / "plan"
        forbidden = AssertionError("Plan mode attempted execution")
        with patch.object(
            STUDY.retained, "prepare", side_effect=forbidden
        ), patch.object(STUDY.retained, "launch", side_effect=forbidden), patch.object(
            STUDY.retained, "verify_engine", side_effect=forbidden
        ), contextlib.redirect_stdout(
            io.StringIO()
        ):
            result = STUDY.main(
                [
                    "--engine",
                    str(self.root / "missing-engine"),
                    "--build-receipt",
                    str(self.root / "missing-receipt.json"),
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(result, 0)
        plan = json.loads((output / "plan.json").read_text())
        self.assertEqual(plan["state"], "planned")
        self.assertEqual(len(plan["cases"]), 9)
        self.assertFalse((output / "study.json").exists())

    def test_existing_output_directory_is_not_reused(self):
        with self.assertRaises(FileExistsError), contextlib.redirect_stdout(
            io.StringIO()
        ):
            STUDY.main(
                [
                    "--engine",
                    "/not-read",
                    "--build-receipt",
                    "/not-read.json",
                    "--output",
                    str(self.root),
                ]
            )

    def test_expected_failure_requires_real_process_and_exact_diagnostic(self):
        (self.root / "stderr.txt").write_text("specific rejection")
        record = {
            "state": "failed",
            "process_id": 123,
            "run_directory": str(self.root),
        }
        self.assertEqual(
            STUDY.rejection_witness(record, "specific rejection")["state"],
            "passed",
        )
        for change in (
            {"state": "passed"},
            {"process_id": None},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    STUDY.rejection_witness(
                        dict(record, **change), "specific rejection"
                    )
        with self.assertRaises(ValueError):
            STUDY.rejection_witness(record, "different failure")


if __name__ == "__main__":
    unittest.main()
