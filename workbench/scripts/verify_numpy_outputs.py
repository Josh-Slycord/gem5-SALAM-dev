#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""NumPy cross-check of saved inputs and complete raw SALAM output vectors.

This tool imports no workbench modules and never reads a guest/checker pass
flag. It accepts only the three currently specified fixed-shape contracts.
Numerical agreement does not establish that a simulator or GUI actually ran.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path

import numpy as np

CONTRACTS = {
    "gemm": ({"rows": 8, "inner": 8, "cols": 8}, "int32", 64),
    "fft": ({"samples": 1024}, "complex128", 1024),
    "stencil3d": ({"row": 16, "col": 32, "hyt": 32}, "int32", 16384),
}
FIELDS = {
    "schema_version",
    "benchmark",
    "dataset",
    "seed",
    "shape",
    "inputs",
    "output_kind",
    "output_count",
    "fixture_sha256",
}
ABS_TOLERANCE = 1.0e-6
REL_TOLERANCE = 1.0e-9
SHA256 = re.compile(r"[0-9a-f]{64}")


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def read_snapshot(path, maximum):
    """Read one regular file once; reject concurrent descriptor changes."""
    source = Path(path).absolute()
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError("Source is not a bounded regular file: " + str(source))
        chunks, length = [], 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            if length > maximum:
                raise ValueError("Source exceeded bounded reader limit")
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(before) != identity(after) or length != before.st_size:
            raise ValueError("Source changed while its snapshot was read")
        payload = b"".join(chunks)
        return payload, {
            "path": str(source),
            "sha256": _sha(payload),
            "bytes": length,
            "device": before.st_dev,
            "inode": before.st_ino,
            "mtime_ns": before.st_mtime_ns,
            "ctime_ns": before.st_ctime_ns,
        }
    finally:
        os.close(descriptor)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def fixture_digest(fixture):
    body = dict(fixture)
    body.pop("fixture_sha256", None)
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    return _sha(encoded)


