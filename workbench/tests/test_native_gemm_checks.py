# SPDX-License-Identifier: BSD-3-Clause
"""Failure controls for independent saved GEMM evidence comparisons."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_gemm_check", ROOT / "workbench/scripts/verify_native_gemm.py"
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
NUMPY, STATS, FU, _ = CHECK._load_helpers()


def fixture(seed=1):
    value = {
        "schema_version": 1,
        "benchmark": "gemm",
        "dataset": "seeded",
        "seed": seed,
        "shape": {"rows": 8, "inner": 8, "cols": 8},
        "inputs": {
            "a": [int(row == col) for row in range(8) for col in range(8)],
            "b": list(range(seed, seed + 64)),
        },
        "output_kind": "int32",
        "output_count": 64,
    }
    value["fixture_sha256"] = NUMPY.fixture_digest(value)
    return value


def raw_frame(value, corrupt=False):
    """The identity matrix produces B directly, independently of NumPy dot."""
    words = list(value["inputs"]["b"])
    if corrupt:
        words[0] ^= 1
    suffix = "v1 gemm {} 64 int32".format(value["fixture_sha256"])
    lines = ["SALAM_RESULT_BEGIN " + suffix]
    lines += [
        "SALAM_RESULT {} {:08x}".format(index, word & 0xFFFFFFFF)
        for index, word in enumerate(words)
    ]
    lines += ["SALAM_RESULT_END " + suffix]
    return ("\n".join(lines) + "\n").encode("ascii")


class NumericalEvidenceControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.first = fixture()
        self.second = fixture(29)
        self.paths = []
        for index, value in enumerate((self.first, self.second), 1):
            path = self.root / ("fixture-" + str(index) + ".json")
            path.write_text(json.dumps(value))
            self.paths.append(path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_two_distinct_identity_products_pass_all_128_outputs(self):
        data = raw_frame(self.first) + raw_frame(self.second)
        results = CHECK.verify_numerical(self.paths, data, NUMPY)
        self.assertEqual([item["state"] for item in results], ["passed", "passed"])
        self.assertEqual(sum(item["compared_count"] for item in results), 128)
        self.assertNotEqual(
            results[0]["observed_bits_sha256"], results[1]["observed_bits_sha256"]
        )

    def test_green_guest_marker_does_not_hide_corrupted_value(self):
        data = b"Check Passed\n" + raw_frame(self.first, corrupt=True)
        result = CHECK.verify_numerical(self.paths[:1], data, NUMPY)[0]
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["mismatch_count"], 1)
        self.assertEqual(result["first_mismatches"][0]["index"], 0)

    def test_missing_or_extra_complete_frame_rejected(self):
        with self.assertRaisesRegex(ValueError, "frame count"):
            CHECK.verify_numerical(self.paths, raw_frame(self.first), NUMPY)
        with self.assertRaisesRegex(ValueError, "frame count"):
            CHECK.verify_numerical(self.paths[:1], raw_frame(self.first) * 2, NUMPY)

    def test_stale_fixture_or_wrong_invocation_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "bind to this fixture"):
            CHECK.verify_numerical(
                self.paths, raw_frame(self.second) + raw_frame(self.first), NUMPY
            )

    def test_repeated_fixture_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct fixture"):
            CHECK.verify_numerical(self.paths[:1] * 2, raw_frame(self.first) * 2, NUMPY)

    def test_nested_incomplete_and_reordered_rows_rejected(self):
        raw = raw_frame(self.first)
        rows = raw.splitlines(keepends=True)
        for changed in (
            b"SALAM_RESULT_BEGIN bad\n" + raw,
            raw.rsplit(b"SALAM_RESULT_END", 1)[0],
            b"".join(rows[:1] + [rows[2], rows[1]] + rows[3:]),
        ):
            with self.subTest(changed=changed[:40]):
                with self.assertRaises(ValueError):
                    CHECK.verify_numerical(self.paths[:1], changed, NUMPY)

    def test_duplicate_fixture_json_field_rejected(self):
        value = self.first
        malformed = json.dumps(value).replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1'
        )
        self.paths[0].write_text(malformed)
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            CHECK.verify_numerical(self.paths[:1], raw_frame(value), NUMPY)


class EffectiveConfigurationControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.left = self.root / "retained.ini"
        self.right = self.root / "direct.ini"
        self.content = (
            "[root]\ntype=Root\nchildren=system\n"
            "[system]\ntype=System\nchildren=clk_domain gemm_clstr\n"
            "[system.gemm_clstr.gemm]\ntype=CommInterface\npio_size=1\n"
            "local=system.gemm_clstr.local_bus.cpu_side_ports[0]\n"
            "[system.gemm_clstr.gemm.clk_domain]\nclock=10000\n"
            "[system.gemm_clstr.gemm.hw_interface.functional_units.integer_multiplier]\n"
            "limit=0\n"
        )
        self.left.write_text(self.content)
        self.right.write_text(self.content)

    def tearDown(self):
        self.temporary.cleanup()

    def compare(self):
        return CHECK.compare_effective_configs(self.left, self.right)

    def test_same_run_cannot_be_claimed_as_a_differential(self):
        report = CHECK.compare_runs(self.root, self.root, [], expected_period_ns=10)
        self.assertEqual(report["state"], "failed")
        self.assertIn("distinct runs", report["issues"][0])

    def test_identical_configuration_passes(self):
        self.assertEqual(self.compare()["state"], "passed")

    def test_effective_fu_and_clock_changes_cannot_be_hidden(self):
        for old, new in (("limit=0", "limit=1"), ("clock=10000", "clock=3000")):
            self.right.write_text(self.content.replace(old, new))
            with self.subTest(new=new):
                result = self.compare()
                self.assertEqual(result["state"], "failed")
                self.assertEqual(result["difference_count"], 1)

    def test_children_order_is_normalized_but_port_connections_are_not(self):
        self.right.write_text(
            self.content.replace(
                "children=clk_domain gemm_clstr", "children=gemm_clstr clk_domain"
            )
        )
        result = self.compare()
        self.assertEqual(result["state"], "passed")
        self.assertEqual(len(result["equivalent_child_orderings"]), 1)
        self.right.write_text(
            self.content.replace("cpu_side_ports[0]", "cpu_side_ports[1]")
        )
        self.assertEqual(self.compare()["state"], "failed")

    def test_input_paths_require_identical_file_bytes(self):
        left_input, right_input = self.root / "left.ll", self.root / "right.ll"
        left_input.write_bytes(b"; same LLVM input\n")
        right_input.write_bytes(left_input.read_bytes())
        self.left.write_text(self.content + "in_file=" + str(left_input) + "\n")
        self.right.write_text(self.content + "in_file=" + str(right_input) + "\n")
        result = self.compare()
        self.assertEqual(result["state"], "passed")
        self.assertEqual(len(result["equivalent_file_identities"]), 1)
        right_input.write_bytes(b"; changed LLVM input\n")
        self.assertEqual(self.compare()["state"], "failed")

    def test_missing_section_and_extra_parameter_are_visible(self):
        self.right.write_text(self.content + "[unexpected]\ntype=SimObject\n")
        self.assertEqual(self.compare()["difference_count"], 1)
        self.right.write_text(self.content + "unexpected_knob=42\n")
        self.assertEqual(self.compare()["difference_count"], 1)

    def test_duplicate_effective_parameter_rejected(self):
        self.right.write_text(self.content + "limit=2\n")
        with self.assertRaises(Exception):
            self.compare()


if __name__ == "__main__":
    unittest.main()
