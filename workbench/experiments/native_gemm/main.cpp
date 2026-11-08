// SPDX-License-Identifier: BSD-3-Clause
// Two-launch numerical transport for the retained/direct factory study.
#include <cstdio>
#include <cstdint>
#include "bench.h"
#include "../../../common/m5ops.h"
#include "../gemm_clstr_hw_defines.h"
static_assert(ROW == 8 && COL == 8, "Declared GEMM shape is 8x8");
static_assert(sizeof(TYPE) == 4, "Declared int32 GEMM");
volatile uint8_t *top = (uint8_t *)(TOP);
volatile uint32_t *val_a = (uint32_t *)(TOP + 1);
volatile uint32_t *val_b = (uint32_t *)(TOP + 9);
volatile uint32_t *val_c = (uint32_t *)(TOP + 17);
static const int input_a[2][64] = {@INPUT_A@};
static const int input_b[2][64] = {@INPUT_B@};
static const char *fixture_hashes[2] = {@HASHES@};

// The retained _write_r ignores its length and prints to NUL. Avoid printf's
// non-NUL-terminated internal chunks in this external qualification transport.
static void uart_text(const char *text) {
    volatile unsigned int *uart = (volatile unsigned int *)0x1c090000;
    while (*text) *uart = (unsigned char)*text++;
}
static void uart_unsigned(unsigned int value) {
    char digits[10];
    unsigned int size = 0;
    do { digits[size++] = (char)('0' + value % 10); value /= 10; } while (value);
    while (size) {
        char character[2] = {digits[--size], 0};
        uart_text(character);
    }
}
static void uart_hex(uint32_t value) {
    const char *alphabet = "0123456789abcdef";
    for (unsigned int index = 0; index < 8; ++index) {
        char character[2] = {alphabet[(value >> (28 - 4 * index)) & 15], 0};
        uart_text(character);
    }
}
static void result_identity(const char *prefix, const char *hash) {
    uart_text(prefix); uart_text(" v1 gemm "); uart_text(hash);
    uart_text(" 64 int32\n");
}
int __attribute__((optimize("0"))) main(void) {
    const uint32_t base = 0x80c00000;
    TYPE *a = (TYPE *)base;
    TYPE *b = (TYPE *)(base + 8 * ROW * COL);
    TYPE *c = (TYPE *)(base + 16 * ROW * COL);
    for (int invocation = 0; invocation < 2; ++invocation) {
        // Reset between complete launches; invocation IDs remain lifetime IDs.
        m5_reset_stats();
        for (int i = 0; i < 64; ++i) {
            a[i] = input_a[invocation][i];
            b[i] = input_b[invocation][i];
            c[i] = 0x5a5a5a5a;
        }
        stage = 0;
        volatile unsigned int wait_count = 0;
        *val_a = (uint32_t)(void *)a;
        *val_b = (uint32_t)(void *)b;
        *val_c = (uint32_t)(void *)c;
        *top = 1;
        while (stage < 1) ++wait_count;
#ifdef RESET_INJECT_MISMATCH
        if (invocation == 1) c[0] ^= 1;
#endif
        bool failed = false;
        // This guest-side CPU reference reads the real input memory.
        for (int row = 0; row < 8; ++row)
            for (int col = 0; col < 8; ++col) {
                int expected = 0;
                for (int inner = 0; inner < 8; ++inner)
                    expected += a[row * 8 + inner] * b[inner * 8 + col];
                if (c[row * 8 + col] != expected) failed = true;
            }
        uart_text("RESET_INVOCATION_BEGIN "); uart_unsigned(invocation + 1);
        uart_text("\n");
#ifdef NATIVE_GEMM_FORCE_GUEST_PASS
        uart_text("Check Passed\n");
#else
        uart_text(failed ? "Check Failed\n" : "Check Passed\n");
#endif
        result_identity("SALAM_RESULT_BEGIN", fixture_hashes[invocation]);
        for (int index = 0; index < 64; ++index) {
            uart_text("SALAM_RESULT "); uart_unsigned(index); uart_text(" ");
            uart_hex((uint32_t)c[index]); uart_text("\n");
        }
        result_identity("SALAM_RESULT_END", fixture_hashes[invocation]);
        uart_text("RESET_INVOCATION_END "); uart_unsigned(invocation + 1);
        uart_text("\n");
        m5_dump_stats();
    }
    m5_exit();
}
