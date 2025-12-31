# Comprehensive gem5-SALAM Test Benchmark

## Overview

This benchmark exercises **every configurable option** in gem5-SALAM, serving as:
- A validation suite for all features
- A documentation reference for configuration options
- A regression test baseline with expected power/area values

## Cluster Architecture

The benchmark consists of three accelerator clusters:

### Cluster 0: Integer/Bitwise Operations
Tests: , , , ,

| Accelerator | Purpose | FU Configuration |
|-------------|---------|------------------|
|  | Integer arithmetic | 16 adders, 4 multipliers |
|  | Bit operations | 8 shifters, 16 bitwise ops |

### Cluster 1: Float Operations
Tests: , ,

| Accelerator | Purpose | FU Configuration |
|-------------|---------|------------------|
|  | Single-precision FP | 8 adders, 8 multipliers, 2 dividers |

### Cluster 2: Double + Streaming
Tests: , , , ,

| Accelerator | Purpose | FU Configuration |
|-------------|---------|------------------|
|  | Double-precision FP | 4 adders, 4 multipliers, 1 divider |
|  | Data generation | 2 double adders/multipliers |
|  | Data processing | 2 double adders/multipliers |

## Configuration Variants

| Variant | File | Features |
|---------|------|----------|
| **Base** |  | NonCoherent DMA, Standard SPM |
| **Stream** |  | + StreamDMA, StreamBuffer, SPM InCon/OutCon |
| **Cache** |  | + ClusterCache for each cluster |
| **Full** |  | All features + debug flags enabled |

## Directory Structure



## Building



## Running

### Base Variant


### Stream Variant


### Cache Variant


### Full Variant (with debug)


## Functional Units Tested

| FU Type | Cluster | Instructions |
|---------|---------|--------------|
| IntegerAdder | 0 | add, sub, icmp |
| IntegerMultiplier | 0 | mul, sdiv, udiv, srem, urem |
| BitShifter | 0 | shl, lshr, ashr |
| BitwiseOperations | 0 | and, or, xor |
| BitRegister | 0 | bitcast |
| FloatAdder | 1 | fadd, fsub, fcmp |
| FloatMultiplier | 1 | fmul |
| FloatDivider | 1 | fdiv |
| DoubleAdder | 2 | fadd, fsub, fcmp (64-bit) |
| DoubleMultiplier | 2 | fmul (64-bit) |
| DoubleDivider | 2 | fdiv (64-bit) |

## Memory Features Tested

| Feature | Variant | Configuration |
|---------|---------|---------------|
| NonCoherent DMA | All | BufferSize: 64, MaxPendingReads: 4 |
| Standard SPM | All | Multiple read/write ports |
| RegisterBank SPM | All | 4 R/W ports, 0 latency |
| ReadyMode SPM | Base+ | ready_mode: true |
| ResetOnRead SPM | Base+ | reset_on_read: true |
| WriteOnValid SPM | Base+ | write_on_valid: true |
| StreamDMA | Stream+ | MM2S/S2MM FIFOs |
| StreamBuffer | Stream+ | InCon/OutCon connections |
| ClusterCache | Cache+ | 4-way, 16KB per cluster |

## GUI Publisher Integration

The benchmark includes GUI publisher status hooks at:
- : Cluster 0 status
- : Cluster 1 status
- : Cluster 2 status
- : Global status

Status codes:
- 0 = Idle
- 1 = Initializing
- 2 = Running
- 3 = Completed
- 4 = Error

## Expected Results

Each variant has expected performance, power, and area ranges defined in . These serve as regression baselines.

## Troubleshooting

### Common Issues

1. **LLVM IR not found**: Run  in the  directory first
2. **Cache errors**: Ensure  flag is used with cache variants
3. **Stream deadlock**: Check InCon/OutCon connections match accelerator ports

### Debug Flags

Enable specific debug output:
