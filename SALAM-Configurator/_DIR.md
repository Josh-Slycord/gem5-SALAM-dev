---
dir_type: python-package
domain: hardware-simulation
tags:
  - dir/type/python-package
  - dir/domain/hardware-simulation
  - dir/tech/python
  - dir/tech/yaml
  - dir/purpose/code-generation
---

# SALAM-Configurator

Python tools for generating gem5-SALAM configuration files from YAML definitions.

## Files

| File | Description |
|------|-------------|
| systembuilder.py | Main generator - converts YAML to Python configs |
| parser.py | YAML parsing and validation utilities |
| fs_template.py | Full-system simulation template |
| template.yml | Example YAML configuration template |
| validate_generation.py | Validation script for generated configs |

## Key Notes

systembuilder.py TEMPLATE replacement at lines 68 and 250.
