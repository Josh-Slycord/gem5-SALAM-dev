/**
 * Hardware defines for merge sort benchmark
 * Cluster: sort_clstr
 */

#ifndef SORT_HW_DEFINES_H
#define SORT_HW_DEFINES_H

/* Memory Base Addresses */
#define BASE_ADDRESS 0x10020000

/* DMA Configurations */
#define MAIN_DMA_MAX_REQ_SIZE 128
#define MAIN_DMA_BUFFER_SIZE 256

/* Accelerator Configurations */
#define COMPUTE_UNIT_PIO_SIZE 32

/* Sort specific */
#define ARRAY_SIZE 2048
#define ARRAY_SIZE_BYTES (2048 * 4)

#endif /* SORT_HW_DEFINES_H */
