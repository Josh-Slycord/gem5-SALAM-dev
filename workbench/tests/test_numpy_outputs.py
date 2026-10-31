# SPDX-License-Identifier: BSD-3-Clause
"""Analytic controls for the separate NumPy checker, never simulator evidence."""
import copy
import importlib.util
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

# Load the standalone script directly; never import the workbench's oracle.
TOOL_PATH = Path(__file__).resolve().parents[1] / "scripts/verify_numpy_outputs.py"
SPEC = importlib.util.spec_from_file_location(
    "independent_numpy_outputs_tool", TOOL_PATH
)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def fixture(benchmark):
    shape, kind, count = verifier.CONTRACTS[benchmark]
    if benchmark == "gemm":
        inputs = {"a": [int(i // 8 == i % 8) for i in range(64)], "b": list(range(64))}
    elif benchmark == "fft":
        real = [0.0] * 1024
        real[0] = 1.0
        angles = -2 * np.pi * np.arange(512) / 1024
        inputs = {
            "real": real,
            "imag": [0.0] * 1024,
            "real_twid": np.cos(angles).tolist(),
            "imag_twid": np.sin(angles).tolist(),
        }
    else:
        inputs = {"input": [1] * 16384, "coefficients": [2, 3]}
    value = {
        "schema_version": 1,
        "benchmark": benchmark,
        "dataset": "boundary",
        "seed": 0,
        "shape": dict(shape),
        "inputs": inputs,
        "output_kind": kind,
        "output_count": count,
    }
    value["fixture_sha256"] = verifier.fixture_digest(value)
    return value


def wire(value, outputs):
    count, kind = value["output_count"], value["output_kind"]
    suffix = "v1 {} {} {} {}".format(
        value["benchmark"], value["fixture_sha256"], count, kind
    )
    lines = ["SALAM_RESULT_BEGIN " + suffix]
    for index, output in enumerate(outputs):
        data = (
            struct.pack(">i", output)
            if kind == "int32"
            else struct.pack(">dd", output.real, output.imag)
        )
        lines.append("SALAM_RESULT {} {}".format(index, data.hex()))
    lines.append("SALAM_RESULT_END " + suffix)
    return ("\n".join(lines) + "\n").encode("ascii")


class IndependentNumericalTests(unittest.TestCase):
    def test_small_matrix_product_has_manual_expected_values(self):
        result = verifier.numpy_gemm([1, 2, 3, 4], [5, 6, 7, 8], 2, 2, 2)
        np.testing.assert_array_equal(result, [19, 22, 43, 50])

    def test_four_sample_fft_checks_sign_scale_and_bit_reversal(self):
        result = verifier.numpy_fft([1, 2, 3, 4], [0, 0, 0, 0])
        # Natural forward DFT is [10, -2+2j, -2, -2-2j].
        expected = np.array([10, -2, -2 + 2j, -2 - 2j])
        np.testing.assert_allclose(result, expected, atol=1e-14, rtol=0)
        natural_order = np.array([10, -2 + 2j, -2, -2 - 2j])
        self.assertEqual(
            verifier.compare_vectors(result, natural_order, "complex128")["state"],
            "failed",
        )
        self.assertEqual(
            verifier.compare_vectors(result, result.conjugate(), "complex128")["state"],
            "failed",
        )

    def test_small_stencil_copies_every_boundary_and_computes_one_interior(self):
        expected = list(range(27))
        expected[13] = 260  # 2*13 + 3*(12+14+10+16+4+22).
        result = verifier.numpy_stencil(list(range(27)), [2, 3], 3, 3, 3)
        np.testing.assert_array_equal(result, expected)

    def test_shifted_impulse_and_complex_tone_fix_fft_direction_order_and_scale(self):
        real, imag = [0.0] * 1024, [0.0] * 1024
        real[1] = 1
        expected = []
        for slot in range(1024):
            frequency = sum(((slot >> bit) & 1) << (9 - bit) for bit in range(10))
            angle = -2 * math.pi * frequency / 1024
            expected.append(complex(math.cos(angle), math.sin(angle)))
        result = verifier.numpy_fft(real, imag)
        np.testing.assert_allclose(result, expected, atol=1e-12, rtol=0)
        self.assertEqual(
            verifier.compare_vectors(result, result / 1024, "complex128")["state"],
            "failed",
        )
        self.assertEqual(
            verifier.compare_vectors(
                result, result.imag + 1j * result.real, "complex128"
            )["state"],
            "failed",
        )
        samples = [
            complex(
                math.cos(2 * math.pi * 3 * n / 1024),
                math.sin(2 * math.pi * 3 * n / 1024),
            )
            for n in range(1024)
        ]
        tone = verifier.numpy_fft(
            [value.real for value in samples], [value.imag for value in samples]
        )
        exact = np.zeros(1024, dtype=np.complex128)
        exact[768] = 1024
        np.testing.assert_allclose(tone, exact, atol=1e-10, rtol=0)

    def test_asymmetric_stencil_impulses_verify_axis_strides_and_boundary_copy(self):
        index = lambda x, y, z: x + 16 * (y + 32 * z)
        values = [0] * 16384
        center = index(3, 5, 7)
        values[center] = 1
        expected = [0] * 16384
        expected[center] = 2
        for neighbor in (
            index(2, 5, 7),
            index(4, 5, 7),
            index(3, 4, 7),
            index(3, 6, 7),
            index(3, 5, 6),
            index(3, 5, 8),
        ):
            expected[neighbor] = 3
        result = verifier.numpy_stencil(values, [2, 3], 16, 32, 32)
        np.testing.assert_array_equal(result, expected)
        wrong_axes = verifier.numpy_stencil(values, [2, 3], 32, 32, 16)
        self.assertEqual(
            verifier.compare_vectors(result, wrong_axes, "int32")["state"], "failed"
        )
        values = [0] * 16384
        values[index(0, 5, 7)] = 17
        expected = list(values)
        expected[index(1, 5, 7)] = 51
        np.testing.assert_array_equal(
            verifier.numpy_stencil(values, [2, 3], 16, 32, 32), expected
        )

    def test_production_contracts_accept_analytic_complete_vectors_and_reject_one_wrong_value(
        self,
    ):
        for benchmark in verifier.CONTRACTS:
            with self.subTest(
                benchmark=benchmark
            ), tempfile.TemporaryDirectory() as temporary:
                value = fixture(benchmark)
                if benchmark == "gemm":
                    expected = list(range(64))  # Identity A times B.
                elif benchmark == "fft":
                    expected = [1 + 0j] * 1024  # Unit impulse at time zero.
                else:
                    expected = [
                        1 if x in (0, 15) or y in (0, 31) or z in (0, 31) else 20
                        for z in range(32)
                        for y in range(32)
                        for x in range(16)
                    ]
                root = Path(temporary)
                (root / "fixture.json").write_text(json.dumps(value))
                (root / "raw.txt").write_bytes(wire(value, expected))
                result = verifier.verify_files(root / "fixture.json", root / "raw.txt")
                self.assertEqual(result["state"], "passed", result)
                self.assertEqual(result["compared_count"], value["output_count"])
                wrong = list(expected)
                wrong[0] += 1
                (root / "raw.txt").write_bytes(wire(value, wrong))
                # An unrelated forced-pass receipt is never consulted.
                (root / "guest-check.json").write_text(
                    '{"state":"passed","guest_pass":true}'
                )
                rejected = verifier.verify_files(
                    root / "fixture.json", root / "raw.txt"
                )
                self.assertEqual(rejected["state"], "failed", rejected)
                self.assertEqual(rejected["mismatch_count"], 1)
                self.assertEqual(rejected["first_mismatches"][0]["index"], 0)

    def test_missing_duplicate_reordered_extra_or_wrong_identity_rows_reject(self):
        value = fixture("gemm")
        good = wire(value, list(range(64))).decode().splitlines()
        variants = [
            good[:10] + good[11:],
            good[:10] + [good[9]] + good[11:],
            good[:2] + [good[3], good[2]] + good[4:],
            good + ["Check Passed"],
            [good[0].replace(value["fixture_sha256"], "0" * 64)] + good[1:],
        ]
        for lines in variants:
            with self.subTest(first=lines[:2]), self.assertRaises(ValueError):
                verifier.parse_observed(("\n".join(lines) + "\n").encode(), value)

    def test_nonfinite_observed_values_never_pass_comparison(self):
        value = fixture("fft")
        outputs = [1 + 0j] * 1024
        outputs[0] = complex(float("nan"), 0)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            verifier.parse_observed(wire(value, outputs), value)
        with self.assertRaisesRegex(ValueError, "finite"):
            verifier.compare_vectors(
                np.array([1 + 0j]), np.array([complex(float("nan"), 0)]), "complex128"
            )

    def test_wire_grammar_accepts_lf_crlf_and_rejects_hidden_record_separators(self):
        value = fixture("gemm")
        payload = wire(value, list(range(64)))
        observed, _ = verifier.parse_observed(payload.replace(b"\n", b"\r\n"), value)
        np.testing.assert_array_equal(observed, list(range(64)))
        for separator in (b"\x0b", b"\x0c", b"\x1c", b"\x1d", b"\x1e"):
            with self.subTest(separator=separator), self.assertRaises(ValueError):
                verifier.parse_observed(payload.replace(b"\n", separator, 1), value)

    def test_fixture_tamper_hash_duplicates_overflow_and_reversed_twiddles_reject(self):
        value = fixture("gemm")
        changed = copy.deepcopy(value)
        changed["inputs"]["b"][0] += 1
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            verifier.load_fixture(json.dumps(changed).encode())
        payload = json.dumps(value).replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1'
        )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verifier.load_fixture(payload.encode())
        changed = copy.deepcopy(value)
        changed["inputs"] = {"a": [32767] * 64, "b": [32767] * 64}
        changed["fixture_sha256"] = verifier.fixture_digest(changed)
        with self.assertRaisesRegex(ValueError, "overflow"):
            verifier.load_fixture(json.dumps(changed).encode())
        changed = fixture("fft")
        changed["inputs"]["imag_twid"][1] *= -1
        changed["fixture_sha256"] = verifier.fixture_digest(changed)
        with self.assertRaisesRegex(ValueError, "twiddle"):
            verifier.load_fixture(json.dumps(changed).encode())

    def test_known_component_tolerances_have_both_accept_and_reject_controls(self):
        expected = np.array([0 + 0j])
        self.assertEqual(
            verifier.compare_vectors(expected, np.array([0.5e-6 + 0j]), "complex128")[
                "state"
            ],
            "passed",
        )
        self.assertEqual(
            verifier.compare_vectors(expected, np.array([2e-6 + 0j]), "complex128")[
                "state"
            ],
            "failed",
        )
        # A large imaginary part must not widen the real component's tolerance.
        self.assertEqual(
            verifier.compare_vectors(
                np.array([0 + 1024j]), np.array([2e-6 + 1024j]), "complex128"
            )["state"],
            "failed",
        )

    def test_external_raw_file_hash_and_regular_file_constraints_reject_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = fixture("gemm")
            (root / "fixture.json").write_text(json.dumps(value))
            (root / "raw.txt").write_bytes(wire(value, list(range(64))))
            result = verifier.verify_files(
                root / "fixture.json", root / "raw.txt", expected_output_hash="0" * 64
            )
            self.assertEqual(result["state"], "rejected")
            self.assertIn("SHA-256", result["error"])
            (root / "linked.txt").symlink_to(root / "raw.txt")
            self.assertEqual(
                verifier.verify_files(root / "fixture.json", root / "linked.txt")[
                    "state"
                ],
                "rejected",
            )


if __name__ == "__main__":
    unittest.main()
