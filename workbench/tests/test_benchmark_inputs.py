"""Staged isolation, identity, and cross-language output checks for breadth runs."""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from salam_workbench.benchmark_inputs import (
    LEGACY_WRITEFILE_ABI,
    MODERN_WRITEFILE_ABI,
    OVERLAYS,
    render_input_header,
    repair_arm_exit,
    repair_uart_write,
    stage_benchmark_inputs,
)
from salam_workbench.benchmark_oracles import assess_output, make_fixture


class BenchmarkInputTests(unittest.TestCase):
    M5OPS_SOURCE = """#if defined(__arm__)
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
"""
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
            "vadd": (
                "#include <stdint.h>\n#define TYPE int32_t\n"
                "#define VADD_LENGTH 8\n#define VADD_ELEMENT_BYTES 4\n"
            ),
            "stencil3d": "#define ROW 16\n#define COL 32\n#define HYT 32\n#define C_SIZE 2\n",
        }
        (base / "defines.h").write_text(definitions[benchmark], encoding="utf-8")
        (base / "sw" / "main.cpp").write_text(
            '#include "../' + cluster + '_hw_defines.h"\n', encoding="utf-8"
        )
        (base / "sw" / "bench.h").write_text(
            "// Source guest definitions\n", encoding="utf-8"
        )
        (base / (cluster + "_hw_defines.h")).write_text(
            "#define TOP 0x10020000\n", encoding="utf-8"
        )
        (base / "hw" / (benchmark + ".c")).write_text(
            "// Preserve kernel bytes\n", encoding="utf-8"
        )
        (base / "hw" / "Makefile").write_text(
            "KERN=stencil3d.c top.c\nbuild:\n\tclang -O1 -S -emit-llvm $(KERN)\n",
            encoding="utf-8",
        )
        return base

    def _vadd_fixture(self):
        return make_fixture(
            "vadd",
            "custom",
            37,
            length=7,
            inputs={
                "a": [1, -3, 4, 0, 2147483647, -2147483648, 17],
                "b": [2, -4, 6, -1, -1, 1, -17],
            },
        )

    def test_vadd_staging_rewrites_shared_length_before_guest_and_kernel_preprocessing(
        self,
    ):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("A host compiler is required to witness shared dimensions")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = self._source(root, "vadd", cluster="vadd_clstr")
            actual = (
                Path(__file__).resolve().parents[2] / "benchmarks/sys_validation/vadd"
            )
            for filename in ("vadd.c", "top.c", "hw_defines.h"):
                shutil.copyfile(actual / "hw" / filename, base / "hw" / filename)
            kernel = base / "hw/vadd.c"
            top = base / "hw/top.c"
            original_top = top.read_bytes()
            original_kernel = kernel.read_bytes()
            original_definitions = (base / "defines.h").read_bytes()
            fixture = self._vadd_fixture()
            receipt = stage_benchmark_inputs(
                root,
                "benchmarks/sys_validation/vadd",
                fixture,
                output_abi=MODERN_WRITEFILE_ABI,
                verbose=True,
            )
            self.assertEqual(kernel.read_bytes(), original_kernel)
            self.assertEqual(top.read_bytes(), original_top)
            self.assertTrue(receipt["kernel_preserved"])
            self.assertIn("#define VADD_LENGTH 7\n", (base / "defines.h").read_text())
            self.assertEqual(receipt["dimensions"], {"length": 7})
            before = next(
                item
                for item in receipt["source_inputs"]
                if item["path"].endswith("/defines.h")
            )
            after = next(
                item
                for item in receipt["outputs"]
                if item["path"].endswith("/defines.h")
            )
            self.assertEqual(
                before["sha256"], hashlib.sha256(original_definitions).hexdigest()
            )
            self.assertEqual(
                after["sha256"],
                hashlib.sha256((base / "defines.h").read_bytes()).hexdigest(),
            )
            self.assertNotEqual(before["sha256"], after["sha256"])
            for source, language in (
                (base / "sw/main.cpp", "c++"),
                (kernel, "c"),
                (top, "c"),
            ):
                witness = subprocess.run(
                    [
                        compiler,
                        "-x",
                        language,
                        "-E",
                        "-dM",
                        "-DSALAM_HOST_TEST_WRITEFILE=0",
                        str(source),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(witness.returncode, 0, witness.stderr)
                macros = dict(
                    line.split(maxsplit=2)[1:]
                    for line in witness.stdout.splitlines()
                    if line.startswith("#define ") and len(line.split(maxsplit=2)) == 3
                )
                self.assertEqual(macros["VADD_LENGTH"], "7")
                self.assertEqual(macros["VADD_ELEMENT_BYTES"], "4")
                self.assertEqual(macros["TYPE"], "int32_t")
            header = (base / "sw/workbench_input.h").read_text()
            self.assertIn("#define SALAM_OUTPUT_COUNT 7", header)
            self.assertIn("#define SALAM_VADD_VERBOSE 1", header)
            self.assertIn("static const int32_t salam_a[7]", header)
            self.assertIn("static const int32_t salam_b[7]", header)
            quiet = render_input_header(fixture)
            self.assertEqual(
                header.replace(
                    "#define SALAM_VADD_VERBOSE 1", "#define SALAM_VADD_VERBOSE 0"
                ),
                quiet,
            )
            with self.assertRaisesRegex(ValueError, "boolean"):
                render_input_header(fixture, verbose=1)

    def test_vadd_explicit_transport_selects_source_receipt_path_and_abi(self):
        for transport, abi, protocol_abi, relative in (
            (
                "file",
                MODERN_WRITEFILE_ABI,
                MODERN_WRITEFILE_ABI,
                "simulator/salam-results.txt",
            ),
            (
                "file",
                LEGACY_WRITEFILE_ABI,
                LEGACY_WRITEFILE_ABI,
                "simulator/salam-results.txt",
            ),
            (
                "uart",
                MODERN_WRITEFILE_ABI,
                "uart_newlib_length_delimited_v1",
                "simulator/system.terminal",
            ),
        ):
            with self.subTest(
                transport=transport, abi=abi
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                base = self._source(root, "vadd")
                receipt = stage_benchmark_inputs(
                    root,
                    "vadd",
                    self._vadd_fixture(),
                    output_abi=abi,
                    output_transport=transport,
                )
                self.assertEqual(
                    receipt["output_transport"],
                    "uart_text_v1"
                    if transport == "uart"
                    else "gem5_semihosting_writefile_text_v1",
                )
                self.assertEqual(receipt["output_transport_abi"], protocol_abi)
                self.assertEqual(receipt["output_relative"], relative)
                source = (base / "sw/workbench_result.h").read_text()
                end = source[
                    source.index("static void salam_result_end()") : source.index(
                        "static void salam_result_int("
                    )
                ]
                if transport == "uart":
                    self.assertIn("std::fwrite(salam_result_buffer", end)
                    self.assertIn("std::fflush(stdout)", end)
                    self.assertNotIn("salam_write_result_file", end)
                else:
                    self.assertIn("salam_write_result_file", end)
                    self.assertNotIn("std::fwrite", end)
                if abi == MODERN_WRITEFILE_ABI:
                    self.assertIn("alignas(4) uint32_t arguments[5]", source)
                else:
                    self.assertIn("alignas(8) uint64_t arguments[5]", source)
                self.assertEqual(
                    receipt["output_transport_header"]["sha256"],
                    hashlib.sha256(
                        (base / "sw/workbench_result.h").read_bytes()
                    ).hexdigest(),
                )

    def test_non_vadd_diagnostic_controls_reject_without_staging_changes(self):
        for options in (
            {"verbose": True},
            {"output_transport": "uart"},
            {"verbose": 1},
            {"output_transport": "auto"},
        ):
            with self.subTest(
                options=options
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                base = self._source(root, "gemm")
                original = (base / "sw/main.cpp").read_bytes()
                with self.assertRaises(ValueError):
                    stage_benchmark_inputs(
                        root, "gemm", make_fixture("gemm"), **options
                    )
                self.assertEqual((base / "sw/main.cpp").read_bytes(), original)
                self.assertFalse((base / "sw/workbench_input.h").exists())
                self.assertFalse((base / "sw/workbench_result.h").exists())

    def test_actual_staged_vadd_cpp_serializers_emit_every_observed_word(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("A host C++ compiler is required for transport behavior")
        for transport in ("file", "uart"):
            for corrupt in (False, True):
                with self.subTest(
                    transport=transport, corrupt=corrupt
                ), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary).resolve()
                    base = self._source(root, "vadd")
                    fixture = self._vadd_fixture()
                    stage_benchmark_inputs(
                        root,
                        "vadd",
                        fixture,
                        output_abi=MODERN_WRITEFILE_ABI,
                        output_transport=transport,
                    )
                    # This executes the actual staged serializer with manually
                    # calculated observed values, not its expected-data array.
                    source = base / "sw/transport.cpp"
                    source.write_text(
                        "#include <cstdio>\n#include <cstdint>\n#include <cstring>\n"
                        "static unsigned file_calls = 0;\n"
                        "static uint64_t host_write(const char *b, uint32_t n, const char *name) {\n"
                        "    ++file_calls;\n"
                        '    if (std::strcmp(name, "salam-results.txt")) return 0;\n'
                        "    return std::fwrite(b, 1, n, stdout);\n"
                        "}\n"
                        "#define SALAM_HOST_TEST_WRITEFILE(b,n,name) host_write(b,n,name)\n"
                        '#include "workbench_result.h"\n'
                        "int main() {\n"
                        '    static_assert(sizeof(salam_a[0]) == 4, "int32 input width");\n'
                        "    int32_t observed[] = {3,-7,10,-1,2147483646,-2147483647,0};\n"
                        + ("    observed[6] = 99;\n" if corrupt else "")
                        + "    salam_result_begin();\n"
                        "    for (int i=0; i<SALAM_OUTPUT_COUNT; ++i) salam_result_int(i, observed[i]);\n"
                        "    salam_result_end();\n"
                        + "    return file_calls == "
                        + ("0" if transport == "uart" else "1")
                        + " ? 0 : 9;\n"
                        "}\n",
                        encoding="utf-8",
                    )
                    binary = root / (
                        "transport.exe" if os.name == "nt" else "transport"
                    )
                    build = subprocess.run(
                        [compiler, "-std=c++11", str(source), "-o", str(binary)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    self.assertEqual(build.returncode, 0, build.stderr)
                    run = subprocess.run(
                        [str(binary)], capture_output=True, text=True, timeout=20
                    )
                    self.assertEqual(run.returncode, 0, run.stderr)
                    rows = [
                        line
                        for line in run.stdout.splitlines()
                        if line.startswith("SALAM_RESULT ")
                    ]
                    self.assertEqual(len(rows), 7)
                    self.assertEqual(
                        len(
                            [
                                line
                                for line in run.stdout.splitlines()
                                if line.startswith("SALAM_RESULT_BEGIN")
                            ]
                        ),
                        1,
                    )
                    self.assertEqual(
                        len(
                            [
                                line
                                for line in run.stdout.splitlines()
                                if line.startswith("SALAM_RESULT_END")
                            ]
                        ),
                        1,
                    )
                    assessment = assess_output(run.stdout, fixture)
                    self.assertEqual(
                        assessment["state"],
                        "failed" if corrupt else "passed",
                        assessment,
                    )
                    self.assertEqual(assessment["compared_count"], 7)
                    self.assertEqual(assessment["mismatch_count"], 1 if corrupt else 0)

    def test_all_supported_workloads_preserve_kernels_and_bind_header_identity(self):
        for benchmark in ("gemm", "fft", "stencil3d"):
            with self.subTest(
                benchmark=benchmark
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                base = self._source(root, benchmark)
                kernel = base / "hw" / (benchmark + ".c")
                before = kernel.read_bytes()
                fixture = make_fixture(benchmark, "seeded", 71)
                receipt = stage_benchmark_inputs(root, benchmark, fixture)
                self.assertTrue(receipt["kernel_preserved"])
                self.assertEqual(kernel.read_bytes(), before)
                self.assertEqual(receipt["fixture_sha256"], fixture["fixture_sha256"])
                self.assertEqual(
                    receipt["uart_write_contract"], "newlib_length_delimited_bytes"
                )
                self.assertEqual(
                    receipt["m5_exit_contract"],
                    "arm32_zero_delay_r0_r1_with_register_memory_clobbers",
                )
                main = (base / "sw" / "main.cpp").read_text(encoding="utf-8")
                self.assertIn('#include "../custom_clstr_hw_defines.h"', main)
                self.assertNotIn("@CLUSTER_HEADER@", main)
                self.assertIn(
                    fixture["fixture_sha256"],
                    (base / "sw" / "workbench_input.h").read_text(),
                )
                for entry in receipt["outputs"]:
                    self.assertEqual(
                        entry["sha256"],
                        hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest(),
                    )
                if benchmark == "stencil3d":
                    self.assertIn(
                        "-target armv7-pc-none-eabi",
                        (base / "hw" / "Makefile").read_text(),
                    )

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
            result = stage_benchmark_inputs(
                root, "benchmarks/sys_validation/gemm", make_fixture("gemm")
            )
            self.assertEqual(result["benchmark"], "gemm")
            with self.assertRaisesRegex(ValueError, "supported sys_validation"):
                stage_benchmark_inputs(
                    root, "benchmarks/legacy/gemm", make_fixture("gemm")
                )

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
        header = render_input_header(
            make_fixture("gemm"), inject_mismatch=True, force_guest_pass=True
        )
        self.assertIn("#define SALAM_INJECT_MISMATCH 1", header)
        self.assertIn("#define SALAM_FORCE_GUEST_PASS 1", header)
        with self.assertRaisesRegex(ValueError, "booleans"):
            render_input_header(make_fixture("gemm"), inject_mismatch=1)

    def test_guest_templates_serialize_actual_buffers_and_bound_output_windows(self):
        for benchmark, emitter in (
            ("gemm", "salam_result_int(i, c[i])"),
            ("fft", "salam_result_complex(i, real[i], imag[i])"),
            ("stencil3d", "salam_result_int(i, output[i])"),
        ):
            with self.subTest(benchmark=benchmark):
                main = (OVERLAYS / benchmark / "sw" / "main.cpp").read_text()
                self.assertIn(emitter, main)
                self.assertLess(
                    main.index("while (stage < 1)"), main.index("salam_check_marker")
                )
                self.assertLess(
                    main.index("m5_dump_stats();"), main.index("salam_result_begin();")
                )
                self.assertLess(
                    main.index("salam_result_end();"), main.index("m5_exit();")
                )
                output_section = main[main.index("salam_result_begin();") :]
                self.assertNotIn("salam_expected", output_section)

    def test_cpp_emitter_round_trips_actual_integer_and_binary64_representations(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest(
                "A host C++ compiler is required for cross-language transport test"
            )
        for benchmark in ("gemm", "fft", "stencil3d"):
            with self.subTest(
                benchmark=benchmark
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                fixture = make_fixture(benchmark, "boundary", 12)
                (root / "workbench_input.h").write_text(
                    render_input_header(fixture), encoding="utf-8"
                )
                shutil.copyfile(
                    OVERLAYS / "common" / "workbench_result.h",
                    root / "workbench_result.h",
                )
                emit = (
                    "salam_result_complex(i, salam_expected_real[i], salam_expected_imag[i]);"
                    if benchmark == "fft"
                    else "salam_result_int(i, salam_expected[i]);"
                )
                source = root / "transport.cpp"
                source.write_text(
                    "#include <cstdio>\n"
                    "#define SALAM_HOST_TEST_WRITEFILE(buffer,length,name) std::fwrite(buffer,1,length,stdout)\n"
                    '#include "workbench_result.h"\nint main() {\n'
                    "salam_result_begin();\n"
                    "for (int i=0; i<SALAM_OUTPUT_COUNT; ++i) " + emit + "\n"
                    "salam_result_end();\nreturn 0;\n}\n",
                    encoding="utf-8",
                )
                binary = root / ("transport.exe" if os.name == "nt" else "transport")
                build = subprocess.run(
                    [compiler, "-std=c++11", str(source), "-o", str(binary)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                run = subprocess.run(
                    [str(binary)], capture_output=True, text=True, timeout=20
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                assessment = assess_output(run.stdout, fixture)
                self.assertEqual(assessment["state"], "passed", assessment)

    def test_repaired_newlib_write_honors_length_including_embedded_nul(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest(
                "A host C++ compiler is required for UART write contract test"
            )
        actual_syscalls = (
            Path(__file__).resolve().parents[2] / "benchmarks" / "common" / "syscalls.c"
        ).read_text(encoding="utf-8")
        body_from_legacy = repair_uart_write(self.UART_SOURCE)
        body_from_actual = repair_uart_write(actual_syscalls)
        self.assertIn(body_from_legacy.strip(), body_from_actual)
        harness = (
            """
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <vector>
struct _reent { int _errno; };
std::vector<unsigned int> observed;
struct Sink { void operator=(unsigned int value) { observed.push_back(value); } };
Sink sink;
Sink *UART0DR = &sink;
"""
            + body_from_legacy
            + """
int main() {
    struct _reent ctx = {0};
    // 1. Non-terminated slice with trailing canary bytes.
    char stale[] = {'a','b','X','Y'};
    errno = 0;
    if (_write_r(&ctx, 1, stale, 2) != 2 || ctx._errno != 0 || errno != 0 ||
        observed.size() != 2 || observed[0] != 'a' || observed[1] != 'b')
        return 1;
    observed.clear();

    // 2. Embedded NUL byte preserved across full requested length.
    char embedded[] = {'a', 0, 'b', 'X'};
    if (_write_r(&ctx, 1, embedded, 3) != 3 || ctx._errno != 0 || errno != 0 ||
        observed.size() != 3 || observed[0] != 'a' || observed[1] != 0 ||
        observed[2] != 'b')
        return 2;
    observed.clear();

    // 3. len == 0 returns 0 without dereferencing NULL or invalid pointer.
    char *unmapped = reinterpret_cast<char *>(static_cast<uintptr_t>(0x1u));
    if (_write_r(&ctx, 1, NULL, 0) != 0 || ctx._errno != 0 || errno != 0 ||
        !observed.empty())
        return 3;
    if (_write_r(&ctx, 1, unmapped, 0) != 0 || ctx._errno != 0 || errno != 0 ||
        !observed.empty())
        return 4;

    // 4. len < 0 returns -1 and reports EINVAL through _reent and errno.
    ctx._errno = 0;
    errno = 0;
    if (_write_r(&ctx, 1, stale, -1) != -1 || ctx._errno != EINVAL ||
        errno != EINVAL || !observed.empty())
        return 5;
    errno = 0;
    if (_write_r(NULL, 1, unmapped, -5) != -1 || errno != EINVAL ||
        !observed.empty())
        return 6;

    // 5. Null buffer with positive length returns -1 and reports EFAULT.
    ctx._errno = 0;
    errno = 0;
    if (_write_r(&ctx, 1, NULL, 1) != -1 || ctx._errno != EFAULT ||
        errno != EFAULT || !observed.empty())
        return 7;
    errno = 0;
    if (_write_r(NULL, 1, NULL, 4) != -1 || errno != EFAULT ||
        !observed.empty())
        return 8;
    return 0;
}
"""
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "uart.cpp"
            source.write_text(harness, encoding="utf-8")
            binary = root / ("uart.exe" if os.name == "nt" else "uart")
            build = subprocess.run(
                [compiler, "-std=c++11", str(source), "-o", str(binary)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=20
            )
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_uart_adapter_refuses_a_different_write_implementation(self):
        with self.assertRaisesRegex(ValueError, "not the known"):
            repair_uart_write(
                self.UART_SOURCE.replace("gem5_print(ptr)", "different_write(ptr,len)")
            )
        actual_syscalls = (
            Path(__file__).resolve().parents[2] / "benchmarks" / "common" / "syscalls.c"
        ).read_text(encoding="utf-8")
        self.assertEqual(repair_uart_write(actual_syscalls), actual_syscalls)
        for tampered in (
            actual_syscalls.replace("EFAULT", "EINVAL"),
            actual_syscalls.replace("if (len == 0)\n        return 0;\n", ""),
            actual_syscalls
            + "\nint _write_r(struct _reent *r, int f, char *p, int n) { return 0; }\n",
        ):
            with self.subTest(tampered=tampered[:40]):
                with self.assertRaises(ValueError):
                    repair_uart_write(tampered)

    def test_arm_exit_initializes_both_delay_words_and_declares_asm_effects(self):
        repaired = repair_arm_exit(self.M5OPS_SOURCE)
        arm, alternate = repaired.split("#elif defined(__aarch64__)", 1)
        self.assertIn("mov r0, #0; mov r1, #0; .inst 0xEE000110 | (0x21 << 16);", arm)
        self.assertIn(': "r0", "r1", "memory"', arm)
        self.assertEqual(
            alternate, self.M5OPS_SOURCE.split("#elif defined(__aarch64__)", 1)[1]
        )

    def test_arm_exit_adapter_refuses_changed_opcodes_or_architecture_branches(self):
        with self.assertRaisesRegex(ValueError, "not the known"):
            repair_arm_exit(self.M5OPS_SOURCE.replace("0x21 << 16", "0x22 << 16"))
        with self.assertRaisesRegex(ValueError, "architecture branches"):
            repair_arm_exit(
                self.M5OPS_SOURCE.replace("defined(__arm__)", "defined(__thumb__)")
            )

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
            (root / "workbench_input.h").write_text(
                render_input_header(fixture), encoding="utf-8"
            )
            shutil.copyfile(
                OVERLAYS / "common" / "workbench_result.h", root / "workbench_result.h"
            )
            source = root / "short.cpp"
            source.write_text(
                """#define SALAM_HOST_TEST_WRITEFILE(buffer,length,name) (length-1)
#include "workbench_result.h"
int main() {
    salam_result_begin();
    for(int i=0;i<SALAM_OUTPUT_COUNT;++i) salam_result_int(i,salam_expected[i]);
    salam_result_end();
    return 0;
}
""",
                encoding="utf-8",
            )
            binary = root / ("short.exe" if os.name == "nt" else "short")
            build = subprocess.run(
                [compiler, "-std=c++11", str(source), "-o", str(binary)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=20
            )
            self.assertEqual(run.stdout, "Check Failed\n")


if __name__ == "__main__":
    unittest.main()
