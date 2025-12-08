# gem5-SALAM Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2024-12-04

### Added
- **Safe generation infrastructure** in SALAM-Configurator/systembuilder.py:
  - --output-dir: Generate files to alternate directory for testing
  - --dry-run: Preview what files would be generated without writing
  - --validate-only: Compare generated files against existing files
  - --base-address: Configurable cluster base address (default: 0x10020000)
  - New helper functions: write_file(), compare_files()
  
- **Validation script** SALAM-Configurator/validate_generation.py:
  - Validates generation for all sys_validation benchmarks
  - Reports differences between generated and existing files
  - Supports --verbose, --benchmark, --path options

- **Documentation directory** docs/:
  - CHANGELOG.md for tracking changes
  - README.md documentation index

- **GUI/Installer integration** gem5-SALAM-gui/:
  - Moved from gem5-SALAM-Installer
  - Provides visual configuration interface

### Fixed
- **md_grid benchmark top.c** - Missing DMA transfer for force array
  - Force array was not being copied to SPM before md_grid accelerator runs
  - Added DMA transfer: force DRAM → FORCE SPM before accelerator start
  - This fixes uninitialized force values (was reading garbage, now reads 0.0)
  - NOTE: Check still fails - requires algorithm/numerical review

- **CRITICAL: HWAcc.py line 15** - acc_config variable was commented out but used on line 31
  - Would cause NameError: name acc_config is not defined at runtime
  - Uncommented the line to properly define the config path

- **HIGH: HWAccConfig.py lines 186-193** - FU configuration not being applied
  - cycles and limit values from config.yml were read but pass statements ignored them
  - Now properly applies: fu_instance.cycles = cfg[cycles]
  - Now properly applies: fu_instance.limit = cfg[limit]

- **HIGH: HWAccConfig.py _instantiate_instructions()** - functional_unit mapping not applied
  - Instructions were instantiated but functional_unit, functional_unit_limit, opcode_num
    values from config.yml hw_config were being ignored
  - Fixed to apply these parameters from hw_config when instantiating instructions
  - This enables proper FU resource allocation during instruction scheduling

- **HIGH: fs_template.py Bridge port naming** - gem5 API compatibility
  - Bridge class uses `cpu_side_port` (singular) not `cpu_side_ports` (plural)
  - Fixed both test_sys.iobridge and drive_sys.iobridge port assignments
  - Enables simulations to run without AttributeError

- **MEDIUM: systembuilder.py genHeaderFiles()** - Nested loop bug (lines 147-187)
  - Original code iterated for currentHeader in headerList: for cluster in clusters
  - This caused incorrect header/cluster pairing (N headers x N clusters instead of 1:1)
  - Fixed to use enumerate(clusters) with index-based header access

### Changed
- **systembuilder.py code style**:
  - Changed from tabs to 4-space indentation
  - L1Cache class now has proper Python indentation
  - Consistent newlines at end of files

### Benchmark Validation Status (sys_validation)
| Benchmark | Simulation | Generation |
|-----------|------------|------------|
| gemm      | Check Passed | Whitespace diff |
| bfs       | Check Passed | Whitespace diff |
| fft       | Check Passed | Whitespace diff |
| md_knn    | Check Passed | Whitespace diff |
| md_grid   | Check Failed | Whitespace diff |
| mergesort | Sorted correctly | Whitespace diff |
| nw        | Check Passed | Whitespace diff |
| spmv      | Check Passed | Whitespace diff |
| stencil2d | Check Passed | Whitespace diff |
| stencil3d | Check Passed | Whitespace diff |

### Known Issues
- md_grid floating-point precision issue (existing bug, not introduced)
- Generation produces whitespace-different files (tabs to spaces, Python style improvement)

## [Previous] - Session History

### Cycle Count Name Mapping Fix
- Fixed instruction name mapping in HWAccConfig.py
- and to and_inst, or to or_inst, xor to xor_inst
- Resolves Python reserved word conflicts

### Config.yml Standardization
- Fixed all sys_validation benchmark config.yml files
- Standardized DMA settings: MaxReqSize=64, BufferSize=128
- Fixed IR paths to use correct LLVM files
- SPM Ports=2 for proper memory interface
