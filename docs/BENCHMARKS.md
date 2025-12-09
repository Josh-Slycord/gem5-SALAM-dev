# gem5-SALAM Benchmark Reference

This document describes all benchmarks available in gem5-SALAM.

---

## Benchmark Categories

| Category | Location | Purpose |
|----------|----------|---------|
| sys_validation | benchmarks/sys_validation/ | System validation tests (10 benchmarks) |
| lenet5-* | benchmarks/lenet5-*/ | LeNet-5 CNN variants |
| mobilenetv2 | benchmarks/mobilenetv2/ | MobileNetV2 neural network |
| legacy | benchmarks/legacy/ | Legacy benchmarks |
| test-cases | benchmarks/test-cases/ | Development test cases |

---

## System Validation Benchmarks

These benchmarks test core SALAM functionality. Run with scripts/run_tests.py.

### Test Status Summary

| Benchmark | Last Result | Duration | Notes |
|-----------|-------------|----------|-------|
| bfs | PASS | ~3s | Breadth-first search |
| fft | PASS | ~9s | Fast Fourier Transform |
| gemm | PASS | ~3s | Matrix multiplication |
| md_grid | FAIL (timeout) | >600s | Known floating-point issue |
| md_knn | PASS | ~11s | Molecular dynamics KNN |
| mergesort | PASS | ~222s | Merge sort algorithm |
| nw | PASS | ~4s | Needleman-Wunsch alignment |
| spmv | PASS | ~3s | Sparse matrix-vector multiply |
| stencil2d | PASS | ~36s | 2D stencil computation |
| stencil3d | PASS | ~32s | 3D stencil computation |

### Benchmark Details

#### bfs (Breadth-First Search)
- **Description**: Graph traversal algorithm
- **Input**: Graph nodes and edges
- **Output**: Level arrays
- **Memory**: RegisterBank for nodes, edges, levels
- **Accelerators**: Top, bfs

#### fft (Fast Fourier Transform)
- **Description**: Discrete Fourier transform
- **Complexity**: O(n log n)
- **Memory**: SPM for real/imaginary components
- **Accelerators**: Top, fft

#### gemm (General Matrix Multiply)
- **Description**: Dense matrix multiplication C = A * B
- **Data Type**: Single-precision floating point
- **Memory**: 3x 32KB SPM (MATRIX1, MATRIX2, MATRIX3)
- **Accelerators**: Top, gemm

#### md_grid (Molecular Dynamics Grid)
- **Description**: Molecular dynamics simulation with grid-based neighbor finding
- **Status**: Known timeout issue
- **Root Cause**: Floating-point precision differences
- **Memory**: SPM for positions, forces, neighbors

#### md_knn (Molecular Dynamics KNN)
- **Description**: Molecular dynamics with K-nearest neighbors
- **Memory**: SPM arrays
- **Accelerators**: Top, md_knn

#### mergesort (Merge Sort)
- **Description**: Divide-and-conquer sorting algorithm
- **Verification**: Sorted correctly message
- **Memory**: SPM for input/output arrays
- **Note**: Longest running sys_validation benchmark (~222s)

#### nw (Needleman-Wunsch)
- **Description**: Sequence alignment algorithm
- **Application**: Bioinformatics
- **Memory**: SPM for sequences and scoring matrix
- **Accelerators**: Top, nw

#### spmv (Sparse Matrix-Vector Multiply)
- **Description**: Sparse matrix operations
- **Format**: CSR (Compressed Sparse Row)
- **Memory**: SPM for values, indices, vector
- **Accelerators**: Top, spmv

#### stencil2d (2D Stencil)
- **Description**: 2D stencil computation
- **Application**: Image processing, PDE solvers
- **Memory**: SPM for input/output grids
- **Accelerators**: Top, stencil2d

#### stencil3d (3D Stencil)
- **Description**: 3D stencil computation
- **Application**: Scientific computing
- **Memory**: SPM for 3D input/output grids
- **Accelerators**: Top, stencil3d

---

## Neural Network Benchmarks

### LeNet-5 Variants

LeNet-5 is a convolutional neural network for digit recognition.

