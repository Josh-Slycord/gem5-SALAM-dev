"""Focused source-pinned checks for staged FFT and stencil3d benchmark overlays."""
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OVERLAYS = PROJECT / "experiments" / "regression" / "overlays"
MANIFEST = OVERLAYS / "manifest.json"


class BenchmarkOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.entries = {entry["overlay"]: entry for entry in cls.manifest["entries"]}
        cls.engine = Path(
            json.loads((PROJECT / "workspace.json").read_text(encoding="utf-8"))[
                "engine"
            ]["path"]
        )

    def test_manifest_pins_all_three_overlays(self):
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["kind"], "staged_benchmark_overlays")
        self.assertEqual(
            set(self.entries),
            {
                "experiments/regression/overlays/fft/sw/main.cpp",
                "experiments/regression/overlays/stencil3d/sw/bench.h",
                "experiments/regression/overlays/stencil3d/hw/Makefile",
            },
        )
        for name, entry in self.entries.items():
            with self.subTest(overlay=name):
                self.assertEqual(entry["kind"], "replace")
                self.assertEqual(
                    hashlib.sha256((PROJECT / name).read_bytes()).hexdigest(),
                    entry["overlay_sha256"],
                )
                self.assertRegex(entry["base_sha256"], r"^[0-9a-f]{64}$")
                self.assertIn("--- " + entry["base"], entry["unified_diff"])
                self.assertIn("+++ " + entry["overlay"], entry["unified_diff"])
                self.assertTrue(entry["diff_summary"])

    def test_overlay_bases_match_selected_engine_when_available(self):
        if not self.engine.is_dir():
            self.skipTest(
                "Independent WSL engine is not mounted in this Python environment"
            )
        for entry in self.entries.values():
            with self.subTest(base=entry["base"]):
                source = self.engine / entry["base"]
                self.assertTrue(source.is_file())
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    entry["base_sha256"],
                )

    def test_fft_guest_uses_one_marker_and_explicit_measurement_window(self):
        source = (OVERLAYS / "fft/sw/main.cpp").read_text(encoding="utf-8")
        self.assertLess(
            source.index("m5_reset_stats();"), source.index("genData(&ffts);")
        )
        self.assertEqual(source.count('printf("Check Passed'), 1)
        self.assertEqual(source.count('printf("Check Failed'), 1)
        self.assertIn("workbench_fft_sample_matches(real[i], real_check[i])", source)
        self.assertIn("workbench_fft_sample_matches(img[i], img_check[i])", source)
        self.assertIn('printf("FFT mismatch index %d component real\\n", i);', source)
        self.assertIn(
            'printf("FFT mismatch index %d component imaginary\\n", i);',
            source,
        )
        self.assertNotRegex(source, r"printf\([^;]*%[aAeEfFgG]")

    def test_fft_actual_predicate_host_semantics(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("No host C++ compiler available")
        source = (OVERLAYS / "fft/sw/main.cpp").read_text(encoding="utf-8")
        begin = source.index("static bool workbench_fft_sample_matches(")
        end = source.index("\n}\n", begin) + 2
        predicate = source[begin:end]
        fixture = (
            """
#include <cmath>
#include <limits>
#define EPSILON ((double)1.0e-6)
"""
            + predicate
            + """
int main() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    if (!workbench_fft_sample_matches(1.0, 1.0 + 5.0e-7)) return 1;
    if (workbench_fft_sample_matches(1.0, 1.0 + 2.0e-6)) return 2;
    if (workbench_fft_sample_matches(nan, 0.0)) return 3;
    if (workbench_fft_sample_matches(0.0, nan)) return 4;
    if (workbench_fft_sample_matches(inf, inf)) return 5;
    if (workbench_fft_sample_matches(1.0e308, -1.0e308)) return 6;
    if (!workbench_fft_sample_matches(-1.0, -1.0)) return 7;
    return 0;
}
"""
        )
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / (
                "fft_predicate.exe" if sys.platform == "win32" else "fft_predicate"
            )
            build = subprocess.run(
                [
                    compiler,
                    "-std=c++11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-x",
                    "c++",
                    "-",
                    "-o",
                    str(executable),
                ],
                input=fixture,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=10
            )
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_fft_fixed_goldens_match_source_kernel_when_available(self):
        data_path = self.engine / "benchmarks/sys_validation/fft/sw/data.c"
        if not data_path.is_file():
            self.skipTest("Independent WSL FFT data source is not mounted")
        source = data_path.read_text(encoding="utf-8").split("#else", 1)[0]
        arrays = dict(
            re.findall(r"const double (\w+)\[[^\]]+\]\s*=\s*\{([^}]*)\}", source, re.S)
        )
        values = {
            name: [float(part.strip()) for part in body.split(",") if part.strip()]
            for name, body in arrays.items()
        }
        self.assertEqual(
            {
                name: len(values[name])
                for name in (
                    "re",
                    "co",
                    "re_twid",
                    "co_twid",
                    "re_chk",
                    "co_chk",
                )
            },
            {
                "re": 1024,
                "co": 1024,
                "re_twid": 512,
                "co_twid": 512,
                "re_chk": 1024,
                "co_chk": 1024,
            },
        )
        real, imag = values["re"][:], values["co"][:]
        span, level = 512, 0
        while span:
            odd = span
            while odd < 1024:
                odd |= span
                even = odd ^ span
                temporary = real[even] + real[odd]
                real[odd] = real[even] - real[odd]
                real[even] = temporary
                temporary = imag[even] + imag[odd]
                imag[odd] = imag[even] - imag[odd]
                imag[even] = temporary
                root_index = (even << level) & 1023
                if root_index:
                    temporary = (
                        values["re_twid"][root_index] * real[odd]
                        - values["co_twid"][root_index] * imag[odd]
                    )
                    imag[odd] = (
                        values["re_twid"][root_index] * imag[odd]
                        + values["co_twid"][root_index] * real[odd]
                    )
                    real[odd] = temporary
                odd += 1
            span >>= 1
            level += 1
        self.assertTrue(all(math.isfinite(value) for value in real + imag))
        self.assertLessEqual(
            max(abs(a - b) for a, b in zip(real, values["re_chk"])), 1.0e-6
        )
        self.assertLessEqual(
            max(abs(a - b) for a, b in zip(imag, values["co_chk"])), 1.0e-6
        )

    def test_stencil3d_oracle_has_no_duplicate_marker(self):
        header = (OVERLAYS / "stencil3d/sw/bench.h").read_text(encoding="utf-8")
        makefile = (OVERLAYS / "stencil3d/hw/Makefile").read_text(encoding="utf-8")
        self.assertIn("for( i=0; i < SIZE; i++ )", header)
        self.assertIn("sts->sol[i]!= sts->check[i]", header)
        self.assertNotIn('"Check Passed"', header)
        self.assertNotIn('"Check Failed"', header)
        self.assertIn("-target armv7-pc-none-eabi", makefile)

    def test_arm_guest_overlays_parse_when_supported_engine_available(self):
        compiler = shutil.which("arm-none-eabi-g++")
        if compiler is None or not self.engine.is_dir():
            self.skipTest("Supported ARM cross-compiler/engine is not available")
        cases = (
            ("fft", "main.cpp", []),
            ("stencil3d", "bench.h", ["-include", "cstdio", "-x", "c++"]),
        )
        for benchmark, filename, extra in cases:
            with self.subTest(benchmark=benchmark):
                source = OVERLAYS / benchmark / "sw" / filename
                original_sw = (
                    self.engine / "benchmarks/sys_validation" / benchmark / "sw"
                )
                argv = (
                    [compiler, "-std=gnu++11", "-fsyntax-only"]
                    + extra
                    + ["-I", str(original_sw), str(source)]
                )
                result = subprocess.run(
                    argv, capture_output=True, text=True, timeout=30
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
