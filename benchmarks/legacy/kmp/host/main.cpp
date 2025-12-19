/**
 * KMP String Matching Host Driver for gem5-SALAM
 * Knuth-Morris-Pratt algorithm from MachSuite
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../../common/dma.h"
#include "../../common/m5ops.h"
#include "../defines.h"

/* Host data buffers */
static char pattern[PATTERN_SIZE];
static int32_t kmpNext[PATTERN_SIZE];
static int32_t n_matches;
static char input[STRING_SIZE];

/* Generate test data with known pattern occurrences */
void genData(void)
{
    /* Pattern to search for */
    pattern[0] = a;
    pattern[1] = b;
    pattern[2] = a;
    pattern[3] = b;

    /* Initialize kmpNext (failure function) */
    kmpNext[0] = -1;
    for (int i = 1; i < PATTERN_SIZE; i++) {
        kmpNext[i] = 0;
    }

    /* Generate input string with some embedded patterns */
    for (int i = 0; i < STRING_SIZE; i++) {
        input[i] = a + (rand() % 4);
    }

    /* Insert known patterns at specific locations */
    memcpy(&input[100], "abab", 4);
    memcpy(&input[500], "abab", 4);
    memcpy(&input[1000], "abab", 4);

    n_matches = 0;
}

int main(void)
{
    m5_reset_stats();

    /* SPM pointers */
    char *spm_pattern = (char *)PATTERN_ADDR;
    int32_t *spm_kmpNext = (int32_t *)KMPNEXT_ADDR;
    int32_t *spm_n_matches = (int32_t *)NMATCHES_ADDR;
    char *spm_input = (char *)INPUT_ADDR;

    printf("Generating KMP test data\n");
    srand(42);
    genData();
    printf("Data generated - searching for abab pattern\n");

    /* Copy data to SPM via DMA */
    dmacpy(spm_pattern, pattern, PATTERN_SIZE);
    while (!pollDma());
    resetDma();

    dmacpy(spm_kmpNext, kmpNext, sizeof(kmpNext));
    while (!pollDma());
    resetDma();

    *spm_n_matches = 0;

    dmacpy(spm_input, input, STRING_SIZE);
    while (!pollDma());
    resetDma();

    printf("Starting KMP accelerator\n");

    /* Start accelerator */
    *acc = 0x01;

    /* Wait for completion */
    while (*acc != 0x4) {
        /* spin */
    }

    printf("KMP search complete\n");

    /* Read result */
    n_matches = *spm_n_matches;

    *acc = 0x00;

    printf("KMP found %d matches\n", n_matches);
    if (n_matches >= 3) {
        printf("KMP SUCCESS - found expected patterns\n");
    } else {
        printf("KMP result: %d matches found\n", n_matches);
    }

    m5_dump_stats();
    m5_exit();
    return 0;
}
