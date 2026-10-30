"""Independent, fixed-shape input and all-output contracts for configured runs.

The host references deliberately use a direct DFT, ordinary matrix product and
coordinate-based stencil, rather than the recovered accelerator algorithms.
The text protocol carries observed IEEE/integer bits, not a guest pass marker.
"""
import cmath
import hashlib
import json
import math
import re
import struct


SCHEMA_VERSION = 1
DATASETS = ("baseline", "seeded", "zeros", "boundary")
SHAPES = {
    "gemm": {"rows": 8, "inner": 8, "cols": 8},
    "fft": {"samples": 1024},
    "stencil3d": {"row": 16, "col": 32, "hyt": 32},
}
OUTPUTS = {"gemm": ("int32", 64), "fft": ("complex128", 1024),
           "stencil3d": ("int32", 16384)}
FFT_ABS_TOLERANCE = 1e-6
FFT_REL_TOLERANCE = 1e-9
_INT32 = re.compile(r"^[0-9a-fA-F]{8}$")
_COMPLEX128 = re.compile(r"^[0-9a-fA-F]{32}$")
_ROW = re.compile(r"^SALAM_RESULT ([0-9]+) ([0-9a-fA-F]+)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_fixture_bytes(fixture):
    """Hash exactly the portable fixture fields, excluding its stored hash."""
    content = {key: value for key, value in fixture.items()
               if key != "fixture_sha256"}
    return json.dumps(content, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def fixture_sha256(fixture):
    return hashlib.sha256(canonical_fixture_bytes(fixture)).hexdigest()


class _DeterministicIntegers:
    """Explicit uint32 LCG so fixtures do not depend on Python random versions."""
    def __init__(self, seed):
        self.state = seed

    def draw(self, lower, upper):
        self.state = (1664525 * self.state + 1013904223) & 0xffffffff
        return lower + self.state % (upper - lower + 1)


def make_fixture(benchmark, dataset="seeded", seed=1):
    if benchmark not in SHAPES or dataset not in DATASETS:
        raise ValueError("Unsupported benchmark or dataset")
    if type(seed) is not int or not 0 <= seed <= 0xffffffff:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    random = _DeterministicIntegers(seed)
    if benchmark == "gemm":
        if dataset == "seeded":
            a = [random.draw(-8, 8) for _ in range(64)]
            b = [random.draw(-8, 8) for _ in range(64)]
        elif dataset == "zeros":
            a, b = [0] * 64, [0] * 64
        elif dataset == "boundary":
            a = [int(i // 8 == i % 8) for i in range(64)]
            b = [16 if i % 2 else -16 for i in range(64)]
        else:
            a = [i % 9 - 4 for i in range(64)]
            b = [(i * 3 + 5) % 13 - 6 for i in range(64)]
        inputs = {"a": a, "b": b}
    elif benchmark == "fft":
        real, imag = [0.0] * 1024, [0.0] * 1024
        if dataset == "seeded":
            real = [random.draw(-32, 32) / 16.0 for _ in range(1024)]
            imag = [random.draw(-32, 32) / 16.0 for _ in range(1024)]
        elif dataset == "boundary":
            real[0], real[1023], imag[512] = 1.0, -0.5, 0.25
        elif dataset == "baseline":
            real[0] = 1.0
        roots = [cmath.exp(-2j * math.pi * k / 1024) for k in range(512)]
        inputs = {"real": real, "imag": imag,
                  "real_twid": [value.real for value in roots],
                  "imag_twid": [value.imag for value in roots]}
    else:
        if dataset == "seeded":
            values = [random.draw(-16, 16) for _ in range(16384)]
        elif dataset == "zeros":
            values = [0] * 16384
        elif dataset == "boundary":
            values = []
            for z in range(32):
                for y in range(32):
                    for x in range(16):
                        edge = x in (0, 15) or y in (0, 31) or z in (0, 31)
                        values.append((8 if (x + y + z) % 2 else -8) if edge else 0)
        else:
            values = list(range(16384))
        inputs = {"input": values,
                  "coefficients": [-2, 3] if dataset == "boundary" else [2, 3]}
    kind, count = OUTPUTS[benchmark]
    fixture = {"schema_version": SCHEMA_VERSION, "benchmark": benchmark,
               "dataset": dataset, "seed": seed, "shape": dict(SHAPES[benchmark]),
               "inputs": inputs, "output_kind": kind, "output_count": count}
    fixture["fixture_sha256"] = fixture_sha256(fixture)
    validate_fixture(fixture)
    return fixture


def validate_fixture(fixture):
    fields = {"schema_version", "benchmark", "dataset", "seed", "shape",
              "inputs", "output_kind", "output_count", "fixture_sha256"}
    if not isinstance(fixture, dict) or set(fixture) != fields:
        raise ValueError("Fixture fields are incomplete or unsupported")
    benchmark = fixture["benchmark"]
    if (type(fixture["schema_version"]) is not int
            or fixture["schema_version"] != SCHEMA_VERSION
            or not isinstance(benchmark, str) or benchmark not in SHAPES
            or fixture["dataset"] not in DATASETS
            or type(fixture["seed"]) is not int
            or not 0 <= fixture["seed"] <= 0xffffffff
            or fixture["shape"] != SHAPES[benchmark]
            or fixture["output_kind"] != OUTPUTS[benchmark][0]
            or type(fixture["output_count"]) is not int
            or fixture["output_count"] != OUTPUTS[benchmark][1]):
        raise ValueError("Fixture identity, dimensions or output contract is invalid")
    shape = fixture["shape"]
    if not isinstance(shape, dict) or any(type(value) is not int for value in shape.values()):
        raise ValueError("Fixture dimensions must be integers")
    inputs = fixture["inputs"]
    counts = ({"a": 64, "b": 64} if benchmark == "gemm" else
              {"real": 1024, "imag": 1024, "real_twid": 512, "imag_twid": 512}
              if benchmark == "fft" else {"input": 16384, "coefficients": 2})
    if not isinstance(inputs, dict) or set(inputs) != set(counts):
        raise ValueError("Fixture input arrays do not match the workload")
    for key, size in counts.items():
        values = inputs[key]
        if not isinstance(values, list) or len(values) != size:
            raise ValueError("Fixture array length is invalid: " + key)
        if benchmark == "fft":
            if any(type(v) not in (int, float) or not math.isfinite(v)
                   or abs(v) > 16 for v in values):
                raise ValueError("FFT inputs must be finite and bounded")
        else:
            bound = 16 if key == "coefficients" else 32767
            if any(type(v) is not int or abs(v) > bound for v in values):
                raise ValueError("Integer input is outside the no-overflow contract")
    # Eight int16 products fit in signed int32 only for the generated <=8 inputs.
    # Broader custom fixtures are accepted only with a conservative safe bound.
    if benchmark == "gemm":
        max_a = max(abs(v) for v in inputs["a"])
        max_b = max(abs(v) for v in inputs["b"])
        if max_a * max_b * 8 > 0x7fffffff:
            raise ValueError("GEMM fixture may cause signed int32 overflow")
    if benchmark == "fft":
        for k, (real, imag) in enumerate(zip(inputs["real_twid"], inputs["imag_twid"])):
            if abs(complex(real, imag) - cmath.exp(-2j * math.pi * k / 1024)) > 1e-12:
                raise ValueError("FFT twiddle is not the required root of unity")
    digest = fixture["fixture_sha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or digest != fixture_sha256(fixture):
        raise ValueError("Fixture SHA-256 does not match its inputs")
    return fixture


def reference_outputs(fixture):
    """Compute every expected output from attributable input arrays."""
    validate_fixture(fixture)
    name, data = fixture["benchmark"], fixture["inputs"]
    if name == "gemm":
        return [sum(data["a"][row * 8 + k] * data["b"][k * 8 + col]
                    for k in range(8)) for row in range(8) for col in range(8)]
    if name == "fft":
        samples = [complex(real, imag) for real, imag in zip(data["real"], data["imag"])]
        result = []
        for index in range(1024):
            frequency = int(format(index, "010b")[::-1], 2)
            step = cmath.exp(-2j * math.pi * frequency / 1024)
            power, value = 1 + 0j, 0j
            for sample in samples:
                value += sample * power
                power *= step
            result.append([value.real, value.imag])
        return result
    inp, coefficients = data["input"], data["coefficients"]
    result = list(inp)
    for z in range(1, 31):
        for y in range(1, 31):
            for x in range(1, 15):
                index = x + 16 * (y + 32 * z)
                neighbors = sum(inp[index + offset] for offset in (-1, 1, -16, 16, -512, 512))
                result[index] = inp[index] * coefficients[0] + neighbors * coefficients[1]
    return result


def encode_output(value, output_kind):
    """Encode a host test/reference value using the observed-output wire format."""
    if output_kind == "int32":
        if type(value) is not int or not -0x80000000 <= value <= 0x7fffffff:
            raise ValueError("Expected an int32 output")
        return struct.pack(">i", value).hex()
    if output_kind == "complex128":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("Expected two float64 components")
        return struct.pack(">dd", *value).hex()
    raise ValueError("Unsupported output kind")


def render_output(fixture, values=None):
    """Host-side protocol fixture helper; not evidence of a simulator run."""
    validate_fixture(fixture)
    if values is None:
        values = reference_outputs(fixture)
    suffix = "v1 %s %s %d %s" % (fixture["benchmark"], fixture["fixture_sha256"],
                                   fixture["output_count"], fixture["output_kind"])
    lines = ["SALAM_RESULT_BEGIN " + suffix]
    lines.extend("SALAM_RESULT %d %s" % (index, encode_output(value, fixture["output_kind"]))
                 for index, value in enumerate(values))
    lines.append("SALAM_RESULT_END " + suffix)
    return "\n".join(lines) + "\n"


def assess_output(text, fixture):
    """Reject malformed, nonfinite or numerically wrong observed output blocks."""
    validate_fixture(fixture)
    result = {"schema_version": 1, "kind": "independent_benchmark_oracle",
              "benchmark": fixture["benchmark"], "fixture_sha256": fixture["fixture_sha256"],
              "state": "failed", "issues": [], "expected_count": fixture["output_count"],
              "observed_count": 0, "compared_count": 0, "mismatch_count": 0,
              "output_sha256": None,
              "max_absolute_error": None,
              "absolute_tolerance": FFT_ABS_TOLERANCE if fixture["benchmark"] == "fft" else 0,
              "relative_tolerance": FFT_REL_TOLERANCE if fixture["benchmark"] == "fft" else 0,
              "method": {"gemm": "independent integer matrix product",
                         "fft": "direct complex DFT in bit-reversed output order",
                         "stencil3d": "independent coordinate-based seven-point stencil"}[fixture["benchmark"]]}
    if not isinstance(text, str):
        result["issues"].append("Observed output is not text")
        return result
    suffix = "v1 %s %s %d %s" % (fixture["benchmark"], fixture["fixture_sha256"],
                                   fixture["output_count"], fixture["output_kind"])
    expected_begin, expected_end = "SALAM_RESULT_BEGIN " + suffix, "SALAM_RESULT_END " + suffix
    lines = [line.rstrip("\r") for line in text.splitlines()]
    begin = [i for i, line in enumerate(lines) if line.startswith("SALAM_RESULT_BEGIN")]
    end = [i for i, line in enumerate(lines) if line.startswith("SALAM_RESULT_END")]
    if len(begin) != 1 or len(end) != 1 or begin[0] >= end[0]:
        result["issues"].append("Expected exactly one complete ordered output block")
        return result
    if lines[begin[0]] != expected_begin or lines[end[0]] != expected_end:
        result["issues"].append("Output identity/count/kind does not match the fixture")
        return result
    if any(line.startswith("SALAM_RESULT") for line in lines[:begin[0]] + lines[end[0] + 1:]):
        result["issues"].append("Output protocol record occurs outside the block")
        return result
    observed = []
    kind = fixture["output_kind"]
    for index, line in enumerate(lines[begin[0] + 1:end[0]]):
        match = _ROW.fullmatch(line)
        if match is None or match.group(1) != str(index):
            result["issues"].append("Output index is missing, repeated, unordered or malformed at %d" % index)
            return result
        hex_value = match.group(2)
        if not (_INT32 if kind == "int32" else _COMPLEX128).fullmatch(hex_value):
            result["issues"].append("Output bit representation is malformed at %d" % index)
            return result
        if kind == "int32":
            observed.append(struct.unpack(">i", bytes.fromhex(hex_value))[0])
        else:
            value = struct.unpack(">dd", bytes.fromhex(hex_value))
            if not all(math.isfinite(component) for component in value):
                result["issues"].append("FFT output is not finite at %d" % index)
                return result
            observed.append(value)
    result["observed_count"] = len(observed)
    if len(observed) != fixture["output_count"]:
        result["issues"].append("Output block is truncated or has extra rows")
        return result
    result["output_sha256"] = hashlib.sha256(b"".join(
        bytes.fromhex(encode_output(value, kind)) for value in observed)).hexdigest()
    expected = reference_outputs(fixture)
    max_error = 0.0
    for index, (actual, wanted) in enumerate(zip(observed, expected)):
        pairs = zip(actual, wanted) if kind == "complex128" else ((actual, wanted),)
        mismatch = False
        for value, reference in pairs:
            error = abs(value - reference)
            max_error = max(max_error, error)
            tolerance = (FFT_ABS_TOLERANCE + FFT_REL_TOLERANCE * abs(reference)
                         if kind == "complex128" else 0)
            mismatch = mismatch or error > tolerance
        if mismatch:
            result["mismatch_count"] += 1
            if result["mismatch_count"] <= 8:
                result["issues"].append("Numerical output mismatch at index %d" % index)
    result["compared_count"] = len(expected)
    result["max_absolute_error"] = max_error
    if not result["issues"]:
        result["state"] = "passed"
    return result
