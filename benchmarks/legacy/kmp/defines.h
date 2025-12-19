#ifndef KMP_DEFINES_H
#define KMP_DEFINES_H

#include <stdint.h>

/* KMP parameters - matching MachSuite */
#define PATTERN_SIZE 4
#define STRING_SIZE  32411

/* SPM Base Address */
#define SPM_BASE     0x2f100000

/* Memory layout:
 * pattern: 4 bytes
 * kmpNext: 4 * 4 = 16 bytes
 * n_matches: 4 bytes
 * input: 32411 bytes
 */
#define PATTERN_ADDR   (SPM_BASE + 0x000)
#define KMPNEXT_ADDR   (SPM_BASE + 0x010)
#define NMATCHES_ADDR  (SPM_BASE + 0x020)
#define INPUT_ADDR     (SPM_BASE + 0x100)

#endif /* KMP_DEFINES_H */
