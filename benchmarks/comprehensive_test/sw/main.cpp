/**
 * ==========================================================================
 * Comprehensive Test Benchmark - Software Driver
 * ==========================================================================
 * Main driver for the comprehensive gem5-SALAM test benchmark.
 * Tests all functional units, memory modes, and streaming features.
 * ==========================================================================
 */

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <cmath>
#include "bench.h"
#include "../../common/m5ops.h"
#include "../comprehensive_clstr_hw_defines.h"

#define INT_SIZE     4
#define FLOAT_SIZE   4
#define DOUBLE_SIZE  4
#define STREAM_SIZE  4
#define FLOAT_EPSILON  1e-5f
#define DOUBLE_EPSILON 1e-10

/* Device control flags - match gem5-SALAM convention */
#define DEV_INIT    0x01
#define DEV_INTR    0x04

/* Heartbeat interval - print status every N iterations */
#define HEARTBEAT_INTERVAL 1000

/* Debug mode - compile with -DDEBUG for verbose output */
#ifdef DEBUG
#define DBG_PRINT(...) printf(__VA_ARGS__)
#else
#define DBG_PRINT(...) ((void)0)
#endif

/* Memory synchronization - force CPU writes to be visible to accelerator */
static inline void sync_memory(volatile void* addr) {
    (void)*(volatile uint32_t*)addr;  /* Read forces write buffer flush */
}

volatile int stage;

void acc_start(volatile uint8_t* acc_addr) {
    *acc_addr = DEV_INIT;
}

void acc_wait(volatile uint8_t* acc_addr, const char* name) {
    volatile int count = 0;
    while ((*acc_addr & DEV_INTR) != DEV_INTR) {
        count++;
        if (count % HEARTBEAT_INTERVAL == 0) {
            printf(".");
        }
    }
    printf("    %s: [%d] %d cycles\n", name, *acc_addr, count);
}

void acc_run(volatile uint8_t* acc_addr, const char* name) {
    *acc_addr = DEV_INIT;

    volatile int count = 0;
    while ((*acc_addr & DEV_INTR) != DEV_INTR) {
        count++;
        if (count % HEARTBEAT_INTERVAL == 0) {
            printf(".");
        }
    }

    /* Compiler barrier - ensure accelerator writes are visible */
    __asm__ __volatile__("" ::: "memory");

    printf("    %s: %d cycles\n", name, count);
}

void generate_int_data(int32_t* a, int32_t* b, int n) {
    for (int i = 0; i < n; i++) {
        a[i] = (i * 7 + 13) % 1000 - 500;
        b[i] = (i * 11 + 17) % 1000 - 500;
    }
}

void generate_float_data(float* a, float* b, int n) {
    for (int i = 0; i < n; i++) {
        a[i] = (float)((i * 7 + 13) % 1000) / 100.0f;
        b[i] = (float)((i * 11 + 17) % 1000) / 100.0f;
    }
}

void generate_double_data(double* a, double* b, int n) {
    for (int i = 0; i < n; i++) {
        a[i] = (double)((i * 7 + 13) % 1000) / 100.0;
        b[i] = (double)((i * 11 + 17) % 1000) / 100.0;
    }
}

void generate_bitwise_data(uint32_t* data, int n) {
    for (int i = 0; i < n; i++) {
        data[i] = (uint32_t)(i * 0x12345678 + 0xDEADBEEF);
    }
}

/* Validation: output = sum + diff + prod */
int validate_int_results(int32_t* a, int32_t* b, int32_t* output, int n) {
    int errors = 0;
    for (int i = 0; i < n; i++) {
        int32_t sum = a[i] + b[i];
        int32_t diff = a[i] - b[i];
        int32_t prod = a[i] * b[i];
        int32_t expected = sum + diff + prod;
        if (output[i] != expected) {
            errors++;
        }
    }
    return errors;
}

int validate_float_results(float* a, float* b, float* output, int n) {
    int errors = 0;
    for (int i = 0; i < n; i++) {
        float sum = a[i] + b[i];
        float diff = a[i] - b[i];
        float prod = a[i] * b[i];
        float expected = sum + diff + prod;
        float delta = fabsf(output[i] - expected);
        float tolerance = FLOAT_EPSILON * fabsf(expected);
        if (delta > tolerance) {
            errors++;
        }
    }
    return errors;
}

int validate_double_results(double* a, double* b, double* output, int n) {
    int errors = 0;
    for (int i = 0; i < n; i++) {
        double sum = a[i] + b[i];
        double diff = a[i] - b[i];
        double prod = a[i] * b[i];
        double expected = sum + diff + prod;
        if (fabs(output[i] - expected) > DOUBLE_EPSILON * fabs(expected)) {
            errors++;
        }
    }
    return errors;
}

