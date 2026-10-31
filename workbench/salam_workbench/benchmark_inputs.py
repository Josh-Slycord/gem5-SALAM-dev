"""Source-bound staged inputs and complete accelerator output for breadth runs.

Only independently staged workspaces may be passed to this adapter. It changes
guest input/check/output code, preserving the accelerator C kernels. Supported
dimensions are deliberately bounded by the original benchmark contracts.
"""
import hashlib
import json
import math
import os
import re
from pathlib import Path

from .benchmark_oracles import reference_outputs, validate_fixture

PROJECT = Path(__file__).resolve().parents[1]
OVERLAYS = PROJECT / "experiments" / "breadth" / "overlays"
SUPPORTED = frozenset(("gemm", "fft", "stencil3d"))
SHAPES = {
    "gemm": {"ROW": "8", "COL": "8"},
    "fft": {"FFT_SIZE": "1024"},
    "stencil3d": {"ROW": "16", "COL": "32", "HYT": "32", "C_SIZE": "2"},
}
_WRITE_BODY = """int _write_r (struct _reent *r, int file, char * ptr, int len)
{
    (void)r;
    (void)file;
    if (len < 0 || (ptr == NULL && len > 0)) {
        errno = EINVAL;
        return -1;
    }
    // newlib writes length-delimited buffers; bytes after len may be stale.
    for (int i = 0; i < len; ++i)
        *UART0DR = (unsigned int)(unsigned char)ptr[i];
    return len;
}"""
_ARM_EXIT_BODY = """static void m5_exit(void)
{
    // ARM32 passes the uint64_t nanosecond delay in r0:r1. Clear both words.
    __asm__ __volatile__ (
        "mov r0, #0; mov r1, #0; .inst 0xEE000110 | (0x21 << 16);"
        :
        :
        : "r0", "r1", "memory");
};"""


def repair_uart_write(source):
    """Repair only the known recovered newlib write-hook implementation."""
    matches = list(re.finditer(r"int\s+_write_r\s*\([^)]*\)\s*\{[^{}]*\}", source))
    if len(matches) != 1:
        raise ValueError("Staged UART write hook has changed")
    match = matches[0]
    expected = (
        "int_write_r(struct_reent*r,intfile,char*ptr,intlen)"
        "{r=r;file=file;ptr=ptr;gem5_print(ptr);returnlen;}"
    )
    if re.sub(r"\s+", "", match.group()) != expected:
        raise ValueError(
            "Staged UART write hook is not the known unbounded implementation"
        )
    return source[: match.start()] + _WRITE_BODY + source[match.end() :]


def repair_arm_exit(source):
    """Bind the known ARM32 exit opcode to a complete zero-delay ABI argument."""
    arm, separator, other_architectures = source.partition("#elif defined(__aarch64__)")
    if not separator or arm.count("#if defined(__arm__)") != 1:
        raise ValueError("Staged m5ops architecture branches have changed")
    pattern = re.compile(
        r"static\s+void\s+m5_exit\s*\(\s*\)\s*\{\s*"
        r"__asm__\s+__volatile__\s*\(\s*"
        r'"mov r0, #0; \.inst 0xEE000110 \| \(0x21 << 16\);"\s*\);\s*\};'
    )
    if len(list(pattern.finditer(arm))) != 1:
        raise ValueError(
            "Staged ARM32 m5_exit is not the known incomplete-delay implementation"
        )
    return pattern.sub(_ARM_EXIT_BODY, arm) + separator + other_architectures


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(path, workspace):
    return {
        "path": path.relative_to(workspace).as_posix(),
        "sha256": _hash(path),
        "bytes": path.stat().st_size,
    }


def _safe_file(path, root):
    path = Path(path)
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if (
        resolved != Path(os.path.normpath(str(path)))
        or path.is_symlink()
        or not path.is_file()
    ):
        raise ValueError(
            "Benchmark adapter requires regular staged files: " + str(path)
        )
    return path


def _array(name, values, kind):
    if kind == "double":

        def literal(value):
            if not math.isfinite(value):
                raise ValueError("Nonfinite fixture value")
            text = format(value, ".17g")
            return text if "." in text or "e" in text.lower() else text + ".0"

    else:

        def literal(value):
            # Parenthesized INT32_MIN avoids an unsigned decimal literal.
            return "(-2147483647 - 1)" if value == -(2**31) else str(value)

    lines = ["static const {} {}[{}] = {{".format(kind, name, len(values))]
    for offset in range(0, len(values), 8):
        lines.append(
            "    " + ", ".join(literal(v) for v in values[offset : offset + 8]) + ","
        )
    lines.append("};")
    return "\n".join(lines)


def render_input_header(fixture, *, inject_mismatch=False, force_guest_pass=False):
    """Render deterministic input and gold data; never substitute observed data."""
    validate_fixture(fixture)
    if type(inject_mismatch) is not bool or type(force_guest_pass) is not bool:
        raise ValueError("Negative-control flags must be booleans")
    benchmark = fixture["benchmark"]
    if benchmark not in SUPPORTED:
        raise ValueError("Unsupported breadth benchmark")
    outputs = reference_outputs(fixture)
    data = fixture["inputs"]
    lines = [
        "// Generated only in a staged workload workspace; inputs are host oracle data.",
        "#ifndef SALAM_WORKBENCH_INPUT_H",
        "#define SALAM_WORKBENCH_INPUT_H",
        "#include <cstdint>",
        '#define SALAM_FIXTURE_SHA256 "{}"'.format(fixture["fixture_sha256"]),
        '#define SALAM_BENCHMARK "{}"'.format(benchmark),
        '#define SALAM_OUTPUT_KIND "{}"'.format(fixture["output_kind"]),
        "#define SALAM_OUTPUT_COUNT {}".format(fixture["output_count"]),
        "#define SALAM_OUTPUT_HEX_WIDTH {}".format(
            32 if fixture["output_kind"] == "complex128" else 8
        ),
        "#define SALAM_INJECT_MISMATCH {}".format(int(inject_mismatch)),
        "#define SALAM_FORCE_GUEST_PASS {}".format(int(force_guest_pass)),
    ]
    if benchmark == "gemm":
        lines.extend(
            (
                _array("salam_a", data["a"], "int32_t"),
                _array("salam_b", data["b"], "int32_t"),
                _array("salam_expected", outputs, "int32_t"),
            )
        )
    elif benchmark == "fft":
        for key in ("real", "imag", "real_twid", "imag_twid"):
            lines.append(_array("salam_" + key, data[key], "double"))
        lines.extend(
            (
                _array("salam_expected_real", [v[0] for v in outputs], "double"),
                _array("salam_expected_imag", [v[1] for v in outputs], "double"),
            )
        )
    else:
        lines.extend(
            (
                _array("salam_input", data["input"], "int32_t"),
                _array("salam_coefficients", data["coefficients"], "int32_t"),
                _array("salam_expected", outputs, "int32_t"),
            )
        )
    lines.extend(("#endif", ""))
    return "\n".join(lines)


