/**
 * Hardware defines for viterbi benchmark
 * Cluster: viterbi_clstr
 */

#ifndef VITERBI_HW_DEFINES_H
#define VITERBI_HW_DEFINES_H

/* Memory Base Addresses */
#define BASE_ADDRESS 0x10020000

/* DMA Configurations */
#define MAIN_DMA_MAX_REQ_SIZE 128
#define MAIN_DMA_BUFFER_SIZE 256

/* Accelerator Configurations */
#define COMPUTE_UNIT_PIO_SIZE 32

/* Viterbi specific */
#define N_STATES_VAL 64
#define N_OBS_VAL 140
#define N_TOKENS_VAL 64
#define TRANSITION_SIZE_BYTES 32768
#define EMISSION_SIZE_BYTES 32768

#endif /* VITERBI_HW_DEFINES_H */
