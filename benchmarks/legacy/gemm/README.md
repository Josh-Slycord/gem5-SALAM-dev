# GEMM Benchmark

General Matrix Multiplication (GEMM) benchmark for gem5-SALAM accelerator evaluation.

## Overview

Computes C = A × B for dense matrices using a triple-nested loop structure.
This is a fundamental kernel for linear algebra and neural network workloads.

## Files

| File | Purpose |
|------|---------|
| `bench/gemm.c` | Accelerator kernel (compiled to LLVM IR) |
| `bench/gemm.h` | Type definitions and test harness |
| `bench/gemm.ll` | Generated LLVM IR for simulation |
| `bench/support.h` | Data generation utilities |
| `host/main.cpp` | Host driver program |
| `host/boot.s` | Bare-metal ARM boot code |
| `config.yml` | Accelerator configuration |
| `defines.h` | Matrix dimensions (ROW, COL) |
| `hw/gemm_hw_defines.h` | Generated memory-mapped addresses |

## Configuration

### Matrix Dimensions (`defines.h`)
```c
#define ROW 8   // Number of rows
#define COL 8   // Number of columns
```

### Accelerator Setup (`config.yml`)
- **Cluster**: `gemm_clstr`
- **DMA**: NonCoherent, 128B max request, 256B buffer
- **Compute Unit**: Single accelerator from `hw/compute.ll`

### Functional Units
| Unit | Cycles | Usage |
|------|--------|-------|
| `integer_adder` | 1 | Index calculations |
| `integer_multiplier` | 1 | Array indexing |
| `float_adder` | 5 | Accumulation |
| `float_multiplier` | 4 | Matrix multiply |

## Building

```bash
# Build all files
make

# Build specific targets
make -C bench    # Generate LLVM IR
make -C host     # Build host binary
```

## Running

### With gem5-SALAM GUI
1. Load `config.yml` in SALAM GUI
2. Set simulation parameters
3. Run and analyze results

### Command Line
```bash
# Generate configuration
python SALAM-Configurator/systembuilder.py config.yml

# Run simulation
./build/ARM/gem5.opt configs/SALAM/generated/gemm.py
```

## Memory Layout

```
Address Range          Content
--------------         -------
0x80c00000            Matrix A (input 1)
0x80c00000 + 8*N      Matrix B (input 2)
0x80c00000 + 16*N     Matrix C (output)
0x80c00000 + 24*N     Check data (verification)

0x2f100000 (SPM)      Scratchpad base (if SPM enabled)
```

## Verification

When compiled with `-DCHECK`, the host code verifies accelerator
results against a software reference implementation:

```
Expected:1.234 Actual:1.234
...
Check Passed
```

## Performance Metrics

Key statistics from `stats.txt`:
- `system.acc.cycles` - Total accelerator cycles
- `system.acc.fu_utilization.*` - Per-FU utilization
- `system.dma.bytes_transferred` - DMA data movement

## Variants

See related benchmarks with different optimization strategies:
- `gemm-no-unroll/` - No loop unrolling
- `gemm-partial-unroll/` - Partial inner loop unroll
- `gemm-full-unroll/` - Full loop unrolling (this benchmark)