LEGACY_WRITEFILE_ABI = "gem5_21_semipseudo_arm32_u64_slots_v1"
MODERN_WRITEFILE_ABI = "gem5_26_semipseudo_arm32_u32_slots_v1"
LEGACY_RESULT_HEADER_SHA256 = (
    "31e407229f8d837774bdb501deea2fc3b49df8dc76232820e89d4a4af26bb744"
)
_MODERN_WRITEFILE_BODY = """// Transport ABI: gem5_26_semipseudo_arm32_u32_slots_v1.
static bool salam_pack_gem5_26_write_arguments(uint32_t arguments[5],
        uint64_t buffer, uint64_t length, uint64_t offset, uint64_t filename) {
    const uint64_t max_word = static_cast<uint64_t>(0xffffffffu);
    if (buffer > max_word || length > max_word || offset > max_word || filename > max_word)
        return false;
    arguments[0] = 0x4f00u;
    arguments[1] = static_cast<uint32_t>(buffer);
    arguments[2] = static_cast<uint32_t>(length);
    arguments[3] = static_cast<uint32_t>(offset);
    arguments[4] = static_cast<uint32_t>(filename);
    return true;
}

static uint64_t salam_write_result_file(const char *buffer, uint32_t length) {
#if defined(SALAM_HOST_TEST_WRITEFILE)
    // Explicit test callback only; production ARM guests use the selected ABI.
    return SALAM_HOST_TEST_WRITEFILE(buffer, length, "salam-results.txt");
#elif defined(__arm__) && !defined(__thumb__)
    static_assert(sizeof(uintptr_t) == 4, "Transport requires ARM32 pointers");
    // gem5 26 Abi32 uses packed 32-bit slots and skips exactly one op slot.
    alignas(4) uint32_t arguments[5];
    static_assert(sizeof(arguments) == 20, "Expected five packed 32-bit slots");
    if (!salam_pack_gem5_26_write_arguments(arguments,
            static_cast<uint64_t>(reinterpret_cast<uintptr_t>(buffer)),
            static_cast<uint64_t>(length), 0,
            static_cast<uint64_t>(reinterpret_cast<uintptr_t>("salam-results.txt"))))
        return ~static_cast<uint64_t>(0);
    register uint32_t operation __asm__("r0") = 0x100;
    register uint32_t parameter_block __asm__("r1") =
        static_cast<uint32_t>(reinterpret_cast<uintptr_t>(arguments));
    // DSB publishes the complete buffer and block before the native pseudo-op.
    __asm__ __volatile__(".inst 0xf57ff04f; svc #0x5d57"
                         : "+r"(operation), "+r"(parameter_block)
                         : : "memory", "cc");
    return operation;
#else
#error "Result transport requires ARM32 ARM-state or an explicit host test callback"
#endif
}

"""


def render_result_header(template, output_abi=LEGACY_WRITEFILE_ABI):
    """Legacy is byte-preserving; the modern writer is an explicit checked port."""
    if output_abi == LEGACY_WRITEFILE_ABI:
        return template
    if output_abi != MODERN_WRITEFILE_ABI:
        raise ValueError("Unsupported result transport ABI")
    if (
        hashlib.sha256(template.encode("utf-8")).hexdigest()
        != LEGACY_RESULT_HEADER_SHA256
    ):
        raise ValueError(
            "Legacy result template differs from the source-bound ABI port"
        )
    start = "static uint64_t salam_write_result_file("
    end = "static void salam_result_begin()"
    if template.count(start) != 1 or template.count(end) != 1:
        raise ValueError("Result transport function anchors are ambiguous")
    first, last = template.index(start), template.index(end)
    return template[:first] + _MODERN_WRITEFILE_BODY + "\n" + template[last:]


