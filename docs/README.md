# gem5-SALAM Documentation

This directory contains documentation for the gem5-SALAM project.

## Quick Links

- [CHANGELOG.md](CHANGELOG.md) - Track all changes and fixes
- [Building_and_Integrating_Accelerators.md](Building_and_Integrating_Accelerators.md) - How to create accelerators
- [SALAM_Object_Overview.md](SALAM_Object_Overview.md) - System architecture overview

## Documentation Index

### Reference Documentation
| Document | Description | Status |
|----------|-------------|--------|
| [DEBUG_FLAGS.md](DEBUG_FLAGS.md) | Debug flag reference (16 flags) | Complete |
| [ASSERTION_ANALYSIS.md](ASSERTION_ANALYSIS.md) | Assertion usage analysis | Complete |
| [GENERATION.md](GENERATION.md) | Config generation & tool comparison | Complete |
| [BENCHMARKS.md](BENCHMARKS.md) | Benchmark documentation | Complete |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and solutions | Complete |
| [TESTING_SALAM.md](TESTING_SALAM.md) | SALAM-specific testing guide | Complete |

### Existing Documentation
| Document | Description |
|----------|-------------|
| [Building_and_Integrating_Accelerators.md](Building_and_Integrating_Accelerators.md) | Guide for creating and integrating hardware accelerators |
| [SALAM_Object_Overview.md](SALAM_Object_Overview.md) | Overview of SALAM object hierarchy |
| [CHANGELOG.md](CHANGELOG.md) | Version history and change tracking |

### Planned Documentation
| Document | Description | Status |
|----------|-------------|--------|
| ARCHITECTURE.md | System architecture deep dive | Planned |
| CONFIGURATION.md | Configuration system guide | Merged into GENERATION.md |

## Configuration Tools

gem5-SALAM has **two** configuration systems:

### SALAM-Configurator (for simulation)
```bash
python SALAM-Configurator/systembuilder.py --sysName <name> --benchDir <dir>
```
Generates: Python configs, full system files, C headers

### salam_config (for validation)
```bash
python -m salam_config.cli validate -c config.yml
python -m salam_config.cli list-fus --cycle-time 5ns
```
Provides: Validation, power model data, system info

See [GENERATION.md](GENERATION.md) for detailed comparison and workflow.

## Directory Structure

```
gem5-SALAM-dev/
├── SALAM-Configurator/     # Legacy config generation
│   ├── systembuilder.py    # Main generator
│   ├── parser.py           # YAML parser classes
│   └── fs_template.py      # Full system template
├── salam_config/           # Modern config module
│   ├── cli.py             # CLI interface
│   ├── core/              # Validation, logging
│   └── models/            # Power model database
├── configs/SALAM/
│   ├── generated/          # Generated Python configs
│   └── HWAccConfig.py     # Accelerator configuration
├── benchmarks/
│   └── sys_validation/     # System validation benchmarks
└── docs/                   # This directory
```

## Test Status

| Benchmark | Status |
|-----------|--------|
| bfs, fft, gemm, md_knn | Passing |
| mergesort, nw, spmv | Passing |
| stencil2d, stencil3d | Passing |
| md_grid | Known Issue (timeout) |
| LeNet5 | Config Valid |

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for md_grid details.
