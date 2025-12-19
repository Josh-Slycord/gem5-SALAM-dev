/**
 * Radix Sort Host Driver for gem5-SALAM
 * Radix sort algorithm from MachSuite
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../../common/dma.h"
#include "../../common/m5ops.h"
#include "../defines.h"

/* Host data buffers */
static int32_t a[SIZE];
static int32_t b[SIZE];
static int32_t bucket[BUCKETSIZE];
static int32_t sum[SCAN_RADIX];

/* Generate random unsorted data */
void genData(void)
{
    for (int i = 0; i < SIZE; i++) {
        a[i] = rand() % 10000;
    }
    memset(b, 0, sizeof(b));
    memset(bucket, 0, sizeof(bucket));
    memset(sum, 0, sizeof(sum));
}

/* Verify array is sorted */
int checkData(void)
{
    for (int i = 1; i < SIZE; i++) {
        if (a[i] < a[i - 1]) {
            return 1;  /* Not sorted */
        }
    }
    return 0;  /* Sorted */
}

int main(void)
{
    m5_reset_stats();

    /* SPM pointers */
    int32_t *spm_a = (int32_t *)ARRAY_A_ADDR;
    int32_t *spm_b = (int32_t *)ARRAY_B_ADDR;
    int32_t *spm_bucket = (int32_t *)BUCKET_ADDR;
    int32_t *spm_sum = (int32_t *)SUM_ADDR;

    printf("Generating radix sort test data\n");
    srand(42);
    genData();
    printf("Data generated - %d elements\n", SIZE);

    /* Print first few unsorted values */
    printf("Before sort: %d, %d, %d, %d, %d...\n",
           a[0], a[1], a[2], a[3], a[4]);

    /* Copy data to SPM via DMA */
    dmacpy(spm_a, a, sizeof(a));
    while (!pollDma());
    resetDma();

    dmacpy(spm_b, b, sizeof(b));
    while (!pollDma());
    resetDma();

    dmacpy(spm_bucket, bucket, sizeof(bucket));
    while (!pollDma());
    resetDma();

    dmacpy(spm_sum, sum, sizeof(sum));
    while (!pollDma());
    resetDma();

    printf("Starting radix sort accelerator\n");

    /* Start accelerator */
    *acc = 0x01;

    /* Wait for completion */
    while (*acc != 0x4) {
        /* spin */
    }

    printf("Radix sort complete\n");

    /* Copy result back */
    dmacpy(a, spm_a, sizeof(a));
    while (!pollDma());

    *acc = 0x00;

    /* Print first few sorted values */
    printf("After sort: %d, %d, %d, %d, %d...\n",
           a[0], a[1], a[2], a[3], a[4]);

    /* Verify */
    if (checkData() == 0) {
        printf("Radix sort SUCCESS - array is sorted\n");
    } else {
        printf("Radix sort FAILED - array not sorted\n");
    }

    m5_dump_stats();
    m5_exit();
    return 0;
}