def stage_benchmark_inputs(
    workspace,
    benchmark,
    fixture,
    *,
    inject_mismatch=False,
    force_guest_pass=False,
    output_abi=LEGACY_WRITEFILE_ABI,
):
    """Apply a reproducible guest-only overlay to one staged benchmark.

    Call after topology/address generation and cluster-header rebinding, before
    compiling guest/IR. ``benchmark`` accepts a name or its canonical relative
    benchmark path. The caller owns enforcing isolation from preserved engines.
    """
    if output_abi not in (LEGACY_WRITEFILE_ABI, MODERN_WRITEFILE_ABI):
        raise ValueError("Unsupported result transport ABI")
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("A regular staged workspace is required")
    if benchmark in SUPPORTED:
        name = benchmark
    elif benchmark in ("benchmarks/sys_validation/" + item for item in SUPPORTED):
        name = benchmark.rsplit("/", 1)[-1]
    else:
        raise ValueError(
            "Breadth input adapter requires a supported sys_validation path"
        )
    validate_fixture(fixture)
    if fixture["benchmark"] != name:
        raise ValueError("Fixture benchmark does not match configured benchmark")
    base = workspace / "benchmarks" / "sys_validation" / name
    definitions = _safe_file(base / "defines.h", workspace)
    macros = dict(
        re.findall(
            r"^#define\s+(\w+)\s+([^\n]+)$",
            definitions.read_text(encoding="utf-8"),
            re.M,
        )
    )
    for macro, expected in SHAPES[name].items():
        if macros.get(macro, "").strip() != expected:
            raise ValueError("Unsupported benchmark dimension: " + macro)
    main = _safe_file(base / "sw" / "main.cpp", workspace)
    bench = _safe_file(base / "sw" / "bench.h", workspace)
    kernel = _safe_file(base / "hw" / (name + ".c"), workspace)
    syscalls = _safe_file(workspace / "benchmarks" / "common" / "syscalls.c", workspace)
    syscall_source = repair_uart_write(syscalls.read_text(encoding="utf-8"))
    m5ops = _safe_file(workspace / "benchmarks" / "common" / "m5ops.h", workspace)
    m5ops_source = repair_arm_exit(m5ops.read_text(encoding="utf-8"))
    includes = []
    for source in (main, bench):
        includes.extend(
            re.findall(
                r'^#include\s+"(\.\./[A-Za-z0-9_-]+_hw_defines\.h)"',
                source.read_text(encoding="utf-8"),
                re.M,
            )
        )
    includes = sorted(set(includes))
    if len(includes) != 1:
        raise ValueError("Expected one source-bound generated cluster header")
    header = _safe_file(base / "sw" / includes[0], workspace)
    before = [
        _record(path, workspace)
        for path in (definitions, main, bench, kernel, header, syscalls, m5ops)
    ]
    payload = render_input_header(
        fixture, inject_mismatch=inject_mismatch, force_guest_pass=force_guest_pass
    )
    generated = base / "sw" / "workbench_input.h"
    if generated.exists():
        raise ValueError("Refusing to overwrite an existing breadth input header")
    template = _safe_file(OVERLAYS / name / "sw" / "main.cpp", PROJECT)
    source = template.read_text(encoding="utf-8")
    if source.count("@CLUSTER_HEADER@") != 1:
        raise ValueError("Invalid breadth guest template")
    source = source.replace("@CLUSTER_HEADER@", includes[0])
    common_template = _safe_file(OVERLAYS / "common" / "workbench_result.h", PROJECT)
    common_header = base / "sw" / "workbench_result.h"
    if common_header.exists():
        raise ValueError("Refusing to overwrite an existing breadth result header")
    planned = [
        (generated, payload),
        (main, source),
        (syscalls, syscall_source),
        (m5ops, m5ops_source),
        (
            common_header,
            render_result_header(
                common_template.read_text(encoding="utf-8"), output_abi
            ),
        ),
    ]
    changed = [path for path, _ in planned]
    templates = [template, common_template]
    if name == "stencil3d":
        makefile = _safe_file(base / "hw" / "Makefile", workspace)
        before.append(_record(makefile, workspace))
        original = makefile.read_text(encoding="utf-8")
        token = "clang -O1 -S "
        if original.count(token) != 1:
            raise ValueError("Stencil IR build command has changed")
        if "-target" not in original:
            original = original.replace(token, token + "-target armv7-pc-none-eabi ")
        elif "-target armv7-pc-none-eabi" not in original:
            raise ValueError("Stencil IR build has a different target")
        planned.append((makefile, original))
        changed.append(makefile)
    for path, text in planned:
        with path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(text)
    if _hash(kernel) != next(
        r["sha256"] for r in before if r["path"].endswith("/hw/" + name + ".c")
    ):
        raise ValueError("Accelerator kernel changed while staging input overlay")
    return {
        "schema_version": 1,
        "kind": "breadth_benchmark_inputs",
        "benchmark": name,
        "fixture_sha256": fixture["fixture_sha256"],
        "dimensions": fixture["shape"],
        "inject_mismatch": inject_mismatch,
        "force_guest_pass": force_guest_pass,
        "source_inputs": before,
        "templates": [_record(path, PROJECT) for path in templates],
        "outputs": [_record(path, workspace) for path in changed],
        "kernel_preserved": True,
        "protocol": "salam_result_hex_v1",
        "output_transport": "gem5_semihosting_writefile_text_v1",
        "output_transport_abi": output_abi,
        "output_transport_header": _record(common_header, workspace),
        "output_transport_template_sha256": _hash(common_template),
        "output_relative": "simulator/salam-results.txt",
        "uart_write_contract": "newlib_length_delimited_bytes",
        "m5_exit_contract": "arm32_zero_delay_r0_r1_with_register_memory_clobbers",
        "measurement_scope": "Explicit guest stats dump follows completion and guest checker, before raw-output serialization; direct SALAM lifecycle is a separate accelerator interval.",
    }
