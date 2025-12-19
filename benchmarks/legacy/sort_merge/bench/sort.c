/**
 * Merge sort kernel
 * Ported from MachSuite for gem5-SALAM
 */
#include "sort.h"

void merge(TYPE *a, int start, int m, int stop) {
    TYPE temp[SIZE];
    int i, j, k;

    for (i = start; i <= m; i++) {
        temp[i] = a[i];
    }

    for (j = m + 1; j <= stop; j++) {
        temp[m + 1 + stop - j] = a[j];
    }

    i = start;
    j = stop;

    for (k = start; k <= stop; k++) {
        TYPE tmp_j = temp[j];
        TYPE tmp_i = temp[i];
        if (tmp_j < tmp_i) {
            a[k] = tmp_j;
            j--;
        } else {
            a[k] = tmp_i;
            i++;
        }
    }
}

void ms_mergesort(TYPE *a) {
    int start, stop;
    int i, m, from, mid, to;

    start = 0;
    stop = SIZE;

    for (m = 1; m < stop - start; m += m) {
        for (i = start; i < stop; i += m + m) {
            from = i;
            mid = i + m - 1;
            to = i + m + m - 1;
            if (to < stop) {
                merge(a, from, mid, to);
            } else {
                merge(a, from, mid, stop);
            }
        }
    }
}

/* SALAM top entry point */
void top() {
    TYPE *a = (TYPE *)ARRAY_ADDR;
    ms_mergesort(a);
}
