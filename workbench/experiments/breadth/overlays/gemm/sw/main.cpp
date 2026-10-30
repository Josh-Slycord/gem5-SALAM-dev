// Staged guest for fixed-size, varied-input configurable GEMM experiments.
#include <cstdio>
#include <cstdint>
#include "../defines.h"
#include "@CLUSTER_HEADER@"
#include "../../../common/m5ops.h"
#include "workbench_result.h"

static_assert(ROW == 8 && COL == 8, "Only the declared 8x8 GEMM shape is supported");
static_assert(sizeof(TYPE) == sizeof(int32_t), "GEMM requires signed int32 storage");
volatile int stage;
volatile uint8_t * top = (uint8_t *)(TOP);
volatile uint32_t * val_a = (uint32_t *)(TOP + 1);
volatile uint32_t * val_b = (uint32_t *)(TOP + 9);
volatile uint32_t * val_c = (uint32_t *)(TOP + 17);

int __attribute__((optimize("0"))) main(void) {
    m5_reset_stats();
    const uint32_t base = 0x80c00000;
    TYPE *a = (TYPE *)base;
    TYPE *b = (TYPE *)(base + 8 * ROW * COL);
    TYPE *c = (TYPE *)(base + 16 * ROW * COL);
    for (int i = 0; i < ROW * COL; ++i) {
        a[i] = salam_a[i];
        b[i] = salam_b[i];
        c[i] = 0x5a5a5a5a;
    }
    volatile int wait_count = 0;
    stage = 0;
    *val_a = (uint32_t)(void *)a;
    *val_b = (uint32_t)(void *)b;
    *val_c = (uint32_t)(void *)c;
    *top = 1;
    while (stage < 1) ++wait_count;
    if (SALAM_INJECT_MISMATCH) c[0] ^= 1;
    bool failed = false;
    for (int i = 0; i < ROW * COL; ++i)
        if (c[i] != salam_expected[i]) failed = true;
    salam_check_marker(failed);
    m5_dump_stats();
    salam_result_begin();
    for (int i = 0; i < ROW * COL; ++i) salam_result_int(i, c[i]);
    salam_result_end();
    m5_exit();
}
