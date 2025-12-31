/**
 * stream_producer.c - Stream Buffer Producer
 *
 * Produces data to a StreamBuffer for consumption by stream_consumer.
 * Used in streaming variant to test StreamDMA and StreamBuffer.
 */

#include <stdint.h>
#include "../../../comprehensive_clstr_hw_defines.h"

#define SIZE 4

void compute(double* input, double* output) {
    int i;

    /* Simple transformation */
    for (i = 0; i < SIZE; i++) {
        output[i] = input[i] + 1.0;
    }
}

void top() {
    double* input = (double*)c2_stream_in;
    double* output = (double*)c2_stream_out;

    compute(input, output);
}
