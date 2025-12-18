# gem5-SALAM Benchmarks

This directory contains benchmark applications for evaluating hardware accelerators
using the gem5-SALAM simulation framework. Benchmarks range from simple arithmetic
kernels to complex neural network inference workloads.

## Directory Structure

```
benchmarks/
├── common/              # Shared utilities for all benchmarks
│   ├── dma.h           # Simple DMA interface
│   ├── queue_dma.h/c   # Queued DMA interface
│   └── m5ops.h         # gem5 pseudo-instructions
├── legacy/             # Classic HLS benchmarks (MachSuite-derived)
│   ├── gemm/          # Matrix multiplication
│   ├── fft/           # Fast Fourier Transform
│   ├── fir/           # Finite Impulse Response filter
│   └── ...            # Other kernels
├── lenet5-*/          # LeNet-5 CNN with different unrolling strategies
├── mobilenetv2/       # MobileNetV2 neural network
├── sys_validation/    # System-level validation tests
└── test-cases/        # Unit tests for specific features
```

## Benchmark Categories

### Legacy Benchmarks (`legacy/`)
Classic compute kernels derived from MachSuite and Rodinia benchmarks:

| Benchmark | Description | Compute Pattern |
|-----------|-------------|-----------------|
| `gemm` | Matrix multiplication | Dense linear algebra |
| `gemm-*-unroll` | GEMM variants with loop unrolling | Optimization study |
| `fft` | Fast Fourier Transform | Signal processing |
| `fir` | FIR filter | Signal processing |
| `conv2` | 2D convolution | Image processing |
| `stencil2d` | 2D stencil computation | Structured grid |
| `stencil3d` | 3D stencil computation | Structured grid |
| `spmv` | Sparse matrix-vector multiply | Sparse algebra |
| `bfs` | Breadth-first search | Graph traversal |
| `nw` | Needleman-Wunsch alignment | Dynamic programming |
| `md-grid` | Molecular dynamics (grid) | N-body simulation |
| `md-knn` | Molecular dynamics (k-NN) | N-body simulation |
| `hotspot` | Thermal simulation | Structured grid |
| `vadd` | Vector addition | Simple parallel |

### Neural Network Benchmarks

#### LeNet-5 Variants (`lenet5-*/`)
Classic CNN architecture with different HLS optimization strategies:

- `lenet5-nounroll/` - No loop unrolling (baseline)
- `lenet5-kernelunroll/` - Kernel loops unrolled
- `lenet5-channelunroll/` - Channel loops unrolled

Each variant contains:
- `naive/` - Direct implementation
- `massive/` - Maximum parallelism configuration
- `stream/` - Streaming dataflow implementation

#### MobileNetV2 (`mobilenetv2/`)
Modern efficient CNN with inverted residuals and bottleneck blocks.

## Benchmark Anatomy

Each benchmark follows a standard structure:

```
benchmark/
├── Makefile           # Build configuration
├── config.yml         # Accelerator configuration for SALAM
├── defines.h          # Problem size parameters
├── bench/             # Core algorithm (for LLVM compilation)
│   ├── *.c           # Algorithm implementation
│   ├── *.h           # Type definitions, test harness
│   └── *.ll          # Generated LLVM IR
├── host/              # Host-side code (runs on CPU)
│   ├── main.cpp      # Driver program
│   ├── boot.s        # Bare-metal boot code
│   ├── boot.ld       # Linker script
│   └── Makefile      # Host build rules
└── hw/                # Generated hardware definitions
    └── *_hw_defines.h # Memory-mapped addresses
```

## Configuration File (config.yml)

The `config.yml` file defines the accelerator architecture:

```yaml
acc_cluster:
- Name: gemm_clstr              # Cluster name
- DMA:
  - Name: main_dma              # DMA controller
    Type: NonCoherent           # Cache coherence mode
    MaxReqSize: 128             # Max transfer size
    BufferSize: 256             # Internal buffer
- Accelerator:
  - Name: compute_unit          # Accelerator name
    IrPath: hw/compute.ll       # LLVM IR path
    PIOSize: 32                 # Control register size

global:
  memory:
    base_address: '0x10020000'  # SPM base address
    alignment: 64               # Memory alignment

hw_config:
  gemm:
    cycle_time: 10ns            # Target clock period
    functional_units:           # FU configuration
      integer_adder:
        cycles: 1               # Operation latency
        limit: 0                # Instance limit (0=unlimited)
```

## Building Benchmarks

### Prerequisites
- ARM cross-compiler (arm-linux-gnueabi-gcc)
- LLVM/Clang for IR generation
- gem5-SALAM compiled with ARM support

### Build Commands

```bash
# Build all benchmarks
cd benchmarks
make all

# Build specific benchmark
cd legacy/gemm
make

# Clean build artifacts
make clean
```

## Running Benchmarks

### Using gem5-SALAM GUI
1. Open SALAM GUI: `python scripts/salam_gui/main.py`
2. Load benchmark config.yml via File → Open Configuration
3. Configure simulation parameters
4. Run simulation and analyze results

### Command Line
```bash
# Generate accelerator configuration
python SALAM-Configurator/systembuilder.py benchmarks/legacy/gemm/config.yml

# Run simulation
./build/ARM/gem5.opt configs/SALAM/generated/gemm.py
```

## Common Utilities

### DMA Interface (`common/dma.h`)
Simple polling-based DMA for data transfers:
```c
dmacpy(spm_addr, mem_addr, size);  // Start transfer
while (!pollDma());                 // Wait for completion
resetDma();                         // Reset for next transfer
```

### Queued DMA (`common/queue_dma.h`)
Queue multiple DMA transfers:
```c
dmacpy(dst1, src1, len1);  // Enqueue transfer 1
dmacpy(dst2, src2, len2);  // Enqueue transfer 2
while (!pollDma());        // Wait for all complete
resetDma();
```

### M5 Operations (`common/m5ops.h`)
gem5 pseudo-instructions for simulation control:
```c
m5_reset_stats();   // Reset statistics counters
// ... benchmark code ...
m5_dump_stats();    // Dump statistics
m5_exit();          // Exit simulation
```

## Adding New Benchmarks

1. Create benchmark directory structure
2. Implement algorithm in `bench/`
3. Create host driver in `host/`
4. Write `config.yml` with accelerator parameters
5. Add to top-level Makefile if desired

## Performance Analysis

Benchmark statistics are captured using m5ops. Use `scripts/salam_gui/` for visualization.

## References

- [gem5-SALAM Paper](https://research.cs.wisc.edu/multifacet/papers/cal19_salam.pdf)
- [MachSuite Benchmarks](https://breagen.github.io/MachSuite/)
- [Rodinia Benchmark Suite](https://rodinia.cs.virginia.edu/doku.php)
