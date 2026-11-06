# SPDX-License-Identifier: BSD-3-Clause
"""Native header layout parity and custom-source preservation checks."""

import copy
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench.native_codegen import (
    BEGIN,
    END,
    HeaderGenerationError,
    header_symbols,
    render_headers,
)
from salam_workbench.native_config import (
    NormalizedConfiguration,
    normalize_configuration,
)

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/sys_validation/gemm"


def changed_model(model, change):
    data = copy.deepcopy(model.to_dict())
    change(data)
    return NormalizedConfiguration(
        json.dumps(data, sort_keys=True, separators=(",", ":"))
    )


def integer_defines(text):
    result = {}
    for name, value in re.findall(
        r"^#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(0x[0-9a-fA-F]+)\s*$",
        text,
        re.MULTILINE,
    ):
        if name in result:
            raise AssertionError("Duplicate macro in independent header witness")
        result[name] = int(value, 16)
    return result


class NativeHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = normalize_configuration(
            BENCHMARK / "config.yml", ROOT, require_ir=False
        )
        cls.name = cls.model.to_dict()["clusters"][0]["authored_name"]
        cls.filename = cls.name + "_hw_defines.h"
        cls.retained = (BENCHMARK / cls.filename).read_text()

    def text(self, model=None, existing=None):
        return render_headers(self.model if model is None else model, existing)[
            self.filename
        ]

    def test_macros_match_retained_gemm_header_exactly(self):
        expected = integer_defines(self.retained)
        actual = header_symbols(self.model)[self.filename]
        self.assertEqual(actual, expected)
        self.assertEqual(integer_defines(self.text()), expected)
        self.assertEqual(actual["DMA_Flags"], 0x10020000)
        self.assertEqual(actual["DMA_RdAddr"], 0x10020001)
        self.assertEqual(actual["DMA_WrAddr"], 0x10020009)
        self.assertEqual(actual["DMA_CopyLen"], 0x10020011)
        self.assertEqual(actual["MATRIX3"], 0x10030140)

    def test_authored_filename_and_variable_case_are_preserved(self):
        def change(data):
            cluster = data["clusters"][0]
            cluster["name"] = "mixedcluster"
            cluster["authored_name"] = "MixedCluster"
            memory = cluster["accelerators"][1]["memories"][0]
            memory["name"] = "myarray"
            memory["authored_name"] = "myArray"

        model = changed_model(self.model, change)
        result = render_headers(model)
        self.assertEqual(list(result), ["MixedCluster_hw_defines.h"])
        self.assertIn("#define myArray 0x100200c0\n", next(iter(result.values())))
        self.assertNotIn("#define MYARRAY", next(iter(result.values())))

    def test_rendering_is_deterministic_and_idempotent(self):
        first = self.text()
        self.assertEqual(self.text(), first)
        self.assertEqual(self.text(existing={self.name: first}), first)

    def test_custom_prefix_suffix_and_region_position_are_preserved(self):
        prefix = "#ifndef CUSTOM_GUARD\r\n#define CUSTOM_GUARD\r\n// authored\r\n"
        suffix = "// authored footer\r\n#endif\r\n"
        existing = prefix + self.retained + suffix
        result = self.text(existing={self.name: existing})
        self.assertTrue(result.startswith(prefix + BEGIN + "\n"))
        self.assertTrue(result.endswith(END + "\n" + suffix))
        self.assertEqual(result.count(BEGIN), 1)
        self.assertEqual(result.count(END), 1)
        self.assertEqual(self.text(existing={self.name: result}), result)

    def test_unmarked_authored_text_receives_a_separate_generated_region(self):
        prefix = "#pragma once\n// authored without final newline"
        result = self.text(existing={self.name: prefix})
        self.assertTrue(result.startswith(prefix + "\n" + BEGIN + "\n"))

    def test_malformed_or_ambiguous_regions_fail_without_rewriting(self):
        malformed = [
            BEGIN + "\n",
            END + "\n",
            END + "\n" + BEGIN + "\n",
            self.retained + self.retained,
            BEGIN + "\n" + BEGIN + "\n" + END + "\n",
            "// BEGIN GENERATED CODE\n" + END + "\n",
            BEGIN + "\n" + END + " // trailing ambiguity\n",
        ]
        for text in malformed:
            with self.subTest(text=text):
                with self.assertRaises(HeaderGenerationError):
                    self.text(existing={self.name: text})

    def test_unexpected_existing_header_cannot_be_silently_dropped(self):
        with self.assertRaisesRegex(HeaderGenerationError, "Unexpected"):
            self.text(existing={"another_cluster": "// authored data\n"})

    def test_authored_macro_collision_is_rejected_even_with_equal_value(self):
        prefix = "#define GEMM 0x10020080\n"
        with self.assertRaisesRegex(HeaderGenerationError, "macro collision"):
            self.text(existing={self.name: prefix + self.retained})

    def test_comment_mentions_are_not_authored_macro_definitions(self):
        prefix = "/*\n#define GEMM 0x0\n*/\n// #define TOP 0\n"
        self.assertTrue(self.text(existing={self.name: prefix}).startswith(prefix))

    def test_comment_delimiters_in_strings_cannot_hide_authored_collisions(self):
        prefix = 'const char *marker = "/*";\n#define GEMM 0x10020080\n'
        with self.assertRaisesRegex(HeaderGenerationError, "macro collision"):
            self.text(existing={self.name: prefix + self.retained})

    def test_duplicate_generated_symbols_are_rejected(self):
        def change(data):
            memory = data["clusters"][0]["accelerators"][1]["memories"][0]
            memory["authored_name"] = "DMA_Flags"
            memory["name"] = "dma_flags"

        with self.assertRaisesRegex(HeaderGenerationError, "duplicate"):
            self.text(model=changed_model(self.model, change))

    def test_invalid_authored_macro_name_is_rejected(self):
        def change(data):
            memory = data["clusters"][0]["accelerators"][1]["memories"][0]
            memory["authored_name"] = "invalid-macro"

        with self.assertRaisesRegex(HeaderGenerationError, "C identifier"):
            self.text(model=changed_model(self.model, change))

    def test_unsupported_memory_and_multi_cluster_models_fail_explicitly(self):
        def change_memory(data):
            data["clusters"][0]["accelerators"][1]["memories"][0][
                "type"
            ] = "RegisterBank"

        def change_clusters(data):
            data["clusters"].append(copy.deepcopy(data["clusters"][0]))

        for change in (change_memory, change_clusters):
            with self.subTest(change=change.__name__):
                with self.assertRaises(HeaderGenerationError):
                    self.text(model=changed_model(self.model, change))

    def test_serialized_receipt_json_is_not_an_input_interface(self):
        with self.assertRaisesRegex(TypeError, "freshly normalized"):
            render_headers(self.model.to_dict())

    def test_ir_materialization_changes_full_identity_but_not_header_bytes(self):
        def change(data):
            count = 0
            for dependency in data["dependencies"]:
                if dependency.get("kind") == "llvm_ir":
                    count += 1
                    dependency["sha256"] = "a" * 64
                    dependency["bytes"] = 12345
                    dependency.pop("state", None)
            self.assertGreater(count, 0)

        after = changed_model(self.model, change)
        self.assertNotEqual(after.sha256, self.model.sha256)
        self.assertEqual(after.layout_sha256, self.model.layout_sha256)
        self.assertEqual(render_headers(after), render_headers(self.model))
        self.assertIn(self.model.layout_sha256, self.text())

    def test_rendering_reads_no_files_or_legacy_generator(self):
        with patch(
            "builtins.open", side_effect=AssertionError("Unexpected file access")
        ), patch.object(
            Path, "read_text", side_effect=AssertionError("Unexpected file access")
        ), patch.object(
            Path, "write_text", side_effect=AssertionError("Unexpected file write")
        ):
            output = self.text(existing={self.name: self.retained})
        self.assertEqual(integer_defines(output), integer_defines(self.retained))

    def test_source_provenance_cannot_inject_an_extra_comment_line(self):
        def change(data):
            data["source"]["path"] = "/fixture/\n#define INJECTED 1\n/config.yml"

        output = self.text(model=changed_model(self.model, change))
        self.assertNotIn("\n#define INJECTED", output)
        self.assertIn("// Source SHA-256: ", output)


if __name__ == "__main__":
    unittest.main()
