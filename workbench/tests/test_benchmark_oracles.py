"""Host-side oracle challenges; these tests do not execute a simulator."""
import copy
import math
import unittest

from salam_workbench.benchmark_oracles import (
    assess_output,
    encode_output,
    fixture_sha256,
    make_fixture,
    reference_outputs,
    render_output,
    validate_fixture,
)


class BenchmarkOracleTests(unittest.TestCase):
    def test_deterministic_seeded_fixtures_and_distinct_inputs(self):
        for name in ("gemm", "fft", "stencil3d"):
            first = make_fixture(name, "seeded", 1)
            self.assertEqual(first, make_fixture(name, "seeded", 1))
            self.assertNotEqual(
                first["inputs"], make_fixture(name, "seeded", 2)["inputs"]
            )
            self.assertNotEqual(
                first["fixture_sha256"],
                make_fixture(name, "seeded", 2)["fixture_sha256"],
            )

    def test_all_dataset_definitions_validate(self):
        for name in ("gemm", "fft", "stencil3d"):
            for dataset in ("baseline", "seeded", "zeros", "boundary"):
                with self.subTest(name=name, dataset=dataset):
                    fixture = make_fixture(name, dataset)
                    self.assertIs(validate_fixture(fixture), fixture)

    def test_input_tampering_is_rejected(self):
        fixture = make_fixture("gemm")
        fixture["inputs"]["a"][0] += 1
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_fixture(fixture)

    def test_invalid_identity_dimensions_counts_and_types(self):
        original = make_fixture("gemm")
        changes = (
            ("schema_version", True),
            ("seed", -1),
            ("seed", True),
            ("benchmark", "bfs"),
            ("output_count", 63),
            ("shape", {"rows": 16, "inner": 8, "cols": 8}),
        )
        for key, value in changes:
            fixture = copy.deepcopy(original)
            fixture[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    validate_fixture(fixture)

    def test_invalid_fft_twiddle_rejected_even_with_recomputed_digest(self):
        fixture = make_fixture("fft")
        fixture["inputs"]["real_twid"][0] = 0
        fixture["fixture_sha256"] = fixture_sha256(fixture)
        with self.assertRaisesRegex(ValueError, "twiddle"):
            validate_fixture(fixture)

    def test_gemm_overflow_contract(self):
        fixture = make_fixture("gemm")
        fixture["inputs"] = {"a": [32767] * 64, "b": [32767] * 64}
        fixture["fixture_sha256"] = fixture_sha256(fixture)
        with self.assertRaisesRegex(ValueError, "overflow"):
            validate_fixture(fixture)

    def test_gemm_identity_and_zero_outputs(self):
        identity = make_fixture("gemm", "boundary")
        self.assertEqual(reference_outputs(identity), identity["inputs"]["b"])
        self.assertEqual(reference_outputs(make_fixture("gemm", "zeros")), [0] * 64)

    def test_fft_impulse_and_frequency_order(self):
        impulse = make_fixture("fft", "baseline")
        self.assertEqual(reference_outputs(impulse), [[1.0, 0.0]] * 1024)
        fixture = make_fixture("fft", "zeros")
        frequency = 7
        fixture["inputs"]["real"] = [
            math.cos(2 * math.pi * frequency * n / 1024) for n in range(1024)
        ]
        fixture["inputs"]["imag"] = [
            math.sin(2 * math.pi * frequency * n / 1024) for n in range(1024)
        ]
        fixture["fixture_sha256"] = fixture_sha256(fixture)
        expected = reference_outputs(fixture)
        peak = int(format(frequency, "010b")[::-1], 2)
        self.assertAlmostEqual(expected[peak][0], 1024, places=6)
        self.assertLess(
            max(
                math.hypot(real, imag)
                for i, (real, imag) in enumerate(expected)
                if i != peak
            ),
            1e-6,
        )

    def test_stencil_coordinates_and_boundary_values(self):
        fixture = make_fixture("stencil3d", "baseline")
        result = reference_outputs(fixture)
        for z, y, x in ((0, 0, 0), (31, 5, 7), (2, 31, 6), (7, 6, 15)):
            index = x + 16 * (y + 32 * z)
            self.assertEqual(result[index], index)
        index = 5 + 16 * (8 + 32 * 10)
        self.assertEqual(result[index], 20 * index)

    def test_stencil_impulse_affects_exactly_six_neighbors(self):
        fixture = make_fixture("stencil3d", "zeros")
        index = 5 + 16 * (8 + 32 * 10)
        fixture["inputs"]["input"][index] = 7
        fixture["fixture_sha256"] = fixture_sha256(fixture)
        result = reference_outputs(fixture)
        self.assertEqual(result[index], 14)
        for offset in (-1, 1, -16, 16, -512, 512):
            self.assertEqual(result[index + offset], 21)
        self.assertEqual(sum(value != 0 for value in result), 7)

    def test_round_trip_all_output_types_and_log_noise(self):
        for name in ("gemm", "fft", "stencil3d"):
            fixture = make_fixture(name, "seeded", 3)
            observed = "Booting guest\n" + render_output(fixture) + "Check Passed\n"
            result = assess_output(observed, fixture)
            self.assertEqual(result["state"], "passed", result["issues"])
            self.assertEqual(result["compared_count"], fixture["output_count"])
            self.assertEqual(len(result["output_sha256"]), 64)

    def test_wrong_identity_and_wrong_kind_fail(self):
        fixture = make_fixture("gemm")
        text = render_output(fixture)
        self.assertEqual(
            assess_output(text.replace(fixture["fixture_sha256"], "0" * 64), fixture)[
                "state"
            ],
            "failed",
        )
        self.assertEqual(
            assess_output(text.replace("int32", "complex128"), fixture)["state"],
            "failed",
        )

    def test_single_wrong_value_fails_despite_guest_pass_marker(self):
        fixture = make_fixture("gemm")
        values = reference_outputs(fixture)
        values[17] += 1
        result = assess_output(
            render_output(fixture, values) + "Check Passed\n", fixture
        )
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["mismatch_count"], 1)
        self.assertEqual(result["compared_count"], 64)
        self.assertIsNotNone(result["output_sha256"])

    def test_nan_and_infinity_outputs_fail(self):
        fixture = make_fixture("fft", "baseline")
        values = reference_outputs(fixture)
        for value in (float("nan"), float("inf"), -float("inf")):
            changed = copy.deepcopy(values)
            changed[37][1] = value
            result = assess_output(render_output(fixture, changed), fixture)
            self.assertEqual(result["state"], "failed")
            self.assertIn("not finite", result["issues"][0])

    def test_duplicate_missing_extra_and_unordered_rows_fail(self):
        fixture = make_fixture("gemm")
        lines = render_output(fixture).splitlines()
        changes = (
            lines[:4] + [lines[3]] + lines[4:],
            lines[:4] + lines[5:],
            lines[:-1] + ["SALAM_RESULT 64 00000000"] + lines[-1:],
            lines[:3] + [lines[4], lines[3]] + lines[5:],
        )
        for changed in changes:
            with self.subTest(first=changed[3]):
                self.assertEqual(
                    assess_output("\n".join(changed), fixture)["state"], "failed"
                )

    def test_missing_footer_repeated_blocks_and_outside_rows_fail(self):
        fixture = make_fixture("gemm")
        text = render_output(fixture)
        changes = (
            "\n".join(text.splitlines()[:-1]),
            text + text,
            text + "SALAM_RESULT 0 00000000\n",
            "Check Passed\n",
        )
        for changed in changes:
            self.assertEqual(assess_output(changed, fixture)["state"], "failed")

    def test_float_tolerance_is_bounded(self):
        fixture = make_fixture("fft", "baseline")
        values = reference_outputs(fixture)
        values[0][0] += 0.5e-6
        self.assertEqual(
            assess_output(render_output(fixture, values), fixture)["state"], "passed"
        )
        values[0][0] += 2e-6
        self.assertEqual(
            assess_output(render_output(fixture, values), fixture)["state"], "failed"
        )

    def test_signed_integer_bits_and_invalid_payload(self):
        fixture = make_fixture("gemm", "boundary")
        self.assertEqual(encode_output(-1, "int32"), "ffffffff")
        text = render_output(fixture).replace("fffffff0", "xyz", 1)
        self.assertEqual(assess_output(text, fixture)["state"], "failed")


if __name__ == "__main__":
    unittest.main()
