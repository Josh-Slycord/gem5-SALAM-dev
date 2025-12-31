/**
 * comprehensive_hw_defines.h
 *
 * Memory map and constants for the comprehensive gem5-SALAM test benchmark.
 * This benchmark exercises ALL configurable options across:
 * - 3 accelerator clusters (integer, float, double)
 * - 11 functional unit types
 * - 50+ LLVM instructions
 * - Multiple memory types (SPM, StreamBuffer, DMA)
 * - All SPM synchronization modes
 */

#ifndef COMPREHENSIVE_HW_DEFINES_H
#define COMPREHENSIVE_HW_DEFINES_H

#include <stdint.h>

/* Device Control Flags */
#define DEV_INIT        0x01
#define DEV_INTR        0x04

/* Data Types */
typedef int32_t   INT_TYPE;
typedef uint32_t  UINT_TYPE;
typedef float     FLOAT_TYPE;
typedef double    DOUBLE_TYPE;

/* Test Parameters */
#define INT_ARRAY_SIZE      256
#define FLOAT_ARRAY_SIZE    256
#define DOUBLE_ARRAY_SIZE   128
#define STREAM_DEPTH        64
#define UNROLL_FACTOR       8

/* Cluster 0: Integer/Bitwise - Base 0x10020000 */
#define C0_DMA_FLAGS        0x10020000
#define C0_INT_TOP          0x10020080
#define C0_INTEGER_STRESS   0x100200C0
#define C0_INT_INPUT_A      0x10020100
#define C0_INT_INPUT_A_SIZE 4096
#define C0_INT_INPUT_B      0x10021100
#define C0_INT_INPUT_B_SIZE 4096
#define C0_INT_OUTPUT       0x10022100
#define C0_INT_OUTPUT_SIZE  4096
#define C0_BITWISE_STRESS   0x10023100
#define C0_BIT_INPUT        0x10023140
#define C0_BIT_INPUT_SIZE   2048
#define C0_BIT_OUTPUT       0x10023940
#define C0_BIT_OUTPUT_SIZE  2048
#define C0_BIT_REGISTERS    0x10024140
#define C0_BIT_REGISTERS_SIZE 64

/* Cluster 1: Float - Base 0x10030000 */
#define C1_DMA_FLAGS        0x10030000
#define C1_FLOAT_TOP        0x10030080
#define C1_FLOAT_STRESS     0x100300C0
#define C1_FLOAT_INPUT_A    0x10030100
#define C1_FLOAT_INPUT_A_SIZE 4096
#define C1_FLOAT_INPUT_B    0x10031100
#define C1_FLOAT_INPUT_B_SIZE 4096
#define C1_FLOAT_OUTPUT     0x10032100
#define C1_FLOAT_OUTPUT_SIZE 4096

/* Cluster 2: Double + Streaming - Base 0x10040000 */
#define C2_DMA_FLAGS        0x10040000
#define C2_STREAM_DMA       0x10040080
#define C2_STREAM_DMA_ADDR  0x100400C0
#define C2_DOUBLE_TOP       0x10040100
#define C2_DOUBLE_STRESS    0x10040140
#define C2_DOUBLE_INPUT_A   0x10040180
#define C2_DOUBLE_INPUT_A_SIZE 8192
#define C2_DOUBLE_INPUT_B   0x10042180
#define C2_DOUBLE_INPUT_B_SIZE 8192
#define C2_DOUBLE_OUTPUT    0x10044180
#define C2_DOUBLE_OUTPUT_SIZE 8192
#define C2_STREAM_PRODUCER  0x10046180
#define C2_PRODUCER_INPUT   0x100461C0
#define C2_PRODUCER_INPUT_SIZE 8192
#define C2_STREAM_CONSUMER  0x100481C0
#define C2_CONSUMER_OUTPUT  0x10048200
#define C2_CONSUMER_OUTPUT_SIZE 8192
#define C2_STREAM_BUFFER    0x1004A200
#define C2_STREAM_BUFFER_SIZE 64

/* GUI Publisher Status */
#define GUI_STATUS_ADDR     0x100F0000
#define GUI_PROGRESS_ADDR   0x100F0004
#define GUI_CYCLES_ADDR     0x100F0008
#define GUI_IDLE            0x00
#define GUI_C0_RUNNING      0x01
#define GUI_C1_RUNNING      0x02
#define GUI_C2_RUNNING      0x03
#define GUI_COMPLETE        0x06
#define GUI_ERROR           0xFF

/* Interrupt Numbers */
#define INT_C0_DMA          95
#define INT_C0_TOP          68
#define INT_C1_DMA          96
#define INT_C1_TOP          69
#define INT_C2_DMA          97
#define INT_C2_TOP          70
#define INT_C2_STREAM_RD    210
#define INT_C2_STREAM_WR    211

/* FU Indices */
#define FU_INTEGER_ADDER    1
#define FU_INTEGER_MUL      2
#define FU_BIT_SHIFTER      3
#define FU_BITWISE_OPS      4
#define FU_FLOAT_ADDER      5
#define FU_DOUBLE_ADDER     6
#define FU_FLOAT_MUL        7
#define FU_FLOAT_DIV        8
#define FU_DOUBLE_MUL       9
#define FU_DOUBLE_DIV       10
#define FU_BIT_REGISTER     15

#endif
