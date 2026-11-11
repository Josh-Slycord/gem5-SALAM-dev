// SPDX-License-Identifier: BSD-3-Clause
// Tiny vector addition: the CPU stages inputs, never computes into outputs.
#include <cstdio>
#include <cstdint>
#include "../defines.h"
#include "@CLUSTER_HEADER@"
#include "../../../common/m5ops.h"
#include "workbench_result.h"

static_assert(sizeof(TYPE) == VADD_ELEMENT_BYTES, "VADD width mismatch");
static_assert(VADD_LENGTH == SALAM_OUTPUT_COUNT, "VADD shape mismatch");
static_assert(VADD_LENGTH >= 1 && VADD_LENGTH <= 256, "VADD length range");
volatile int stage;
volatile uint8_t *top = (volatile uint8_t *)TOP;

static void write_argument(unsigned int offset, uintptr_t value)
{
    // Byte writes avoid unaligned 64-bit stores to flag+8-byte argument slots.
    for (unsigned int i = 0; i < 8; ++i) {
        volatile uint8_t *byte = (volatile uint8_t *)(TOP + offset + i);
        *byte = i < 4 ? (uint8_t)(value >> (8 * i)) : 0;
    }
}

int __attribute__((optimize("0"))) main(void)
{
    m5_reset_stats();
    const uintptr_t base = 0x80c00000;
    TYPE *a = (TYPE *)base;
    TYPE *b = (TYPE *)(base + VADD_ELEMENT_BYTES * VADD_LENGTH);
    TYPE *c = (TYPE *)(base + 2 * VADD_ELEMENT_BYTES * VADD_LENGTH);
    for (int i = 0; i < VADD_LENGTH; ++i) {
        a[i] = salam_a[i];
        b[i] = salam_b[i];
        c[i] = 0x5a5a5a5a;
    }
    stage = 0;
    write_argument(1, (uintptr_t)a);
    write_argument(9, (uintptr_t)b);
    write_argument(17, (uintptr_t)c);
    *top = 1;
    volatile unsigned int wait_count = 0;
    while (stage < 1 && wait_count < 1000000) ++wait_count;
    if (stage < 1) {
        printf("VADD accelerator timeout\nCheck Failed\n");
        m5_exit();
        return 1;
    }
    if (SALAM_INJECT_MISMATCH) c[0] ^= 1;
    bool failed = false;
    for (int i = 0; i < VADD_LENGTH; ++i)
        if (c[i] != salam_expected[i]) failed = true;
    salam_check_marker(failed);
    m5_dump_stats();
    if (SALAM_VADD_VERBOSE)
        for (int i = 0; i < VADD_LENGTH; ++i)
            printf("VADD[%d] %ld + %ld -> %ld\n", i,
                   (long)a[i], (long)b[i], (long)c[i]);
    salam_result_begin();
    for (int i = 0; i < VADD_LENGTH; ++i) salam_result_int(i, c[i]);
    salam_result_end();
    m5_exit();
    return 0;
}
