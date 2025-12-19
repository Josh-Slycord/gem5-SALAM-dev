/**
 * AES-256 ECB Encryption
 * Derived from MachSuite - byte-oriented implementation
 */

#ifndef __AES_H__
#define __AES_H__

#include <stdint.h>

#include "../defines.h"

typedef struct
{
    uint8_t key[32];
    uint8_t enckey[32];
    uint8_t deckey[32];
} aes256_context;

void aes256_encrypt_ecb(aes256_context *ctx, uint8_t k[32], uint8_t buf[16]);

#endif // __AES_H__
