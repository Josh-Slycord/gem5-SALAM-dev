/**
 * KMP string matching kernel
 * Ported from MachSuite for gem5-SALAM
 * Based on http://www-igm.univ-mlv.fr/~lecroq/string/node8.html
 */
#include "kmp.h"

/* Compute Prefix Function */
void CPF(char *pattern, int32_t *kmpNext) {
    int32_t k, q;
    k = 0;
    kmpNext[0] = 0;

    for (q = 1; q < PATTERN_SIZE; q++) {
        while (k > 0 && pattern[k] != pattern[q]) {
            k = kmpNext[q];
        }
        if (pattern[k] == pattern[q]) {
            k++;
        }
        kmpNext[q] = k;
    }
}

/* KMP string matching */
int kmp(char *pattern, char *input, int32_t *kmpNext, int32_t *n_matches) {
    int32_t i, q;
    n_matches[0] = 0;

    CPF(pattern, kmpNext);

    q = 0;
    for (i = 0; i < STRING_SIZE; i++) {
        while (q > 0 && pattern[q] != input[i]) {
            q = kmpNext[q];
        }
        if (pattern[q] == input[i]) {
            q++;
        }
        if (q >= PATTERN_SIZE) {
            n_matches[0]++;
            q = kmpNext[q - 1];
        }
    }
    return 0;
}

/* SALAM top entry point */
void top() {
    char *pattern = (char *)PATTERN_ADDR;
    char *input = (char *)INPUT_ADDR;
    int32_t *kmpNext = (int32_t *)KMPNEXT_ADDR;
    int32_t *n_matches = (int32_t *)NMATCHES_ADDR;

    kmp(pattern, input, kmpNext, n_matches);
}
