# Legacy Benchmarks

Classic compute kernels for gem5-SALAM accelerator evaluation, derived from
MachSuite and Rodinia benchmark suites.

## Available Benchmarks

| Benchmark | Algorithm | Domain | Complexity |
|-----------|-----------|--------|------------|
| **gemm** | Matrix Multiply | Linear Algebra | O(n³) |
| **gemm-no-unroll** | GEMM without unrolling | Linear Algebra | O(n³) |
| **gemm-partial-unroll** | GEMM partial unroll | Linear Algebra | O(n³) |
| **gemm-full-unroll** | GEMM full unroll | Linear Algebra | O(n³) |
| **fft** | Fast Fourier Transform | Signal Processing | O(n log n) |
| **fir** | FIR Filter | Signal Processing | O(n·k) |
| **conv2** | 2D Convolution | Image Processing | O(n²·k²) |
| **stencil2d** | 2D Stencil | Structured Grid | O(n²) |
| **stencil3d** | 3D Stencil | Structured Grid | O(n³) |
| **spmv** | Sparse Matrix-Vector | Sparse Algebra | O(nnz) |
| **bfs** | Breadth-First Search | Graph | O(V+E) |
| **nw** | Needleman-Wunsch | Bioinformatics | O(n²) |
| **md-grid** | Molecular Dynamics (Grid) | Scientific | O(n) |
| **md-knn** | Molecular Dynamics (k-NN) | Scientific | O(n·k) |
| **hotspot** | Thermal Simulation | Physics | O(n²) |
| **vadd** | Vector Addition | Parallel | O(n) |
| **vadd-inputs** | Vector Add with inputs | Parallel | O(n) |
| **vfdiv** | Vector FP Division | Parallel | O(n) |

## Directory Structure

Each benchmark follows a consistent structure:

```
benchmark/
├── Makefile           # Top-level build
├── config.yml         # Accelerator configuration
├── defines.h          # Problem size parameters
├── bench/             # Kernel code (→ LLVM IR)
│   ├── kernel.c      # Main computation
│   ├── kernel.h      # Type definitions
│   ├── kernel.ll     # Generated IR
│   └── support.h     # Test utilities
├── host/              # Host driver
│   ├── main.cpp      # Driver program
│   ├── boot.s        # Boot assembly
│   └── Makefile      # Host build
└── hw/                # Generated
    └── *_hw_defines.h
```

## Building

```bash
# Build all legacy benchmarks
make all

# Build specific benchmark
cd gemm && make

# Clean all
make clean
```

## Benchmark Categories

### Linear Algebra
- **gemm**: Dense matrix multiplication, fundamental for BLAS and neural networks
- **spmv**: Sparse matrix operations for scientific computing

### Signal Processing
- **fft**: Cooley-Tukey FFT, butterfly operations
- **fir**: Finite impulse response filter, convolution-based

### Image/Grid Processing
- **conv2**: 2D convolution with configurable kernel
- **stencil2d/3d**: Iterative stencil computations
- **hotspot**: Heat diffusion simulation

### Graph Algorithms
- **bfs**: Level-synchronous breadth-first search

### Bioinformatics
- **nw**: Dynamic programming sequence alignment

### Scientific Computing
- **md-grid/knn**: Molecular dynamics force calculations

### Simple Parallel
- **vadd/vfdiv**: Element-wise vector operations (baseline benchmarks)

## Configuration Guidelines

### Adjusting Problem Size
Edit `defines.h`:
```c
#define SIZE 64    // Array/matrix dimension
#define DEPTH 4    // For multi-dimensional data
```

### Modifying Accelerator
Edit `config.yml`:
- Adjust functional unit latencies
- Set resource limits
- Configure DMA parameters

### Adding Unrolling
In `bench/kernel.c`:
```c
#pragma clang loop unroll(full)      // Full unroll
#pragma clang loop unroll_count(4)   // Partial unroll
```

## References

- [MachSuite](https://breagen.github.io/MachSuite/)
- [Rodinia](https://rodinia.cs.virginia.edu/doku.php)
- [gem5-SALAM Paper](https://research.cs.wisc.edu/multifacet/papers/cal19_salam.pdf)
