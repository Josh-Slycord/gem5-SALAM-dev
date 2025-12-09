# gem5-SALAM Configuration Generation Guide

This document describes the configuration generation system for gem5-SALAM, including the salam_config module, configuration file format, and the relationship with legacy tools.

---

## Overview

gem5-SALAM uses YAML configuration files to define hardware accelerator clusters. Two generation systems exist:

1. **salam_config** (v2.0) - Modern Python module with CLI
2. **SALAM-Configurator** - Legacy generation scripts

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| salam_config/cli.py | Entry point | Command-line interface |
| salam_config/core/config_manager.py | Core | Configuration orchestration |
| salam_config/core/schema_validator.py | Core | YAML validation |
| salam_config/models/power_model.py | Models | FU power/timing data |
| SALAM-Configurator/ | Legacy | Original config generator |

### Generated Files

The generation system takes config.yml and produces:

1. **Python accelerator config** (gemm.py) - gem5 accelerator setup
2. **Full system config** (fs_gemm.py) - Complete simulation config
3. **C header with defines** (gemm_clstr_hw_defines.h) - Hardware addresses

---

## Quick Start

### Prerequisites

1. Set the M5_PATH environment variable:

   export M5_PATH=/path/to/gem5-SALAM-dev

2. Ensure Python 3.7+ with PyYAML installed:

   pip install pyyaml

### Generate Configurations

From gem5-SALAM-dev directory:

    python -m salam_config.cli generate -b gemm
    python -m salam_config.cli generate -b gemm -v           # verbose
    python -m salam_config.cli generate -b gemm --dry-run    # preview
    python -m salam_config.cli generate -b bfs --cycle-time 10ns

### Validate Configuration

    python -m salam_config.cli validate -c benchmarks/sys_validation/gemm/config.yml

### View System Info

    python -m salam_config.cli info

---

## Configuration File Format

Each benchmark has a config.yml file defining the accelerator cluster.

Location: benchmarks/<category>/<benchmark>/config.yml

### acc_cluster Section

Defines the hardware accelerator cluster topology:

- Name: Cluster identifier
- DMA: DMA configuration (Name, MaxReqSize, BufferSize, Type)
- Accelerator: Accelerator definitions (Name, IrPath, PIOSize)
- Var: Variable/memory definitions (Name, Type, Size, Ports)

### hw_config Section

Defines instruction-level timing:

- functional_unit: FU enum value
- functional_unit_limit: Max concurrent instances (0 = unlimited)
- opcode_num: LLVM opcode number
- runtime_cycles: Execution latency in cycles

---

## CLI Reference

### Commands

- generate: Generate all configurations for a benchmark
- generate-hw: Generate HW profile C++ classes
- validate: Validate configuration YAML
- list-fus: List functional units with power data
- list-instructions: List instruction to FU mappings
- info: Show system information

### Generate Options

| Option | Description | Default |
|--------|-------------|---------|
| -b, --benchmark | Benchmark name (required) | - |
| -d, --bench-dir | Benchmark directory | benchmarks/sys_validation |
| --cycle-time | Cycle time (1ns-10ns) | 5ns |
| --base-address | Memory base address | 0x10020000 |
| --dry-run | Preview only | False |
| -v, --verbose | Verbose output | False |

---

## Power Model Database

### Supported Cycle Times

1ns (1 GHz), 2ns (500 MHz), 3ns (333 MHz), 4ns (250 MHz),
5ns (200 MHz), 6ns (167 MHz), 10ns (100 MHz)

### Functional Unit Enum Values

| Enum | Functional Unit | Used By |
|------|-----------------|---------|
| 0 | bit_register | load, store, phi |
| 1 | integer_adder | add, sub |
| 2 | integer_multiplier | mul, sdiv, udiv |
| 3 | shifter | shl, ashr, lshr |
| 4 | bit_logic | and, or, xor |
| 6 | float_sp_adder | fadd, fsub |
| 9 | float_sp_multiplier | fmul |
| 10 | float_sp_divider | fdiv |

### Address Space

- Base: 0x10020000
- Max: 0x13ffffff
- Alignment: 64 bytes

---

## Validation

