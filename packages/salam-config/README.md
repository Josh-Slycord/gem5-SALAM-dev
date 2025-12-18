# salam-config

Standalone configuration and power modeling tools for SALAM (SoC Architecture for LLVM-based Accelerator Modeling).

## Overview

This package provides gem5-independent tools for:
- Validating SALAM accelerator configuration YAML files
- Querying the 40nm power model database
- Listing functional units and instruction mappings
- Generating configuration outputs (with optional gem5 integration)

## Installation

From source (development):
    cd packages/salam-config
    pip install -e .

With development dependencies:
    pip install -e ".[dev]"

## Usage

### Command Line Interface

Validate a configuration file:
    salam-config validate -c path/to/config.yml

List functional units with power data:
    salam-config list-fus --cycle-time 5ns

List instruction to functional unit mappings:
    salam-config list-instructions

Show system information:
    salam-config info

## Power Model Data

The package includes a 40nm power model database with:
- 50+ functional units (adders, multipliers, dividers, etc.)
- Timing data for 7 cycle times (1ns, 2ns, 3ns, 4ns, 5ns, 6ns, 10ns)
- Per-operation power, energy, and area estimates
- Based on Synopsys DesignWare IP characterization

## Standalone vs gem5 Integration

This package can be used in two modes:

1. Standalone Mode: Configuration validation, power queries, and analysis without gem5
2. gem5 Mode: Full configuration generation for gem5-SALAM simulation

Standalone mode requires only pyyaml. gem5 mode requires the full gem5-SALAM installation.

## License

BSD-3-Clause (same as gem5)
