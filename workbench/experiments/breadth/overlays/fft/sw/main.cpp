// Staged guest for fixed-size, varied-input configurable complex FFT experiments.
#include <cstdio>
#include <cstdint>
#include "../defines.h"
#include "@CLUSTER_HEADER@"
#include "../../../common/m5ops.h"
#include "workbench_result.h"

static_assert(FFT_SIZE == 1024, "Only the declared 1024-point FFT is supported");
volatile int stage;
volatile uint8_t * top = (uint8_t *)(TOP);
volatile uint32_t * loc_real = (uint32_t *)(TOP + 1);
volatile uint32_t * loc_imag = (uint32_t *)(TOP + 9);
volatile uint32_t * loc_real_twid = (uint32_t *)(TOP + 17);
volatile uint32_t * loc_imag_twid = (uint32_t *)(TOP + 25);

int __attribute__((optimize("0"))) main(void) {
    m5_reset_stats();
    const uint32_t base = 0x80c00000;
    double *real = (double *)base;
    double *imag = (double *)(base + 8 * FFT_SIZE);
    double *real_twid = (double *)(base + 16 * FFT_SIZE);
    double *imag_twid = (double *)(base + 20 * FFT_SIZE);
    for (int i = 0; i < FFT_SIZE; ++i) {
        real[i] = salam_real[i];
        imag[i] = salam_imag[i];
    }
    for (int i = 0; i < FFT_HALF; ++i) {
        real_twid[i] = salam_real_twid[i];
        imag_twid[i] = salam_imag_twid[i];
    }
    volatile int wait_count = 0;
    stage = 0;
    *loc_real = (uint32_t)(void *)real;
    *loc_imag = (uint32_t)(void *)imag;
    *loc_real_twid = (uint32_t)(void *)real_twid;
    *loc_imag_twid = (uint32_t)(void *)imag_twid;
    *top = 1;
    while (stage < 1) ++wait_count;
    if (SALAM_INJECT_MISMATCH) real[0] += 1.0;
    bool failed = false;
    for (int i = 0; i < FFT_SIZE; ++i)
        if (!salam_float_matches(real[i], salam_expected_real[i]) ||
            !salam_float_matches(imag[i], salam_expected_imag[i])) failed = true;
    salam_check_marker(failed);
    m5_dump_stats();
    salam_result_begin();
    for (int i = 0; i < FFT_SIZE; ++i) salam_result_complex(i, real[i], imag[i]);
    salam_result_end();
    m5_exit();
}
