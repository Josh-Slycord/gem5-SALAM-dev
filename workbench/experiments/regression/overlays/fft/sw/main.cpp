#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include "bench.h"
#include "../../../common/m5ops.h"
#include "../fft_clstr_hw_defines.h"

fft_struct ffts;

#define BASE            0x80c00000

#define REAL_OFFSET     0
#define IMG_OFFSET      8*FFT_SIZE
#define RTWID_OFFSET    16*FFT_SIZE
#define ITWID_OFFSET    20*FFT_SIZE
#define RCHK_OFFSET     24*FFT_SIZE
#define ICHK_OFFSET     32*FFT_SIZE

volatile uint8_t  * top           = (uint8_t  *)(TOP);
volatile uint32_t * loc_real      = (uint32_t *)(TOP+1);
volatile uint32_t * loc_img       = (uint32_t *)(TOP+9);
volatile uint32_t * loc_real_twid = (uint32_t *)(TOP+17);
volatile uint32_t * loc_img_twid  = (uint32_t *)(TOP+25);

static bool workbench_fft_sample_matches(double observed, double expected) {
    if (!std::isfinite(observed) || !std::isfinite(expected))
        return false;
    const double difference = observed - expected;
    return std::isfinite(difference) && std::fabs(difference) <= EPSILON;
}

int __attribute__ ((optimize("0"))) main(void) {
    m5_reset_stats();
	double *real       	= (double *)(BASE+REAL_OFFSET);
	double *img        	= (double *)(BASE+IMG_OFFSET);
	double *real_twid  	= (double *)(BASE+RTWID_OFFSET);
	double *img_twid   	= (double *)(BASE+ITWID_OFFSET);
	double *real_check 	= (double *)(BASE+RCHK_OFFSET);
	double *img_check  	= (double *)(BASE+ICHK_OFFSET);

    volatile int count = 0;
    stage = 0;

    ffts.real       = real;
    ffts.img        = img;
    ffts.real_twid  = real_twid;
    ffts.img_twid   = img_twid;
    ffts.real_check = real_check;
    ffts.img_check  = img_check;

    printf("Generating data\n");
    genData(&ffts);
    printf("Data generated\n");

    *loc_real       = (uint32_t)(void *)real;
	*loc_img        = (uint32_t)(void *)img;
	*loc_real_twid  = (uint32_t)(void *)real_twid;
	*loc_img_twid   = (uint32_t)(void *)img_twid;

    *top = 0x01;
    while (stage < 1) count++;

    printf("Job complete\n");

#ifdef CHECK
    bool fail = false;
    for (int i = 0; i < FFT_SIZE; i++) {
        if (!workbench_fft_sample_matches(real[i], real_check[i])) {
            printf("FFT mismatch index %d component real\n", i);
            fail = true;
            break;
        }
        if (!workbench_fft_sample_matches(img[i], img_check[i])) {
            printf("FFT mismatch index %d component imaginary\n", i);
            fail = true;
            break;
        }
    }
    if(fail)
        printf("Check Failed\n");
    else
        printf("Check Passed\n");
#endif
    m5_dump_stats();
    m5_exit();
}
