//BEGIN GENERATED CODE
/**
 * @file vadd_clstr_hw_defines.h
 * @brief Memory-mapped register addresses for vadd_clstr cluster
 *
 * @warning GENERATED CODE - DO NOT MODIFY
 *          Regenerate via the SALAM Workbench native builder.
 *
 * These defines provide the memory-mapped addresses for accessing
 * DMA controllers, accelerators, and scratchpad memory in the
 * gem5-SALAM simulation environment.
 */
// Generator: salam_workbench.native_codegen/v1
// Normalized layout SHA-256: 5636f645e8c4e625ee24c9c9a9ad5e6bc8a576e75a9d36299284d8021c87ecb7
// Source configuration: "benchmarks/sys_validation/vadd/config.yml"
// Source SHA-256: af4fb07242cb28ca960f436195bac755a9876d2dfcdaa1600b4c36eed3800d13
//Cluster: VADD_CLSTR
//NonCoherentDMA
#define DMA_Flags 0x10020000
#define DMA_RdAddr 0x10020001
#define DMA_WrAddr 0x10020009
#define DMA_CopyLen 0x10020011
//Accelerator: TOP
#define TOP 0x10020040
//Accelerator: VADD
#define VADD 0x10020080
#define VECTOR_A 0x100200c0
#define VECTOR_B 0x10020500
#define VECTOR_C 0x10020940
//END GENERATED CODE
