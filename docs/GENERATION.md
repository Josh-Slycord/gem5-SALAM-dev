# gem5-SALAM Generation System

This document describes the file generation system used by gem5-SALAM.

## Overview

The generation system takes config.yml and produces:
1. Python accelerator config (gemm.py)
2. Full system config (fs_gemm.py)  
3. C header with defines (gemm_clstr_hw_defines.h)

## Components

### systembuilder.py

Main generation script.

Usage:
  python3 systembuilder.py --sysName NAME --benchDir PATH [options]

Options:
  --output-dir  Write to alternate directory
  --dry-run     Preview without writing
  --validate-only  Compare against existing

### validate_generation.py

Batch validation for all benchmarks.

Usage:
  python3 validate_generation.py [--verbose] [--benchmark NAME]

## Address Space

Base: 0x10020000
Max:  0x13ffffff
Alignment: 64 bytes

## Troubleshooting

Set M5_PATH:
  export M5_PATH=/path/to/gem5-SALAM-dev

