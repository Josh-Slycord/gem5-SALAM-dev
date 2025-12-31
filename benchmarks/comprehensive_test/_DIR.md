---
dir_type: benchmark
domain: hardware-simulation
tags:
  - dir/type/benchmark
  - dir/domain/hardware-simulation
  - dir/tech/gem5-salam
  - dir/tech/llvm-ir
  - dir/purpose/accelerator-testing
  - shared/comprehensive-test
related:
  - "[[SALAM-Configurator/]]"
  - "[[standards_and_procedures/GEM5_SALAM_PATTERNS.md]]"
---

# Comprehensive Test Benchmark

A comprehensive gem5-SALAM test benchmark that exercises all configurable options including multiple accelerator clusters, functional unit types, memory modes, and streaming features.

## Purpose

- Tests all gem5-SALAM functional units (Integer, Float, Double, Bitwise)
- Validates hw_config instruction cycle overrides
- Exercises multiple cluster configurations
- Provides a template for new benchmark development

## Subdirectories

| Directory | Description |
|-----------|-------------|
| hw/ | Hardware accelerator sources, IR files, and configurations |
| sw/ | Software driver (main.cpp, boot code, linker script) |
| expected_results/ | Expected output for validation |

## Files

| File | Description |
|------|-------------|
| _DIR.md | This directory documentation |
| README.md | Benchmark overview and usage |
| config.yml | Main SALAM-Configurator YAML configuration |
| config_cache.yml | Cache mode configuration variant |
| config_full.yml | Full configuration with all options |
| config_stream.yml | Streaming accelerator configuration |
| comprehensive_clstr_hw_defines.h | Auto-generated hardware address defines |
| comprehensive_hw_defines.h | Manual hardware address defines (reference) |

## Key Patterns

Memory synchronization required before accelerator access - see GEM5_SALAM_PATTERNS.md.

## Building and Running

Build hardware IR, then software, then run simulation with gem5.opt.
