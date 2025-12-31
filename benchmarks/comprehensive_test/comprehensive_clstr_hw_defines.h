//BEGIN GENERATED CODE
/**
 * @file comprehensive_clstr_hw_defines.h
 * @brief Memory-mapped register addresses for comprehensive_clstr cluster
 *
 * @warning GENERATED CODE - DO NOT MODIFY
 *          Regenerate using: ./systembuilder.py
 *
 * These defines provide the memory-mapped addresses for accessing
 * DMA controllers, accelerators, and scratchpad memory in the
 * gem5-SALAM simulation environment.
 */
//Cluster: COMPREHENSIVE_CLSTR
//NonCoherentDMA
#define DMA0_Flags 0x10020000
#define DMA0_RdAddr 0x10020001
#define DMA0_WrAddr 0x10020009
#define DMA0_CopyLen 0x10020011
//NonCoherentDMA
#define DMA1_Flags 0x10020040
#define DMA1_RdAddr 0x10020041
#define DMA1_WrAddr 0x10020049
#define DMA1_CopyLen 0x10020051
//NonCoherentDMA
#define DMA2_Flags 0x10020080
#define DMA2_RdAddr 0x10020081
#define DMA2_WrAddr 0x10020089
#define DMA2_CopyLen 0x10020091
//Accelerator: CLUSTER0_TOP
#define CLUSTER0_TOP 0x100200c0
//Accelerator: INTEGER_STRESS
#define INTEGER_STRESS 0x10020100
#define c0_input_a 0x10020140
#define c0_input_b 0x10021180
#define c0_output 0x100221c0
//Accelerator: BITWISE_STRESS
#define BITWISE_STRESS 0x10023200
#define c0_bitwise_in 0x10023240
#define c0_bitwise_out 0x10024280
#define c0_regbank 0x100252c0
//Accelerator: CLUSTER1_TOP
#define CLUSTER1_TOP 0x10025400
//Accelerator: FLOAT_STRESS
#define FLOAT_STRESS 0x10025440
#define c1_input_a 0x10025480
#define c1_input_b 0x100264c0
#define c1_output 0x10027500
//Accelerator: CLUSTER2_TOP
#define CLUSTER2_TOP 0x10028540
//Accelerator: DOUBLE_STRESS
#define DOUBLE_STRESS 0x10028580
#define c2_input_a 0x100285c0
#define c2_input_b 0x1002a600
#define c2_output 0x1002c640
//Accelerator: STREAM_PRODUCER
#define STREAM_PRODUCER 0x1002e680
#define c2_stream_in 0x1002e6c0
//Accelerator: STREAM_CONSUMER
#define STREAM_CONSUMER 0x1002f700
#define c2_stream_out 0x1002f740
//END GENERATED CODE
