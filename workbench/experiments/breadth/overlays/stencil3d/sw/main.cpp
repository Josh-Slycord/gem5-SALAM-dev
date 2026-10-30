// Staged guest for fixed-size, varied-input configurable seven-point stencil.
#include <cstdio>
#include <cstdint>
#include "../defines.h"
#include "@CLUSTER_HEADER@"
#include "../../../common/m5ops.h"
#include "workbench_result.h"

static_assert(ROW == 16 && COL == 32 && HYT == 32 && C_SIZE == 2,
              "Only the declared 16x32x32 stencil shape is supported");
static_assert(sizeof(TYPE) == sizeof(int32_t), "Stencil requires int32 storage");
volatile int stage;
volatile uint8_t * top = (uint8_t *)(TOP);
volatile uint32_t * loc_coefficients = (uint32_t *)(TOP + 1);
volatile uint32_t * loc_input = (uint32_t *)(TOP + 9);
volatile uint32_t * loc_output = (uint32_t *)(TOP + 17);

int __attribute__((optimize("0"))) main(void) {
    m5_reset_stats();
    const uint32_t base = 0x80c00000;
    TYPE *coefficients = (TYPE *)base;
    TYPE *input = (TYPE *)(base + sizeof(TYPE) * C_SIZE);
    TYPE *output = (TYPE *)(base + sizeof(TYPE) * (C_SIZE + SIZE));
    for (int i = 0; i < C_SIZE; ++i) coefficients[i] = salam_coefficients[i];
    for (int i = 0; i < SIZE; ++i) {
        input[i] = salam_input[i];
        output[i] = 0x5a5a5a5a;
    }
    volatile int wait_count = 0;
    stage = 0;
    *loc_coefficients = (uint32_t)(void *)coefficients;
    *loc_input = (uint32_t)(void *)input;
    *loc_output = (uint32_t)(void *)output;
    *top = 1;
    while (stage < 1) ++wait_count;
    if (SALAM_INJECT_MISMATCH) output[0] ^= 1;
    bool failed = false;
    for (int i = 0; i < SIZE; ++i)
        if (output[i] != salam_expected[i]) failed = true;
    salam_check_marker(failed);
    m5_dump_stats();
    salam_result_begin();
    for (int i = 0; i < SIZE; ++i) salam_result_int(i, output[i]);
    salam_result_end();
    m5_exit();
}
