# gem5-SALAM Architecture

gem5-SALAM is a hardware accelerator simulation framework built on gem5. This document describes the system architecture and key components.

## Overview

gem5-SALAM enables simulation of custom hardware accelerators integrated with ARM-based systems. The architecture centers on two primary components:

- **CommInterface** - Communication and control
- **LLVMInterface** - Computation engine using LLVM IR

## Architecture Diagram

```
+--------------------------------------------------+
|          System CPU / Memory Hierarchy           |
+-------------------------+------------------------+
                          | (System Bus)
+-------------------------v------------------------+
|            AccCluster (Accelerator Cluster)      |
|  +--------------------------------------------+  |
|  |        CommInterface (Control)             |  |
|  |  +--------------------------------------+  |  |
|  |  |     LLVMInterface (Compute)          |  |  |
|  |  |  - LLVM IR Parser                    |  |  |
|  |  |  - CDFG Constructor                  |  |  |
|  |  |  - Instruction Scheduler             |  |  |
|  |  +--------------------------------------+  |  |
|  +--------------------------------------------+  |
|       |          |           |         |         |
|  +----v----+ +---v---+ +----v----+ +--v----+    |
|  |Scratchpad| |RegBank| |StreamDma| | DMA  |    |
|  +---------+ +-------+ +---------+ +------+    |
+--------------------------------------------------+
```

## Core Components

### CommInterface

**Location:** `src/hwacc/comm_interface.hh`

The CommInterface manages system integration:

- Memory-mapped register (MMR) management
- Queue management for memory requests
- Port arbitration and packet routing
- Interrupt generation

**Memory Map:**
```
| Flags (status/control) | Config | Variables |
```

**Port Types:**
| Port | Purpose |
|------|---------|
| PIO | Processor configuration |
| Local | Cluster-internal devices |
| ACP | Coherent system access |
| Stream | AXI-Stream interface |
| SPM | Scratchpad with sync |
| Reg | Register banks |

### LLVMInterface

**Location:** `src/hwacc/llvm_interface.hh`

The computation engine that:

1. Parses LLVM IR bitcode files
2. Builds Control and Data Flow Graphs (CDFG)
3. Schedules and executes instructions
4. Manages memory operations

**Key Methods:**
- `tick()` - Main simulation clock
- `launchRead()/launchWrite()` - Memory operations
- `constructStaticGraph()` - Build CDFG

### AccCluster

**Location:** `src/hwacc/acc_cluster.hh`

Organizational container for grouping accelerators:

- Extends gem5 `Platform` class
- Provides interconnect utilities
- Manages interrupt control
- Simplifies multi-accelerator configuration

### Memory Components

**ScratchpadMemory** (`src/hwacc/scratchpad_memory.hh`)
- Private fast memory with access synchronization
- Ready-mode to prevent access to uninitialized data
- Multiple ports with independent sync

**RegisterBank** (`src/hwacc/register_bank.hh`)
- Fast register file storage
- Minimal latency (~10ns typical)

### Data Transfer

**NoncoherentDma** - Memory-to-memory transfers
**StreamDma** - AXI-Stream interface with auto-play
**StreamBuffer** - Small FIFO for streaming

## LLVM Infrastructure

**Location:** `src/hwacc/LLVMRead/src/`

| Class | Purpose |
|-------|---------|
| `Value` | Base for all LLVM values |
| `Instruction` | LLVM instruction with dependencies |
| `BasicBlock` | Instruction sequence container |
| `Function` | Entry point for computation |
| `IRParse` | Parses LLVM bitcode |

## Hardware Modeling

**Location:** `src/hwacc/HWModeling/src/`

The `HWInterface` connects:

- **CycleCounts** - Instruction latencies
- **FunctionalUnits** - Available hardware units
- **SALAMPowerModel** - Power estimation
- **HWStatistics** - Performance metrics

## Simulation Flow

### 1. Configuration (Python)

```python
# Create accelerator cluster
system.acc_cluster = AccCluster()

# Configure communication interface
system.acc = CommInterface(
    pio_addr=0x10020000,
    pio_size=1024,
    int_num=68
)

# Configure LLVM interface with IR file
AccConfig(system.acc, ir_path, config_path)
```

### 2. Initialization (C++)

1. CommInterface allocates MMR memory
2. LLVMInterface parses LLVM bitcode
3. CDFG is constructed from IR
4. HWInterface loads timing/power data

### 3. Execution Loop

```
CommInterface::tick()
  - Check control register for Start
  - Process memory request queues
  - Initiate read/write operations

LLVMInterface::tick()
  - Launch top function
  - For each ActiveFunction:
    - Process completion queues
    - Schedule instructions
    - Issue memory operations
    - Track dependencies
```

### 4. Memory Flow

```
LLVMInterface.launchRead(inst)
    |
CommInterface.enqueueRead(request)
    |
Port.sendPacket()
    |
Memory Response
    |
CommInterface.readCommit()
    |
LLVMInterface executes instruction
```

## Configuration Files

### config.yml (YAML)

```yaml
acc_cluster:
  - Name: MyAccelerator
  - DMA:
    - Name: dma
      Type: NonCoherent
      BufferSize: 256
  - Accelerator:
    - Name: compute
      IrPath: hw/compute.ll
      PIOSize: 64
    - Var:
      - Name: input_spm
        Type: SPM
        Size: 4096
```

### INI Configuration

```ini
[CycleCounts]
gep = 0
add = 1
load = 4
store = 3

[AccConfig]
clock_period = 10
int_num = 68
```

## Debug Flags

| Flag | Description |
|------|-------------|
| `CommInterface` | Communication operations |
| `LLVMInterface` | Instruction scheduling |
| `Runtime` | General runtime events |
| `RuntimeQueues` | Queue state changes |
| `StreamDma` | DMA operations |
| `HWACC` | All accelerator debug |

## Key Design Patterns

### Queue-Based Execution

- **Reservation Queue** - Instructions waiting for dependencies
- **Compute Queue** - Waiting for functional units
- **Read Queue** - Load operations in flight
- **Write Queue** - Store operations in flight

### Lockstep vs Out-of-Order

- **Lockstep** - All instructions stall if any stalls
- **OoO** - Only affected regions stall (default)

### Dynamic Dependency Tracking

- RAW hazard detection via `activeWrites` map
- Register value propagation
- Phi node handling for control flow

## Directory Structure

```
src/hwacc/
  comm_interface.{hh,cc}     # Communication
  llvm_interface.{hh,cc}     # Computation
  compute_unit.{hh,cc}       # Base class
  acc_cluster.{hh,cc}        # Cluster container
  scratchpad_memory.{hh,cc}  # Private memory
  register_bank.{hh,cc}      # Register storage
  stream_dma.{hh,cc}         # Streaming DMA
  noncoherent_dma.{hh,cc}    # Basic DMA
  stream_buffer.{hh,cc}      # Stream FIFO
  LLVMRead/src/              # LLVM parsing
  HWModeling/src/            # Hardware models
```

## Related Documentation

- [DEBUG_FLAGS.md](DEBUG_FLAGS.md) - Debug flag reference
- [GENERATION.md](GENERATION.md) - Configuration generation
- [BENCHMARKS.md](BENCHMARKS.md) - Benchmark reference
- [Building_and_Integrating_Accelerators.md](Building_and_Integrating_Accelerators.md) - Tutorial
