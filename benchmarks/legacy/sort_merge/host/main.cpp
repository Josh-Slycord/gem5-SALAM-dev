/**
 * Merge Sort Host Driver for gem5-SALAM
 * Merge sort algorithm from MachSuite
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../../common/dma.h"
#include "../../common/m5ops.h"
#include "../defines.h"

/* Host data buffer */
static TYPE a[SIZE];

/* Generate random unsorted data */
void genData(void)
{
    for (int i = 0; i < SIZE; i++) {
        a[i] = rand() % 10000;
    }
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

    /* SPM pointer */
    TYPE *spm_a = (TYPE *)ARRAY_ADDR;

    printf("Generating merge sort test data\n");
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

    printf("Starting merge sort accelerator\n");

    /* Start accelerator */
    *acc = 0x01;

    /* Wait for completion */
    while (*acc != 0x4) {
        /* spin */
    }

    printf("Merge sort complete\n");

    /* Copy result back */
    dmacpy(a, spm_a, sizeof(a));
    while (!pollDma());

    *acc = 0x00;

    /* Print first few sorted values */
    printf("After sort: %d, %d, %d, %d, %d...\n",
           a[0], a[1], a[2], a[3], a[4]);

    /* Verify */
    if (checkData() == 0) {
        printf("Merge sort SUCCESS - array is sorted\n");
    } else {
        printf("Merge sort FAILED - array not sorted\n");
    }

    m5_dump_stats();
    m5_exit();
    return 0;
}