The schema validator checks:

- acc_cluster section required
- DMA: Name required, valid Type (NonCoherent, Stream, Coherent)
- Accelerator: Name required
- Variable: Name, Type, Size required
- hw_config: runtime_cycles non-negative

---

## Legacy Tools (SALAM-Configurator)

### When to Use Which Tool

| Task | Use |
|------|-----|
| Validate config.yml | salam_config validate |
| Generate gem5 Python configs | salam_config generate |
| Generate C header files | SALAM-Configurator/systembuilder.py |

### Running SALAM-Configurator

    cd SALAM-Configurator
    python systembuilder.py --sysName gemm --benchDir benchmarks/sys_validation/gemm

Options:
- --output-dir: Write to alternate directory
- --dry-run: Preview without writing
- --validate-only: Compare against existing

---

## Troubleshooting

### M5_PATH Not Set

    export M5_PATH=/home/jslycord/gem5-SALAM-dev

### Invalid Cycle Time

Use supported values: 1ns, 2ns, 3ns, 4ns, 5ns, 6ns, 10ns

### Missing acc_cluster Section

Ensure config.yml has acc_cluster: section with proper YAML indentation.

---

## See Also

- DEBUG_FLAGS.md - Debug flag reference
- ASSERTION_ANALYSIS.md - Assertion usage
- Building_and_Integrating_Accelerators.md - Accelerator guide
- SALAM_Object_Overview.md - SALAM object model


---

## Configuration Tool Comparison

gem5-SALAM has **two** configuration systems. Here is when to use each:

### SALAM-Configurator (Legacy) - Use for Simulation

**Location:** `SALAM-Configurator/systembuilder.py`

**Use when:** You need to generate all files required to run a simulation.

**Generates:**
- `configs/SALAM/generated/<benchmark>.py` - Accelerator cluster definition
- `configs/SALAM/generated/fs_<benchmark>.py` - Full system configuration
- `<cluster>_hw_defines.h` - C header with memory addresses

**Command:**
```bash
cd $M5_PATH
python SALAM-Configurator/systembuilder.py   --sysName gemm   --benchDir benchmarks/sys_validation/gemm
```

**Options:**
- `--dry-run` - Preview without writing files
- `--validate-only` - Compare generated vs existing files
- `--base-address 0x10020000` - Custom base address

---

### salam_config (Modern) - Use for Validation & Analysis

**Location:** `salam_config/` module

**Use when:** You need to validate configs, query power data, or check system info.

**Provides:**
- Config validation with detailed error messages
- Power model database (40nm technology)
- Functional unit information
- Instruction-to-FU mapping

**Commands:**
```bash
# Validate a config file
python -m salam_config.cli validate -c benchmarks/sys_validation/gemm/config.yml

# List functional units with power/area data
python -m salam_config.cli list-fus --cycle-time 5ns

# List instruction mappings
python -m salam_config.cli list-instructions

# Show system info
python -m salam_config.cli info
```

---

### Workflow Recommendation

| Task | Tool |
|------|------|
| Generate simulation configs | SALAM-Configurator |
| Validate config.yml syntax | salam_config |
| Check power/area data | salam_config |
| Verify before simulation | Both (validate then generate) |
| Debug config issues | salam_config validate |

**Typical workflow:**
```bash
# 1. Validate the config first
python -m salam_config.cli validate -c benchmarks/sys_validation/mytest/config.yml

# 2. If valid, generate simulation files
python SALAM-Configurator/systembuilder.py --sysName mytest --benchDir benchmarks/sys_validation/mytest

# 3. Run simulation
./build/ARM/gem5.opt configs/SALAM/generated/fs_mytest.py --kernel=...
```

---

### Key Differences

| Feature | salam_config | SALAM-Configurator |
|---------|--------------|-------------------|
| Primary Purpose | Validation & Info | File Generation |
| Python Configs | Partial (metadata only) | Full (simulation-ready) |
| Full System File | No | Yes |
| C Headers | Disabled | Yes |
| Power Model | Yes (40nm database) | No |
| Schema Validation | Yes (detailed errors) | No (YAML parse only) |
| CLI Style | Subcommands | Arguments |
