/**
 * Hardware defines for KMP benchmark
 * Cluster: kmp_clstr
 */

#ifndef KMP_HW_DEFINES_H
#define KMP_HW_DEFINES_H

/* Memory Base Addresses */
#define BASE_ADDRESS 0x10020000

/* DMA Configurations */
#define MAIN_DMA_MAX_REQ_SIZE 128
#define MAIN_DMA_BUFFER_SIZE 256

/* Accelerator Configurations */
#define COMPUTE_UNIT_PIO_SIZE 32

/* KMP specific */
#define STRING_SIZE_BYTES 32411
#define PATTERN_SIZE_BYTES 4

#endif /* KMP_HW_DEFINES_H */
