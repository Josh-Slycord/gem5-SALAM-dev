"""Staged isolation, identity, and cross-language output checks for breadth runs."""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from salam_workbench.benchmark_inputs import (
    OVERLAYS, render_input_header, stage_benchmark_inputs, repair_uart_write, repair_arm_exit,
)
from salam_workbench.benchmark_oracles import make_fixture, assess_output


class BenchmarkInputTests(unittest.TestCase):
    M5OPS_SOURCE = '''#if defined(__arm__)
static void m5_exit()
{
    __asm__ __volatile__ ("mov r0, #0; .inst 0xEE000110 | (0x21 << 16);");
};
#elif defined(__aarch64__)
static void m5_exit(void) {
    __asm__ __volatile__("mov x0, #0; .inst 0XFF000110 | (0x21 << 16);");
};
#else
#define ENABLED 0
#endif
'''
    UART_SOURCE = """int _write_r (struct _reent *r, int file, char * ptr, int len)
{
    r = r;
    file = file;
    ptr = ptr;
    gem5_print(ptr);
    return len;
}
"""

    def _source(self, root, benchmark, *, cluster="custom_clstr"):
        base = root / "benchmarks" / "sys_validation" / benchmark
        (base / "sw").mkdir(parents=True)
        (base / "hw").mkdir()
        common = root / "benchmarks" / "common"
        common.mkdir(exist_ok=True)
        (common / "syscalls.c").write_text(self.UART_SOURCE, encoding="utf-8")
        (common / "m5ops.h").write_text(self.M5OPS_SOURCE, encoding="utf-8")
        definitions = {
            "gemm": "#define ROW 8\n#define COL 8\n#define TYPE int\n",
            "fft": "#define FFT_SIZE 1024\n",
            "stencil3d": "#define ROW 16\n#define COL 32\n#define HYT 32\n#define C_SIZE 2\n",
        }
        (base / "defines.h").write_text(definitions[benchmark], encoding="utf-8")
        (base / "sw" / "main.cpp").write_text(
            '#include "../' + cluster + '_hw_defines.h"\n', encoding="utf-8")
        (base / "sw" / "bench.h").write_text("// Source guest definitions\n", encoding="utf-8")
        (base / (cluster + "_hw_defines.h")).write_text("#define TOP 0x10020000\n", encoding="utf-8")
        (base / "hw" / (benchmark + ".c")).write_text("// Preserve kernel bytes\n", encoding="utf-8")
        (base / "hw" / "Makefile").write_text(
            "KERN=stencil3d.c top.c\nbuild:\n\tclang -O1 -S -emit-llvm $(KERN)\n", encoding="utf-8")
        return base

    def test_all_supported_workloads_preserve_kernels_and_bind_header_identity(self):
        for benchmark in ("gemm", "fft", "stencil3d"):
            with self.subTest(benchmark=benchmark), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                base = self._source(root, benchmark)
                kernel = base / "hw" / (benchmark + ".c")
                before = kernel.read_bytes()
                fixture = make_fixture(benchmark, "seeded", 71)
                receipt = stage_benchmark_inputs(root, benchmark, fixture)
                self.assertTrue(receipt["kernel_preserved"])
                self.assertEqual(kernel.read_bytes(), before)
                self.assertEqual(receipt["fixture_sha256"], fixture["fixture_sha256"])
                self.assertEqual(receipt["uart_write_contract"], "newlib_length_delimited_bytes")
                self.assertEqual(receipt["m5_exit_contract"],
                                 "arm32_zero_delay_r0_r1_with_register_memory_clobbers")
                main = (base / "sw" / "main.cpp").read_text(encoding="utf-8")
                self.assertIn('#include "../custom_clstr_hw_defines.h"', main)
                self.assertNotIn("@CLUSTER_HEADER@", main)
                self.assertIn(fixture["fixture_sha256"],
                              (base / "sw" / "workbench_input.h").read_text())
                for entry in receipt["outputs"]:
                    self.assertEqual(entry["sha256"], hashlib.sha256(
                        (root / entry["path"]).read_bytes()).hexdigest())
                if benchmark == "stencil3d":
                    self.assertIn("-target armv7-pc-none-eabi",
                                  (base / "hw" / "Makefile").read_text())

    def test_refuses_wrong_dimensions_without_writing_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = self._source(root, "gemm")
            (base / "defines.h").write_text("#define ROW 9\n#define COL 8\n")
            before = (base / "sw" / "main.cpp").read_bytes()
            with self.assertRaisesRegex(ValueError, "Unsupported benchmark dimension"):
                stage_benchmark_inputs(root, "gemm", make_fixture("gemm"))
            self.assertFalse((base / "sw" / "workbench_input.h").exists())
            self.assertEqual((base / "sw" / "main.cpp").read_bytes(), before)

    def test_refuses_fixture_for_different_workload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._source(root, "gemm")
            with self.assertRaisesRegex(ValueError, "does not match"):
                stage_benchmark_inputs(root, "gemm", make_fixture("fft"))

    def test_canonical_relative_path_supported_but_other_layouts_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._source(root, "gemm")
            result = stage_benchmark_inputs(root, "benchmarks/sys_validation/gemm",
                                            make_fixture("gemm"))
            self.assertEqual(result["benchmark"], "gemm")
            with self.assertRaisesRegex(ValueError, "supported sys_validation"):
                stage_benchmark_inputs(root, "benchmarks/legacy/gemm", make_fixture("gemm"))

    def test_existing_input_headers_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = self._source(root, "gemm")
            existing = base / "sw" / "workbench_input.h"
            existing.write_text("retained data\n")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                stage_benchmark_inputs(root, "gemm", make_fixture("gemm"))
            self.assertEqual(existing.read_text(), "retained data\n")

    def test_control_options_explicitly_recorded_in_header(self):
        header = render_input_header(make_fixture("gemm"), inject_mismatch=True,
                                     force_guest_pass=True)
        self.assertIn("#define SALAM_INJECT_MISMATCH 1", header)
        self.assertIn("#define SALAM_FORCE_GUEST_PASS 1", header)
        with self.assertRaisesRegex(ValueError, "booleans"):
            render_input_header(make_fixture("gemm"), inject_mismatch=1)

    def test_guest_templates_serialize_actual_buffers_and_bound_output_windows(self):
        for benchmark, emitter in (("gemm", "salam_result_int(i, c[i])"),
                                   ("fft", "salam_result_complex(i, real[i], imag[i])"),
                                   ("stencil3d", "salam_result_int(i, output[i])")):
            with self.subTest(benchmark=benchmark):
                main = (OVERLAYS / benchmark / "sw" / "main.cpp").read_text()
                self.assertIn(emitter, main)
                self.assertLess(main.index("while (stage < 1)"), main.index("salam_check_marker"))
                self.assertLess(main.index("m5_dump_stats();"), main.index("salam_result_begin();"))
                self.assertLess(main.index("salam_result_end();"), main.index("m5_exit();"))
                output_section = main[main.index("salam_result_begin();"):]
                self.assertNotIn("salam_expected", output_section)

    def test_cpp_emitter_round_trips_actual_integer_and_binary64_representations(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("A host C++ compiler is required for cross-language transport test")
        for benchmark in ("gemm", "fft", "stencil3d"):
            with self.subTest(benchmark=benchmark), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                fixture = make_fixture(benchmark, "boundary", 12)
                (root / "workbench_input.h").write_text(render_input_header(fixture), encoding="utf-8")
                shutil.copyfile(OVERLAYS / "common" / "workbench_result.h",
                                root / "workbench_result.h")
                emit = ("salam_result_complex(i, salam_expected_real[i], salam_expected_imag[i]);"
                        if benchmark == "fft" else "salam_result_int(i, salam_expected[i]);")
                source = root / "transport.cpp"
                source.write_text('#include <cstdio>\n'
                                  '#define SALAM_HOST_TEST_WRITEFILE(buffer,length,name) std::fwrite(buffer,1,length,stdout)\n'
                                  '#include "workbench_result.h"\nint main() {\n'
                                  'salam_result_begin();\n'
                                  'for (int i=0; i<SALAM_OUTPUT_COUNT; ++i) ' + emit + '\n'
                                  'salam_result_end();\nreturn 0;\n}\n', encoding="utf-8")
                binary = root / ("transport.exe" if os.name == "nt" else "transport")
                build = subprocess.run([compiler, "-std=c++11", str(source), "-o", str(binary)],
                                       capture_output=True, text=True, timeout=60)
                self.assertEqual(build.returncode, 0, build.stderr)
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
                self.assertEqual(run.returncode, 0, run.stderr)
                assessment = assess_output(run.stdout, fixture)
                self.assertEqual(assessment["state"], "passed", assessment)

    def test_repaired_newlib_write_honors_length_including_embedded_nul(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("A host C++ compiler is required for UART write contract test")
        body = repair_uart_write(self.UART_SOURCE)
        harness = '''
#include <cerrno>
#include <cstddef>
#include <vector>
struct _reent {};
std::vector<unsigned int> observed;
struct Sink { void operator=(unsigned int value) { observed.push_back(value); } };
Sink sink;
Sink *UART0DR = &sink;
'''+body+'''
int main() {
    char stale[] = {'a','b','X','Y',0};
    if (_write_r(NULL,1,stale,2) != 2 || observed.size()!=2 ||
        observed[0]!='a' || observed[1]!='b') return 1;
    observed.clear();
    char embedded[] = {'a',0,'b','X',0};
    if (_write_r(NULL,1,embedded,3)!=3 || observed.size()!=3 ||
        observed[0]!='a' || observed[1]!=0 || observed[2]!='b') return 2;
    observed.clear();
    if (_write_r(NULL,1,NULL,0)!=0 || !observed.empty()) return 3;
    if (_write_r(NULL,1,stale,-1)!=-1 || errno!=EINVAL || !observed.empty()) return 4;
    if (_write_r(NULL,1,NULL,1)!=-1 || errno!=EINVAL || !observed.empty()) return 5;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "uart.cpp"
            source.write_text(harness, encoding="utf-8")
            binary = root / ("uart.exe" if os.name == "nt" else "uart")
            build = subprocess.run([compiler, "-std=c++11", str(source), "-o", str(binary)],
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_uart_adapter_refuses_a_different_write_implementation(self):
        with self.assertRaisesRegex(ValueError, "not the known"):
            repair_uart_write(self.UART_SOURCE.replace("gem5_print(ptr)", "different_write(ptr,len)"))

    def test_arm_exit_initializes_both_delay_words_and_declares_asm_effects(self):
        repaired = repair_arm_exit(self.M5OPS_SOURCE)
        arm, alternate = repaired.split("#elif defined(__aarch64__)", 1)
        self.assertIn("mov r0, #0; mov r1, #0; .inst 0xEE000110 | (0x21 << 16);", arm)
        self.assertIn(': "r0", "r1", "memory"', arm)
        self.assertEqual(alternate, self.M5OPS_SOURCE.split("#elif defined(__aarch64__)", 1)[1])

    def test_arm_exit_adapter_refuses_changed_opcodes_or_architecture_branches(self):
        with self.assertRaisesRegex(ValueError, "not the known"):
            repair_arm_exit(self.M5OPS_SOURCE.replace("0x21 << 16", "0x22 << 16"))
        with self.assertRaisesRegex(ValueError, "architecture branches"):
            repair_arm_exit(self.M5OPS_SOURCE.replace("defined(__arm__)", "defined(__thumb__)"))

    def test_buffered_file_transport_uses_verified_semihosting_abi(self):
        header = (OVERLAYS / "common" / "workbench_result.h").read_text()
        self.assertIn("alignas(8) uint64_t arguments[5]", header)
        self.assertIn('operation __asm__("r0") = 0x100', header)
        self.assertIn("0x4f00", header)
        self.assertIn('".inst 0xf57ff04f; svc #0x5d57"', header)
        self.assertIn(': : "memory", "cc"', header)
        self.assertNotIn("0xEE4F0110", header)

    def test_short_file_write_is_rejected_by_guest(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("A host C++ compiler is required for file transport test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = make_fixture("gemm", "seeded", 12)
            (root / "workbench_input.h").write_text(render_input_header(fixture), encoding="utf-8")
            shutil.copyfile(OVERLAYS / "common" / "workbench_result.h", root / "workbench_result.h")
            source = root / "short.cpp"
            source.write_text('''#define SALAM_HOST_TEST_WRITEFILE(buffer,length,name) (length-1)
#include "workbench_result.h"
int main() {
    salam_result_begin();
    for(int i=0;i<SALAM_OUTPUT_COUNT;++i) salam_result_int(i,salam_expected[i]);
    salam_result_end();
    return 0;
}
''', encoding="utf-8")
            binary = root / ("short.exe" if os.name == "nt" else "short")
            build = subprocess.run([compiler, "-std=c++11", str(source), "-o", str(binary)],
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            self.assertEqual(run.stdout, "Check Failed\n")


if __name__ == "__main__":
    unittest.main()
