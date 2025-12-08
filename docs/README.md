# gem5-SALAM Documentation

This directory contains documentation for the gem5-SALAM project.

## Quick Links

- [CHANGELOG.md](CHANGELOG.md) - Track all changes and fixes
- [Building_and_Integrating_Accelerators.md](Building_and_Integrating_Accelerators.md) - How to create accelerators
- [SALAM_Object_Overview.md](SALAM_Object_Overview.md) - System architecture overview

## Documentation Index

### Core Documentation
| Document | Description |
|----------|-------------|
| [CHANGELOG.md](CHANGELOG.md) | Version history and change tracking |
| [GENERATION.md](GENERATION.md) | File generation system documentation (TODO) |

### Existing Documentation
| Document | Description |
|----------|-------------|
| [Building_and_Integrating_Accelerators.md](Building_and_Integrating_Accelerators.md) | Guide for creating and integrating hardware accelerators |
| [SALAM_Object_Overview.md](SALAM_Object_Overview.md) | Overview of SALAM object hierarchy |

### Planned Documentation
| Document | Description | Status |
|----------|-------------|--------|
| ARCHITECTURE.md | System architecture deep dive | Planned |
| BENCHMARKS.md | Benchmark documentation and results | Planned |
| CONFIGURATION.md | Configuration system guide | Planned |

## File Generation System

gem5-SALAM uses several scripts to generate configuration files:

### SALAM-Configurator
- **systembuilder.py** - Main generation script
  - Reads: `config.yml` from benchmark directories
  - Generates: Python configs in `configs/SALAM/generated/`
  - Generates: C headers (`*_clstr_hw_defines.h`) in benchmark directories

### Generated File Markers
- C headers use `//BEGIN GENERATED CODE` and `//END GENERATED CODE`
- Python configs currently have no markers (improvement planned)

## Directory Structure

```
gem5-SALAM-dev/
├── SALAM-Configurator/     # Configuration generation scripts
│   ├── systembuilder.py    # Main generator
│   ├── parser.py           # YAML parser
│   └── fs_template.py      # Full system template
├── configs/SALAM/
│   ├── generated/          # Generated Python configs
│   ├── HWAcc.py           # Hardware accelerator setup
│   └── HWAccConfig.py     # Accelerator configuration
├── benchmarks/
│   └── sys_validation/     # System validation benchmarks
├── docs/                   # This directory
└── gem5-SALAM-gui/        # GUI configuration tool (planned)
```

## Future: Wiki Generation

This documentation is structured to support future automatic wiki generation.
Markdown files follow consistent formatting for easy parsing.
