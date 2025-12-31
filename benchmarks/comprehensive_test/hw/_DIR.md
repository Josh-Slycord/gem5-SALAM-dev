---
dir_type: config
domain: hardware-simulation
tags:
  - dir/type/config
  - dir/domain/hardware-simulation
  - dir/tech/llvm-ir
  - dir/tech/c
  - dir/purpose/accelerator-definition
---

# Hardware Accelerator Directory

Contains accelerator source code, compiled LLVM IR, and configuration files for the comprehensive test benchmark.

## Subdirectories

| Directory | Description |
|-----------|-------------|
| source/ | C source files for accelerators (organized by cluster) |
| ir/ | Compiled LLVM IR files (generated from source/) |
| configs/ | INI configuration files for instruction cycle counts |

## Files

| File | Description |
|------|-------------|
| _DIR.md | This directory documentation |
| Makefile | Builds LLVM IR from C sources using clang |

## Build Process

The Makefile compiles C sources to LLVM IR using:

- clang with -O1 optimization
- ARM target (arm-linux-gnueabihf)
- LLVM IR output (-emit-llvm)
