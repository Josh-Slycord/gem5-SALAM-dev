/**
 * Hardware defines for AES-256 ECB benchmark
 * Cluster: aes_clstr
 */

#ifndef AES_HW_DEFINES_H
#define AES_HW_DEFINES_H

/* Memory Base Addresses */
#define BASE_ADDRESS 0x10020000

/* DMA Configurations */
#define MAIN_DMA_MAX_REQ_SIZE 128
#define MAIN_DMA_BUFFER_SIZE 256

/* Accelerator Configurations */
#define COMPUTE_UNIT_PIO_SIZE 32

/* AES-256 specific */
#define AES_BLOCK_SIZE 16
#define AES_KEY_SIZE 32
#define AES_CONTEXT_SIZE 96

#endif /* AES_HW_DEFINES_H */
