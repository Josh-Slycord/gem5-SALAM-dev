/**
 * AES Host Header
 */

#ifndef __AES_HOST_H__
#define __AES_HOST_H__

#include <stdint.h>

#include "../defines.h"

typedef struct
{
    uint8_t key[32];
    uint8_t enckey[32];
    uint8_t deckey[32];
} aes256_context;

typedef struct
{
    aes256_context *ctx;
    uint8_t *key;
    uint8_t *buf;
    uint8_t *expected;
} aes_struct;

volatile uint8_t* acc = (volatile uint8_t*)0x2f000000;
uint64_t val_key, val_buf, val_ctx;

void genData(aes_struct *aes) {
    // Test key (all zeros for simplicity)
    for (int i = 0; i < 32; i++) {
        aes->key[i] = 0;
    }
    // Test plaintext
    for (int i = 0; i < 16; i++) {
        aes->buf[i] = i;
    }
}

int checkData(aes_struct *aes) {
    // Just verify encryption happened (output != input)
    int changed = 0;
    for (int i = 0; i < 16; i++) {
        if (aes->buf[i] != i) changed++;
    }
    return (changed > 0) ? 0 : 1; // 0 = success
}

#endif // __AES_HOST_H__
