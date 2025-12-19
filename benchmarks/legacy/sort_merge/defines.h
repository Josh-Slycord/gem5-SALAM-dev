#ifndef SORT_MERGE_DEFINES_H
#define SORT_MERGE_DEFINES_H

#include <stdint.h>

/* Merge sort parameters - matching MachSuite */
#define SIZE 2048
#define TYPE int32_t
#define TYPE_MAX INT32_MAX

/* SPM Base Address */
#define SPM_BASE     0x2f100000

/* Memory layout:
 * a: 2048 * 4 = 8192 bytes
 */
#define ARRAY_ADDR   (SPM_BASE + 0x000)

#endif /* SORT_MERGE_DEFINES_H */
