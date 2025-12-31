/**
 * integer_stress.c - Integer Functional Unit Stress Test (Simplified)
 *
 * Tests: IntegerAdder
 * Instructions: add, sub, mul
 */

#include <stdint.h>
#include "../../../comprehensive_clstr_hw_defines.h"

#define SIZE 4

void compute(int32_t* input_a, int32_t* input_b, int32_t* output) {
    int i;

    for (i = 0; i < SIZE; i++) {
        int32_t a = input_a[i];
        int32_t b = input_b[i];

        /* Simple operations only */
        int32_t sum = a + b;
        int32_t diff = a - b;
        int32_t prod = a * b;

        output[i] = sum + diff + prod;
    }
}

void top() {
    int32_t* input_a = (int32_t*)c0_input_a;
    int32_t* input_b = (int32_t*)c0_input_b;
    int32_t* output  = (int32_t*)c0_output;

    compute(input_a, input_b, output);
}
