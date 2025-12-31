/**
 * float_stress.c - Float Operations (Simplified)
 */

#include <stdint.h>
#include "../../../comprehensive_clstr_hw_defines.h"

#define SIZE 4

void compute(float* input_a, float* input_b, float* output) {
    int i;

    for (i = 0; i < SIZE; i++) {
        float a = input_a[i];
        float b = input_b[i];

        float sum = a + b;
        float diff = a - b;
        float prod = a * b;

        output[i] = sum + diff + prod;
    }
}

void top() {
    float* input_a = (float*)c1_input_a;
    float* input_b = (float*)c1_input_b;
    float* output  = (float*)c1_output;

    compute(input_a, input_b, output);
}
