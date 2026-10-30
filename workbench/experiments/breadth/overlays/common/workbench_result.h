// Complete observed-output protocol for independently checked SALAM experiments.
#ifndef SALAM_WORKBENCH_RESULT_H
#define SALAM_WORKBENCH_RESULT_H
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cmath>
#include "workbench_input.h"

static_assert(sizeof(uint32_t) == 4, "Expected 32-bit words");
static_assert(sizeof(double) == 8, "Expected IEEE binary64 storage");
static_assert(SALAM_OUTPUT_COUNT > 0 && SALAM_OUTPUT_COUNT <= 16384,
              "Output shape exceeds bounded file transport");

// Maximum 5-digit row index, 8/32 hex digits and framing. Stencil uses <460 KiB.
static const size_t salam_result_capacity =
    (SALAM_OUTPUT_HEX_WIDTH + 20) * SALAM_OUTPUT_COUNT + 512;
static char salam_result_buffer[salam_result_capacity];
static size_t salam_result_length = 0;
static int salam_result_rows = 0;
static bool salam_result_failed = false;

static void salam_append_bytes(const char *data, size_t count) {
    if (salam_result_failed) return;
    if (count > salam_result_capacity - salam_result_length) {
        salam_result_failed = true;
        return;
    }
    std::memcpy(salam_result_buffer + salam_result_length, data, count);
    salam_result_length += count;
}

static void salam_append_text(const char *text) {
    salam_append_bytes(text, std::strlen(text));
}

static void salam_append_unsigned(unsigned int value) {
    char digits[10];
    unsigned int count = 0;
    do {
        digits[count++] = static_cast<char>('0' + value % 10);
        value /= 10;
    } while (value != 0);
    while (count != 0) salam_append_bytes(&digits[--count], 1);
}

static void salam_append_hex(uint32_t value) {
    static const char alphabet[] = "0123456789abcdef";
    char digits[8];
    for (unsigned int i = 0; i < 8; ++i)
        digits[i] = alphabet[(value >> (28 - 4 * i)) & 15];
    salam_append_bytes(digits, sizeof(digits));
}

static void salam_append_identity(const char *prefix) {
    salam_append_text(prefix);
    salam_append_text(" v1 " SALAM_BENCHMARK " " SALAM_FIXTURE_SHA256 " ");
    salam_append_unsigned(SALAM_OUTPUT_COUNT);
    salam_append_text(" " SALAM_OUTPUT_KIND "\n");
}

static uint64_t salam_write_result_file(const char *buffer, uint32_t length) {
#if defined(SALAM_HOST_TEST_WRITEFILE)
    // Explicit test callback only; production ARM guests use the verified ABI.
    return SALAM_HOST_TEST_WRITEFILE(buffer, length, "salam-results.txt");
#elif defined(__arm__) && !defined(__thumb__)
    static_assert(sizeof(uintptr_t) == 4, "Transport requires the verified ARM32 ABI");
    // This gem5's SemiPseudoAbi32 uses 64-bit slots and skips the first op slot.
    // Ordinary m5_write_file's register ABI cannot carry all four arguments.
    alignas(8) uint64_t arguments[5] = {
        0x4f00, static_cast<uint64_t>(reinterpret_cast<uintptr_t>(buffer)),
        length, 0,
        static_cast<uint64_t>(reinterpret_cast<uintptr_t>("salam-results.txt"))
    };
    register uint32_t operation __asm__("r0") = 0x100;
    register uint32_t parameter_block __asm__("r1") =
        static_cast<uint32_t>(reinterpret_cast<uintptr_t>(arguments));
    // Encoded ARMv7 DSB SY drains buffer stores. The old compiler's default ISA
    // does not accept the mnemonic, while this recorded simulated CPU does.
    __asm__ __volatile__(".inst 0xf57ff04f; svc #0x5d57"
                         : "+r"(operation), "+r"(parameter_block)
                         : : "memory", "cc");
    return operation;
#else
#error "Result transport requires ARM32 ARM-state or an explicit host test callback"
#endif
}

static void salam_result_begin() {
    salam_result_length = 0;
    salam_result_rows = 0;
    salam_result_failed = false;
    salam_append_identity("SALAM_RESULT_BEGIN");
}

static void salam_result_end() {
    if (salam_result_rows != SALAM_OUTPUT_COUNT) salam_result_failed = true;
    salam_append_identity("SALAM_RESULT_END");
    if (salam_result_failed ||
        salam_write_result_file(salam_result_buffer,
                                static_cast<uint32_t>(salam_result_length)) != salam_result_length) {
        printf("Check Failed\n");
        return;
    }
    printf("SALAM file saved: salam-results.txt\n");
}

static void salam_result_int(int index, int32_t observed) {
    if (SALAM_OUTPUT_HEX_WIDTH != 8 || index != salam_result_rows || index >= SALAM_OUTPUT_COUNT) {
        salam_result_failed = true;
        return;
    }
    salam_append_text("SALAM_RESULT ");
    salam_append_unsigned(static_cast<unsigned int>(index));
    salam_append_text(" ");
    salam_append_hex(static_cast<uint32_t>(observed));
    salam_append_text("\n");
    ++salam_result_rows;
}

static void salam_result_complex(int index, double real, double imag) {
    // ARMv7 guest memory is little endian; avoid float printf and aliasing UB.
    uint32_t real_words[2], imag_words[2];
    std::memcpy(real_words, &real, sizeof(real));
    std::memcpy(imag_words, &imag, sizeof(imag));
    if (SALAM_OUTPUT_HEX_WIDTH != 32 || index != salam_result_rows || index >= SALAM_OUTPUT_COUNT) {
        salam_result_failed = true;
        return;
    }
    salam_append_text("SALAM_RESULT ");
    salam_append_unsigned(static_cast<unsigned int>(index));
    salam_append_text(" ");
    salam_append_hex(real_words[1]);
    salam_append_hex(real_words[0]);
    salam_append_hex(imag_words[1]);
    salam_append_hex(imag_words[0]);
    salam_append_text("\n");
    ++salam_result_rows;
}

static bool salam_float_matches(double observed, double expected) {
    if (!std::isfinite(observed) || !std::isfinite(expected)) return false;
    const double error = std::fabs(observed - expected);
    return std::isfinite(error) && error <= 1.0e-6 + 1.0e-9 * std::fabs(expected);
}

static void salam_check_marker(bool failed) {
    if (SALAM_FORCE_GUEST_PASS) failed = false;
    if (failed) printf("Check Failed\n");
    else printf("Check Passed\n");
}
#endif
