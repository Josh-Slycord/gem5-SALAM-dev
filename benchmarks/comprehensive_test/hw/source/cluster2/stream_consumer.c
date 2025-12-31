/**
 * stream_consumer.c - Stream Buffer Consumer
 *
 * Consumes data from StreamBuffer produced by stream_producer.
 * Used in streaming variant to test StreamDMA and StreamBuffer.
 */

#include <stdint.h>
#include "../../../comprehensive_clstr_hw_defines.h"

#define SIZE 4

void compute(double* input, double* output) {
    int i;

    /* Simple transformation */
    for (i = 0; i < SIZE; i++) {
        output[i] = input[i] * 2.0;
    }
}

void top() {
    double* input = (double*)c2_stream_in;
    double* output = (double*)c2_stream_out;

    compute(input, output);
}
