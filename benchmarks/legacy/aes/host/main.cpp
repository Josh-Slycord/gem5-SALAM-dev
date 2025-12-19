/**
 * AES-256 Host Driver for gem5-SALAM
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../../common/dma.h"
#include "../../common/m5ops.h"
#include "aes.h"

aes_struct aes;

int main(void) {
    m5_reset_stats();

    // SPM addresses
    uint8_t *spm_key = (uint8_t *)KEY_ADDR;
    uint8_t *spm_buf = (uint8_t *)BUF_ADDR;
    aes256_context *spm_ctx = (aes256_context *)CTX_ADDR;

    // Host buffers
    static uint8_t host_key[32];
    static uint8_t host_buf[16];
    static aes256_context host_ctx;

    aes.key = host_key;
    aes.buf = host_buf;
    aes.ctx = &host_ctx;

    printf("Generating AES test data\n");
    genData(&aes);
    printf("Data generated\n");

    // Copy data to SPM via DMA
    dmacpy(spm_key, host_key, 32);
    while (!pollDma());
    resetDma();

    dmacpy(spm_buf, host_buf, 16);
    while (!pollDma());
    resetDma();

    // Clear context
    memset(spm_ctx, 0, sizeof(aes256_context));

    printf("Starting AES accelerator\n");

    // Start accelerator
    *acc = 0x01;

    // Wait for completion
    while (*acc != 0x4) {
        // spin
    }

    printf("AES complete\n");

    // Copy result back
    dmacpy(host_buf, spm_buf, 16);
    while (!pollDma());

    *acc = 0x00;

    // Verify
    if (checkData(&aes) == 0) {
        printf("AES encryption successful\n");
        printf("Ciphertext: ");
        for (int i = 0; i < 16; i++) {
            printf("%02x ", host_buf[i]);
        }
        printf("\n");
    } else {
        printf("AES FAILED - output unchanged\n");
    }

    m5_dump_stats();
    m5_exit();
    return 0;
}
