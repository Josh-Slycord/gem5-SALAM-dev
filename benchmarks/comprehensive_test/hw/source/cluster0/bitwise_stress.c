/**
 * bitwise_stress.c - Bitwise Operations (Simplified)
 */

#include <stdint.h>

#include "../../../comprehensive_clstr_hw_defines.h"

#define SIZE 4

void compute(uint32_t* input, uint32_t* output) {
    int i;

    for (i = 0; i < SIZE; i++) {
        uint32_t val = input[i];

        uint32_t shl = val << 1;
        uint32_t shr = val >> 1;
        uint32_t and_op = val & 0xFF;
        uint32_t or_op = val | 0xFF00;
        uint32_t xor_op = val ^ 0xFFFF;

        output[i] = shl ^ shr ^ and_op ^ or_op ^ xor_op;
    }
}

void top() {
    uint32_t* input  = (uint32_t*)c0_bitwise_in;
    uint32_t* output = (uint32_t*)c0_bitwise_out;

    compute(input, output);
}
