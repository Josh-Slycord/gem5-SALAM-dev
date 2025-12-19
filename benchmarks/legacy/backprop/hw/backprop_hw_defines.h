/**
 * Hardware defines for backprop benchmark
 * Cluster: backprop_clstr
 */

#ifndef BACKPROP_HW_DEFINES_H
#define BACKPROP_HW_DEFINES_H

/* Memory Base Addresses */
#define BASE_ADDRESS 0x10020000

/* DMA Configurations */
#define MAIN_DMA_MAX_REQ_SIZE 128
#define MAIN_DMA_BUFFER_SIZE 256

/* Accelerator Configurations */
#define COMPUTE_UNIT_PIO_SIZE 32

/* Backprop specific - large data sizes */
#define WEIGHTS1_SIZE_BYTES 6656
#define WEIGHTS2_SIZE_BYTES 32768
#define WEIGHTS3_SIZE_BYTES 1536
#define TOTAL_DATA_SIZE 62872

#endif /* BACKPROP_HW_DEFINES_H */
