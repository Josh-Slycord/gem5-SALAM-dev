/**
 * Radix sort kernel
 * Ported from MachSuite for gem5-SALAM
 * Based on SHOC benchmark suite
 */
#include "sort.h"

#define BUFFER_A 0
#define BUFFER_B 1

void local_scan(int *bucket) {
    int radixID, i, bucket_indx;
    for (radixID = 0; radixID < SCAN_RADIX; radixID++) {
        for (i = 1; i < SCAN_BLOCK; i++) {
            bucket_indx = radixID * SCAN_BLOCK + i;
            bucket[bucket_indx] += bucket[bucket_indx - 1];
        }
    }
}

void sum_scan(int *sum, int *bucket) {
    int radixID, bucket_indx;
    sum[0] = 0;
    for (radixID = 1; radixID < SCAN_RADIX; radixID++) {
        bucket_indx = radixID * SCAN_BLOCK - 1;
        sum[radixID] = sum[radixID - 1] + bucket[bucket_indx];
    }
}

void last_step_scan(int *bucket, int *sum) {
    int radixID, i, bucket_indx;
    for (radixID = 0; radixID < SCAN_RADIX; radixID++) {
        for (i = 0; i < SCAN_BLOCK; i++) {
            bucket_indx = radixID * SCAN_BLOCK + i;
            bucket[bucket_indx] = bucket[bucket_indx] + sum[radixID];
        }
    }
}

void init(int *bucket) {
    int i;
    for (i = 0; i < BUCKETSIZE; i++) {
        bucket[i] = 0;
    }
}

void hist(int *bucket, int *a, int exp) {
    int blockID, i, bucket_indx, a_indx;
    for (blockID = 0; blockID < NUMOFBLOCKS; blockID++) {
        for (i = 0; i < 4; i++) {
            a_indx = blockID * ELEMENTSPERBLOCK + i;
            bucket_indx = ((a[a_indx] >> exp) & MASK) * NUMOFBLOCKS +
                          blockID + 1;
            bucket[bucket_indx]++;
        }
    }
}

void update(int *b, int *bucket, int *a, int exp) {
    int i, blockID, bucket_indx, a_indx;
    for (blockID = 0; blockID < NUMOFBLOCKS; blockID++) {
        for (i = 0; i < 4; i++) {
            int idx = blockID * ELEMENTSPERBLOCK + i;
            bucket_indx = ((a[idx] >> exp) & MASK) * NUMOFBLOCKS + blockID;
            a_indx = blockID * ELEMENTSPERBLOCK + i;
            b[bucket[bucket_indx]] = a[a_indx];
            bucket[bucket_indx]++;
        }
    }
}

void ss_sort(int *a, int *b, int *bucket, int *sum) {
    int exp = 0;
    int valid_buffer = 0;

    for (exp = 0; exp < 32; exp += 2) {
        init(bucket);
        if (valid_buffer == BUFFER_A) {
            hist(bucket, a, exp);
        } else {
            hist(bucket, b, exp);
        }

        local_scan(bucket);
        sum_scan(sum, bucket);
        last_step_scan(bucket, sum);

        if (valid_buffer == BUFFER_A) {
            update(b, bucket, a, exp);
            valid_buffer = BUFFER_B;
        } else {
            update(a, bucket, b, exp);
            valid_buffer = BUFFER_A;
        }
    }
}

/* SALAM top entry point */
void top() {
    int *a = (int *)ARRAY_A_ADDR;
    int *b = (int *)ARRAY_B_ADDR;
    int *bucket = (int *)BUCKET_ADDR;
    int *sum = (int *)SUM_ADDR;

    ss_sort(a, b, bucket, sum);
}
