---
dir_type: source
domain: hardware-simulation
tags:
  - dir/type/source
  - dir/domain/hardware-simulation
  - dir/tech/cpp
  - dir/tech/arm
  - dir/purpose/driver
---

# Software Driver Directory

Contains the baremetal ARM software driver for the comprehensive test benchmark.

## Files

| File | Description |
|------|-------------|
| _DIR.md | This directory documentation |
| main.cpp | Main test driver with accelerator interaction and validation |
| isr.c | Interrupt service routine handler |
| boot.s | ARM boot assembly code |
| boot.ld | Linker script for baremetal ARM |
| bench.h | Benchmark header with stage variable declaration |
| Makefile | Builds main.elf from source files |
| main.elf | Compiled executable (git ignored) |
| *.o | Object files (git ignored) |

## Key Components

### main.cpp
- Memory synchronization (sync_memory)
- Accelerator run/wait functions with heartbeat
- Data generation for int/float/double tests
- Validation against expected results

### boot.s
- ARM vector table and reset handler
- Stack setup and BSS initialization
- Calls main() entry point