def load_fixture(payload):
    fixture = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(fixture, dict) or set(fixture) != FIELDS:
        raise ValueError("Unsupported or incomplete fixture fields")
    benchmark = fixture["benchmark"]
    if not isinstance(benchmark, str) or benchmark not in CONTRACTS:
        raise ValueError("Unsupported benchmark")
    shape, kind, count = CONTRACTS[benchmark]
    if (
        type(fixture["schema_version"]) is not int
        or fixture["schema_version"] != 1
        or type(fixture["seed"]) is not int
        or not 0 <= fixture["seed"] <= 0xFFFFFFFF
        or fixture["dataset"] not in ("baseline", "seeded", "zeros", "boundary")
        or fixture["shape"] != shape
        or not isinstance(fixture["shape"], dict)
        or any(type(value) is not int for value in fixture["shape"].values())
        or fixture["output_kind"] != kind
        or type(fixture["output_count"]) is not int
        or fixture["output_count"] != count
    ):
        raise ValueError(
            "Fixture identity or fixed dimensions do not match the contract"
        )
    digest = fixture["fixture_sha256"]
    if (
        not isinstance(digest, str)
        or not SHA256.fullmatch(digest)
        or fixture_digest(fixture) != digest
    ):
        raise ValueError("Canonical fixture SHA-256 mismatch")
    lengths = (
        {"a": 64, "b": 64}
        if benchmark == "gemm"
        else {"real": 1024, "imag": 1024, "real_twid": 512, "imag_twid": 512}
        if benchmark == "fft"
        else {"input": 16384, "coefficients": 2}
    )
    inputs = fixture["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != set(lengths):
        raise ValueError("Unexpected input array fields")
    for name, length in lengths.items():
        values = inputs[name]
        if not isinstance(values, list) or len(values) != length:
            raise ValueError("Wrong input array length: " + name)
        if benchmark == "fft":
            valid = all(
                type(value) in (int, float)
                and math.isfinite(value)
                and abs(value) <= 16
                for value in values
            )
        else:
            limit = 16 if name == "coefficients" else 32767
            valid = all(type(value) is int and abs(value) <= limit for value in values)
        if not valid:
            raise ValueError("Input outside finite/no-overflow contract: " + name)
    if benchmark == "gemm":
        if max(map(abs, inputs["a"])) * max(map(abs, inputs["b"])) * 8 > 0x7FFFFFFF:
            raise ValueError("GEMM inputs can overflow signed int32 accumulation")
    if benchmark == "fft":
        angles = -2.0 * np.pi * np.arange(512, dtype=np.float64) / 1024
        roots = np.cos(angles) + 1j * np.sin(angles)
        supplied = np.asarray(inputs["real_twid"]) + 1j * np.asarray(
            inputs["imag_twid"]
        )
        if np.any(np.abs(supplied - roots) > 1.0e-12):
            raise ValueError("FFT twiddles do not describe the forward transform")
    return fixture


def numpy_gemm(a, b, rows, inner, columns):
    left = np.asarray(a, dtype=np.int64).reshape(rows, inner)
    right = np.asarray(b, dtype=np.int64).reshape(inner, columns)
    product = np.dot(left, right)
    if np.any(product < -0x80000000) or np.any(product > 0x7FFFFFFF):
        raise ValueError("Expected GEMM output is outside int32")
    return product.reshape(-1)


def numpy_fft(real, imag):
    """Forward FFT, then binary-axis transpose for the kernel's DIF ordering."""
    samples = np.asarray(real, dtype=np.float64) + 1j * np.asarray(
        imag, dtype=np.float64
    )
    size = samples.size
    if size < 2 or size & (size - 1):
        raise ValueError("FFT length must be a power of two")
    bits = size.bit_length() - 1
    addresses = np.arange(size).reshape((2,) * bits)
    order = addresses.transpose(tuple(range(bits - 1, -1, -1))).reshape(-1)
    return np.fft.fft(samples)[order]


def numpy_stencil(values, coefficients, rows, columns, height):
    """C-order [z,y,x], with all six boundary faces copied from the input."""
    source = np.asarray(values, dtype=np.int64).reshape(height, columns, rows)
    output = source.copy()
    neighbors = (
        source[:-2, 1:-1, 1:-1]
        + source[2:, 1:-1, 1:-1]
        + source[1:-1, :-2, 1:-1]
        + source[1:-1, 2:, 1:-1]
        + source[1:-1, 1:-1, :-2]
        + source[1:-1, 1:-1, 2:]
    )
    output[1:-1, 1:-1, 1:-1] = (
        coefficients[0] * source[1:-1, 1:-1, 1:-1] + coefficients[1] * neighbors
    )
    if np.any(output < -0x80000000) or np.any(output > 0x7FFFFFFF):
        raise ValueError("Expected stencil output is outside int32")
    return output.reshape(-1)


def expected_outputs(fixture):
    inputs = fixture["inputs"]
    if fixture["benchmark"] == "gemm":
        return numpy_gemm(inputs["a"], inputs["b"], 8, 8, 8)
    if fixture["benchmark"] == "fft":
        return numpy_fft(inputs["real"], inputs["imag"])
    return numpy_stencil(inputs["input"], inputs["coefficients"], 16, 32, 32)


def parse_observed(payload, fixture):
    """Parse a dedicated result file, not a console log or saved assessment."""
    if not payload.endswith(b"\n"):
        raise ValueError("Result file lacks its final newline")
    # Only the writer's LF and a normal archival CRLF conversion are accepted.
    # str.splitlines() would also accept VT/FF/ASCII record separators.
    lines = payload.decode("ascii").split("\n")[:-1]
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    count = fixture["output_count"]
    suffix = "v1 {} {} {} {}".format(
        fixture["benchmark"], fixture["fixture_sha256"], count, fixture["output_kind"]
    )
    if len(lines) != count + 2:
        raise ValueError("Wrong result framing/row count")
    if (
        lines[0] != "SALAM_RESULT_BEGIN " + suffix
        or lines[-1] != "SALAM_RESULT_END " + suffix
    ):
        raise ValueError("Result frame does not bind to this fixture")
    width = 8 if fixture["output_kind"] == "int32" else 32
    row = re.compile(r"SALAM_RESULT ([0-9]+) ([0-9a-fA-F]{" + str(width) + r"})")
    words = []
    for index, line in enumerate(lines[1:-1]):
        match = row.fullmatch(line)
        if not match or match[1] != str(index):
            raise ValueError(
                "Malformed, duplicated, missing, or reordered row at " + str(index)
            )
        words.append(match[2])
    binary = bytes.fromhex("".join(words))
    if fixture["output_kind"] == "int32":
        observed = np.frombuffer(binary, dtype=">i4").astype(np.int64)
    else:
        components = np.frombuffer(binary, dtype=">f8").reshape(count, 2)
        if not np.all(np.isfinite(components)):
            raise ValueError("Observed FFT output contains nonfinite binary64 values")
        observed = components[:, 0] + 1j * components[:, 1]
    return observed, binary


def compare_vectors(expected, observed, kind):
    if expected.shape != observed.shape:
        raise ValueError("Expected and observed vector lengths differ")
    if not np.all(np.isfinite(expected)) or not np.all(np.isfinite(observed)):
        raise ValueError("Numerical comparison requires finite vectors")
    if kind == "int32":
        mask = expected != observed
        errors = np.abs(expected - observed)
    else:
        expected_parts = np.column_stack((expected.real, expected.imag))
        observed_parts = np.column_stack((observed.real, observed.imag))
        errors = np.abs(observed_parts - expected_parts)
        thresholds = ABS_TOLERANCE + REL_TOLERANCE * np.abs(expected_parts)
        mask = np.any(errors > thresholds, axis=1)
    indices = np.flatnonzero(mask)
    first = []
    for index in indices[:16]:
        value = (
            lambda array: int(array[index])
            if kind == "int32"
            else [float(array[index].real), float(array[index].imag)]
        )
        first.append(
            {
                "index": int(index),
                "expected": value(expected),
                "observed": value(observed),
            }
        )
    return {
        "state": "passed" if indices.size == 0 else "failed",
        "compared_count": int(expected.size),
        "mismatch_count": int(indices.size),
        "first_mismatches": first,
        "maximum_absolute_component_error": float(np.max(errors))
        if errors.size
        else 0.0,
        "absolute_tolerance": ABS_TOLERANCE if kind == "complex128" else 0,
        "relative_tolerance": REL_TOLERANCE if kind == "complex128" else 0,
    }


def _expected_bytes(expected, kind):
    if kind == "int32":
        return expected.astype(">i4").tobytes()
    components = np.column_stack((expected.real, expected.imag))
    return components.astype(">f8").tobytes()


def verify_files(
    fixture_path,
    output_path,
    expected_fixture_file_hash=None,
    expected_output_hash=None,
):
    report = {
        "schema_version": 1,
        "kind": "independent_numpy_numerical_crosscheck",
        "state": "rejected",
        "scope": "All raw output elements against NumPy algorithms on saved input arrays; no simulator execution/build/GUI attestation",
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "implementation": {
            "script_sha256": _sha(Path(__file__).read_bytes()),
            "numpy_version": np.__version__,
            "python_version": sys.version,
            "python_executable": sys.executable,
        },
    }
    try:
        report["stage"] = "read_input_snapshots"
        fixture_bytes, report["fixture_file"] = read_snapshot(
            fixture_path, 2 * 1024 * 1024
        )
        output_bytes, report["output_file"] = read_snapshot(
            output_path, 16 * 1024 * 1024
        )
        for expected, actual, label in (
            (
                expected_fixture_file_hash,
                report["fixture_file"]["sha256"],
                "fixture file",
            ),
            (expected_output_hash, report["output_file"]["sha256"], "raw output"),
        ):
            if expected is not None and (
                not SHA256.fullmatch(expected) or expected != actual
            ):
                raise ValueError("Supplied SHA-256 does not match " + label)
        report["stage"] = "validate_fixture"
        fixture = load_fixture(fixture_bytes)
        report.update(
            benchmark=fixture["benchmark"],
            dataset=fixture["dataset"],
            seed=fixture["seed"],
            shape=fixture["shape"],
            fixture_sha256=fixture["fixture_sha256"],
            output_kind=fixture["output_kind"],
        )
        report["stage"] = "parse_raw_observed_values"
        observed, bits = parse_observed(output_bytes, fixture)
        report["observed_count"] = int(observed.size)
        report["observed_bits_sha256"] = _sha(bits)
        report["stage"] = "numpy_numerical_comparison"
        expected = expected_outputs(fixture)
        report["expected_bits_sha256"] = _sha(
            _expected_bytes(expected, fixture["output_kind"])
        )
        report[
            "bit_hash_encoding"
        ] = "Row-major big-endian signed int32, or binary64 real then imaginary per row; FFT hashes need not match under numerical tolerances"
        report["method"] = {
            "gemm": "NumPy int64 dot with int32 range check",
            "fft": "NumPy forward FFT followed by binary-axis transpose for DIF bit-reversed order",
            "stencil3d": "NumPy int64 seven-point slicing with copied six-face boundary and int32 range check",
        }[fixture["benchmark"]]
        report.update(compare_vectors(expected, observed, fixture["output_kind"]))
    except Exception as error:
        report.update(state="rejected", error=type(error).__name__ + ": " + str(error))
    report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture", required=True, help="Saved benchmark-fixture.json input arrays"
    )
    parser.add_argument(
        "--raw-output", required=True, help="Dedicated salam-results.txt protocol file"
    )
    parser.add_argument("--expected-fixture-file-sha256")
    parser.add_argument("--expected-output-sha256")
    parser.add_argument(
        "--receipt",
        help="New JSON evidence file; an existing file is never overwritten",
    )
    options = parser.parse_args(argv)
    report = verify_files(
        options.fixture,
        options.raw_output,
        options.expected_fixture_file_sha256,
        options.expected_output_sha256,
    )
    payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if options.receipt:
        with Path(options.receipt).open("x", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload, end="")
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
