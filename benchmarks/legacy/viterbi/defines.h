#ifndef VITERBI_DEFINES_H
#define VITERBI_DEFINES_H

#include <stdint.h>

/* Viterbi parameters - matching MachSuite */
#define N_STATES  64
#define N_OBS     140
#define N_TOKENS  64

#define TYPE double
typedef uint8_t tok_t;
typedef TYPE prob_t;
typedef uint8_t state_t;
typedef int32_t step_t;

/* SPM Base Address */
#define SPM_BASE     0x2f100000

/* Memory layout:
 * obs: 140 bytes
 * path: 140 bytes
 * init: 64 * 8 = 512 bytes
 * transition: 64 * 64 * 8 = 32768 bytes
 * emission: 64 * 64 * 8 = 32768 bytes
 */
#define OBS_ADDR         (SPM_BASE + 0x0000)
#define PATH_ADDR        (SPM_BASE + 0x0100)
#define INIT_ADDR        (SPM_BASE + 0x0200)
#define TRANSITION_ADDR  (SPM_BASE + 0x0400)
#define EMISSION_ADDR    (SPM_BASE + 0x8400)

#endif /* VITERBI_DEFINES_H */
