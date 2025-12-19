/**
 * AES-256 Benchmark Definitions
 * Derived from MachSuite
 */

#ifndef __AES_DEFINES_H__
#define __AES_DEFINES_H__

#include <stdint.h>

// AES-256 uses 32-byte key and 16-byte block
#define KEY_SIZE 32
#define BLOCK_SIZE 16

// Memory-mapped SPM base addresses
#define SPM_BASE     0x2f100000
#define KEY_ADDR     (SPM_BASE + 0x000)
#define BUF_ADDR     (SPM_BASE + 0x100)
#define CTX_ADDR     (SPM_BASE + 0x200)

#endif // __AES_DEFINES_H__
