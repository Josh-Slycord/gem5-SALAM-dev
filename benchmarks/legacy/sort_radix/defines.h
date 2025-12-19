#ifndef SORT_RADIX_DEFINES_H
#define SORT_RADIX_DEFINES_H

#include <stdint.h>

/* Radix sort parameters - matching MachSuite */
#define SIZE 2048
#define NUMOFBLOCKS 512
#define ELEMENTSPERBLOCK 4
#define RADIXSIZE 4
#define BUCKETSIZE (NUMOFBLOCKS * RADIXSIZE)
#define MASK 0x3
#define SCAN_BLOCK 16
#define SCAN_RADIX (BUCKETSIZE / SCAN_BLOCK)

/* SPM Base Address */
#define SPM_BASE     0x2f100000

/* Memory layout:
 * a: 2048 * 4 = 8192 bytes
 * b: 2048 * 4 = 8192 bytes
 * bucket: 2048 * 4 = 8192 bytes
 * sum: 128 * 4 = 512 bytes
 */
#define ARRAY_A_ADDR   (SPM_BASE + 0x0000)
#define ARRAY_B_ADDR   (SPM_BASE + 0x2000)
#define BUCKET_ADDR    (SPM_BASE + 0x4000)
#define SUM_ADDR       (SPM_BASE + 0x6000)

#endif /* SORT_RADIX_DEFINES_H */