int test_cluster0() {
    printf("Testing Cluster 0: Integer/Bitwise Operations\n");

    int32_t* int_a = (int32_t*)c0_input_a;
    int32_t* int_b = (int32_t*)c0_input_b;
    int32_t* int_out = (int32_t*)c0_output;
    uint32_t* bit_in = (uint32_t*)c0_bitwise_in;
    uint32_t* bit_out = (uint32_t*)c0_bitwise_out;

    DBG_PRINT("  a=%p b=%p
", int_a, int_b);

    generate_int_data(int_a, int_b, INT_SIZE);
    generate_bitwise_data(bit_in, INT_SIZE);
    memset(int_out, 0, INT_SIZE * sizeof(int32_t));
    memset(bit_out, 0, INT_SIZE * sizeof(uint32_t));

    /* Sync memory before accelerator access */
    sync_memory(int_a);
    sync_memory(int_b);

    acc_run((volatile uint8_t*)INTEGER_STRESS, "integer_stress");
    acc_run((volatile uint8_t*)BITWISE_STRESS, "bitwise_stress");

    int int_errors = validate_int_results(int_a, int_b, int_out, INT_SIZE);

    if (int_errors == 0) {
        printf("  Cluster 0: PASSED\n");
        return 0;
    } else {
        printf("  Cluster 0: FAILED (%d errors)\n", int_errors);
        return 1;
    }
}

int test_cluster1() {
    printf("Testing Cluster 1: Float Operations\n");

    float* float_a = (float*)c1_input_a;
    float* float_b = (float*)c1_input_b;
    float* float_out = (float*)c1_output;

    generate_float_data(float_a, float_b, FLOAT_SIZE);
    memset(float_out, 0, FLOAT_SIZE * sizeof(float));

    /* Sync memory before accelerator access */
    sync_memory(float_a);
    sync_memory(float_b);

    acc_run((volatile uint8_t*)FLOAT_STRESS, "float_stress");

    int float_errors = validate_float_results(float_a, float_b,
                                                float_out, FLOAT_SIZE);

    if (float_errors == 0) {
        printf("  Cluster 1: PASSED\n");
        return 0;
    } else {
        printf("  Cluster 1: FAILED (%d errors)\n", float_errors);
        return 1;
    }
}

int test_cluster2() {
    printf("Testing Cluster 2: Double Operations\n");

    double* double_a = (double*)c2_input_a;
    double* double_b = (double*)c2_input_b;
    double* double_out = (double*)c2_output;

    generate_double_data(double_a, double_b, DOUBLE_SIZE);
    memset(double_out, 0, DOUBLE_SIZE * sizeof(double));

    /* Sync memory before accelerator access */
    sync_memory(double_a);
    sync_memory(double_b);

    acc_run((volatile uint8_t*)DOUBLE_STRESS, "double_stress");

    int double_errors = validate_double_results(double_a, double_b,
                                                 double_out, DOUBLE_SIZE);

    if (double_errors == 0) {
        printf("  Cluster 2: PASSED\n");
        return 0;
    } else {
        printf("  Cluster 2: FAILED (%d errors)\n", double_errors);
        return 1;
    }
}

#ifdef STREAM_VARIANT
int test_streaming() {
    printf("Testing Cluster 2: Streaming Operations\n");

    double* stream_in = (double*)c2_stream_in;
    double* stream_out = (double*)c2_stream_out;

    for (int i = 0; i < STREAM_SIZE; i++) {
        stream_in[i] = (double)i * 1.5;
    }
    memset(stream_out, 0, STREAM_SIZE * sizeof(double));

    printf("  Starting producer and consumer concurrently...\n");
    acc_start((volatile uint8_t*)STREAM_PRODUCER);
    acc_start((volatile uint8_t*)STREAM_CONSUMER);

    acc_wait((volatile uint8_t*)STREAM_PRODUCER, "stream_producer");
    acc_wait((volatile uint8_t*)STREAM_CONSUMER, "stream_consumer");

    int errors = 0;
    for (int i = 0; i < STREAM_SIZE; i++) {
        double expected = stream_in[i] + 1.0;
        if (fabs(stream_out[i] - expected) > DOUBLE_EPSILON * fabs(expected)) {
            errors++;
        }
    }

    if (errors == 0) {
        printf("  Streaming Test: PASSED\n");
        return 0;
    } else {
        printf("  Streaming Test: FAILED (%d errors)\n", errors);
        return 1;
    }
}
#endif

int __attribute__ ((optimize("0"))) main(void) {
    m5_reset_stats();

    printf("========================================\n");
    printf("Comprehensive gem5-SALAM Test Benchmark\n");
    printf("========================================\n");

    stage = 0;

    int total_errors = 0;

    total_errors += test_cluster0();
    total_errors += test_cluster1();
    total_errors += test_cluster2();

#ifdef STREAM_VARIANT
    total_errors += test_streaming();
#endif

    printf("========================================\n");
    if (total_errors == 0) {
        printf("ALL TESTS PASSED\n");
    } else {
        printf("TESTS FAILED: %d cluster(s) with errors\n", total_errors);
    }
    printf("========================================\n");

    m5_dump_stats();
    m5_exit();
}