| Variant | Location | Unrolling Strategy |
|---------|----------|-------------------|
| lenet5-nounroll | benchmarks/lenet5-nounroll/ | No loop unrolling |
| lenet5-kernelunroll | benchmarks/lenet5-kernelunroll/ | Kernel-level unrolling |
| lenet5-channelunroll | benchmarks/lenet5-channelunroll/ | Channel-level unrolling |

#### Configurations per Variant

| Config | Description |
|--------|-------------|
| naive | Baseline implementation |
| massive | Highly parallelized |
| stream | Stream-based processing |

#### LeNet-5 Architecture

- conv0: 5x5 convolution, 6 filters
- pool0: 2x2 max pooling
- conv1: 5x5 convolution, 16 filters
- pool1: 2x2 max pooling
- fc0: Fully connected (400->120)
- fc1: Fully connected (120->84)
- fc2: Fully connected (84->10)

#### Accelerators

Each LeNet-5 variant includes:
- top: Top-level controller
- conv0, conv1, conv2: Convolution layers
- pool0, pool1: Pooling layers
- fc0, fc1: Fully connected layers
- data_mover_*: Data movement units

### MobileNetV2

- **Location**: benchmarks/mobilenetv2/
- **Description**: Efficient CNN for mobile devices
- **Architecture**: Inverted residual blocks with linear bottlenecks

---

## Running Benchmarks

### System Validation Tests

python scripts/run_tests.py           # Run all
python scripts/run_tests.py -b gemm   # Single benchmark
python scripts/run_tests.py -l        # List available
python scripts/run_tests.py -t 1200   # Custom timeout (seconds)

### Manual Benchmark Execution

export M5_PATH=/path/to/gem5-SALAM-dev
cd 

./build/ARM/gem5.opt configs/SALAM/generated/fs_gemm.py     --mem-size=4GB     --mem-type=DDR4_2400_8x8     --kernel=benchmarks/sys_validation/gemm/sw/main.elf     --disk-image=baremetal/common/fake.iso     --machine-type=VExpress_GEM5_V1     --dtb-file=none     --bare-metal     --cpu-type=DerivO3CPU     --accpath=benchmarks/sys_validation     --accbench=gemm     --caches --l2cache

### Running LeNet-5

./build/ARM/gem5.opt configs/SALAM/generated/fs_lenet5_naive.py     --mem-size=4GB     --mem-type=DDR4_2400_8x8     --kernel=benchmarks/lenet5-nounroll/naive/sw/main.elf     --disk-image=baremetal/common/fake.iso     --machine-type=VExpress_GEM5_V1     --dtb-file=none     --bare-metal     --cpu-type=DerivO3CPU     --accpath=benchmarks/lenet5-nounroll     --accbench=naive     --caches --l2cache

---

## Benchmark Directory Structure

Each benchmark follows this structure:

benchmarks/<category>/<benchmark>/
    config.yml              # Accelerator configuration
    <name>_clstr_hw_defines.h  # Generated C header
    hw/                     # Hardware description
        ir/                 # LLVM IR files
        configs/            # HW configuration INI files
    sw/                     # Software
        main.cpp            # Test application
        main.elf            # Compiled binary
        Makefile            # Build rules

---

## Verification

### Pass Criteria

- Check Passed - Explicit pass message in output
- Check Failed - Explicit fail message
- Sorted correctly - For sorting benchmarks
- Exit code 0 - Successful completion

### Debug Flags

For debugging benchmark execution:

./build/ARM/gem5.opt --debug-flags=SALAMConfig,SALAMCfg ...

See docs/DEBUG_FLAGS.md for complete flag reference.

---

## Known Issues

### md_grid Timeout

- **Issue**: Benchmark times out after 600 seconds
- **Cause**: Floating-point precision differences
- **Workaround**: Not currently available
- **Status**: Under investigation

---

## Adding New Benchmarks

1. Create directory structure under benchmarks/
2. Write config.yml with acc_cluster and hw_config sections
3. Compile LLVM IR from source
4. Generate C defines using SALAM-Configurator
5. Compile software application
6. Validate configuration: python -m salam_config.cli validate -c config.yml

---

## See Also

- GENERATION.md - Configuration generation guide
- DEBUG_FLAGS.md - Debug flag reference
- Building_and_Integrating_Accelerators.md - Accelerator development
