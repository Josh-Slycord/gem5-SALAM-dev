# gem5-SALAM Debug Flags Reference

This document describes all debug flags available in gem5-SALAM for tracing and debugging hardware accelerator simulations.

## Usage

Enable debug flags when running gem5:
```bash
./build/ARM/gem5.opt --debug-flags=FlagName configs/SALAM/generated/fs_benchmark.py ...
```

Multiple flags can be combined:
```bash
./build/ARM/gem5.opt --debug-flags=CommInterface,LLVMInterface ...
```

## Individual Debug Flags

| Flag | Usage Count | Primary File(s) | Description |
|------|-------------|-----------------|-------------|
| `CommInterface` | 38+ | comm_interface.cc | Memory communication interface - read/write requests, port management |
| `CommInterfaceQueues` | 12+ | comm_interface.cc | Detailed queue operations in CommInterface |
| `DeviceMMR` | 21+ | comm_interface.cc, dma.cc | Device Memory-Mapped Register access |
| `LLVMInterface` | 10+ | llvm_interface.cc | LLVM IR interpretation and execution |
| `LLVMParse` | * | LLVMRead/ | LLVM bitcode parsing |
| `NoncoherentDma` | 2 | noncoherent_dma.cc | Non-coherent DMA transfers |
| `Runtime` | 20+ | llvm_interface.cc | Runtime execution events |
| `RuntimeCompute` | * | llvm_interface.cc | Compute operation scheduling |
| `RuntimeQueues` | * | llvm_interface.cc | Runtime queue management |
| `SALAM_Debug` | 8 | basic_block.cc, hw_statistics.cc | General SALAM debug messages |
| `StreamBuffer` | * | stream_buffer.cc | Stream buffer operations |
| `StreamDma` | * | stream_dma.cc | Streaming DMA transfers |
| `Trace` | * | Various | Function call tracing (often commented out) |
| `Step` | * | Various | Step-by-step execution tracing |
| `SALAMResults` | NEW | llvm_interface.cc, data_collection.cc | Performance/statistics output (human-readable) |
| `SALAMResultsCSV` | NEW | data_collection.cc | CSV format stats for scripted analysis |

## Compound Flags

### JDEV (Development/Debugging)
Combines multiple flags for comprehensive debugging:
```
JDEV = LLVMInterface + CommInterface + Runtime + RuntimeCompute + RuntimeQueues + SALAM_Debug + SALAMResults
```

**Use case**: Full development debugging - shows LLVM execution, memory operations, and compute scheduling.

### HWACC (Hardware Accelerator)
Focused on hardware accelerator interface:
```
HWACC = CommInterface + LLVMInterface
```

**Use case**: Debugging accelerator communication and LLVM execution without queue details.

## Flag Details

### CommInterface
Traces all communication between accelerators and memory system:
- Read/write packet handling
- Memory port allocation
- Request queue management
- Retry handling

Example output:
```
CommInterface: Trying to read addr: 0x10020080, 4 bytes through port: local
CommInterface: Done with a read. addr: 0x10020080, size: 4
```

### DeviceMMR
Traces memory-mapped register access:
- Accelerator control register reads/writes
- DMA flag register operations
- Configuration register access

### LLVMInterface
Traces LLVM IR execution:
- Instruction scheduling
- Dependency graph construction
- Runtime engine initialization

### Runtime
Traces high-level runtime events:
- Global read/write commits
- Accelerator state transitions

### SALAM_Debug
General debugging for:
- Basic block execution
- HW statistics collection
- Power/energy modeling

## Recommended Usage Patterns

### Debugging DMA Issues
```bash
--debug-flags=NoncoherentDma,DeviceMMR,CommInterface
```

### Debugging Accelerator Execution
```bash
--debug-flags=LLVMInterface,Runtime,SALAM_Debug
```

### Full Debug (High Output Volume)
```bash
--debug-flags=JDEV
```

### Memory Communication Issues
```bash
--debug-flags=CommInterface,CommInterfaceQueues
```

## Notes

- Many DPRINTF calls are guarded by `if (debug())` or `if (dbg)` checks
- Some Trace statements are commented out in production code
- Debug output can significantly slow simulation - use judiciously
- Consider using `--debug-file=debug.txt` to capture output to file

## Related Files

- Debug flag definitions: `src/hwacc/SConscript` (lines 73-90)
- CommInterface: `src/hwacc/comm_interface.cc`
- LLVMInterface: `src/hwacc/llvm_interface.cc`
- DMA: `src/hwacc/noncoherent_dma.cc`, `src/hwacc/stream_dma.cc`