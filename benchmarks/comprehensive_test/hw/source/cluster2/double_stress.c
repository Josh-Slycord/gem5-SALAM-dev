/**
 * double_stress.c - Double Operations (Simplified)
 */

#include <stdint.h>
#include "../../../comprehensive_clstr_hw_defines.h"

#define SIZE 4

void compute(double* input_a, double* input_b, double* output) {
    int i;

    for (i = 0; i < SIZE; i++) {
        double a = input_a[i];
        double b = input_b[i];

        double sum = a + b;
        double diff = a - b;
        double prod = a * b;

        output[i] = sum + diff + prod;
    }
}

void top() {
    double* input_a = (double*)c2_input_a;
    double* input_b = (double*)c2_input_b;
    double* output  = (double*)c2_output;

    compute(input_a, input_b, output);
}
