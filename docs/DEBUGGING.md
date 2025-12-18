# gem5-SALAM Debugging Guide

A comprehensive guide to debugging hardware accelerator simulations in gem5-SALAM.

## Table of Contents
- [Quick Start](#quick-start)
- [Build Types](#build-types)
- [Debug Flags](#debug-flags)
- [GDB Debugging](#gdb-debugging)
- [DDD Debugging](#ddd-debugging)
- [Valgrind Memory Checking](#valgrind-memory-checking)
- [Debug Scenarios](#debug-scenarios)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Basic debug output
./build/ARM/gem5.opt --debug-flags=SALAMQuick configs/SALAM/generated/fs_vadd.py

# Verbose execution tracing
./build/ARM/gem5.opt --debug-flags=SALAMVerbose configs/SALAM/generated/fs_vadd.py

# GDB debugging
./scripts/run_debug.sh gdb 0 configs/SALAM/generated/fs_vadd.py

# Valgrind memory check
./scripts/run_valgrind.sh configs/SALAM/generated/fs_vadd.py
```

---

## Build Types

gem5 provides three build variants. Choose based on your debugging needs:

| Build | Command | Debug Symbols | Asserts | DPRINTF | Speed | Use Case |
|-------|---------|---------------|---------|---------|-------|----------|
| **opt** | `scons build/ARM/gem5.opt -j$(nproc)` | Yes | Yes | Yes | Medium | Development, testing |
| **debug** | `scons build/ARM/gem5.debug -j$(nproc)` | Yes (full) | Yes | Yes | Slow | GDB, Valgrind |
| **fast** | `scons build/ARM/gem5.fast -j$(nproc)` | No | No | No | Fast | Production runs |

### Recommendations

- **Default to `gem5.opt`** - Good balance of debuggability and performance
- **Use `gem5.debug`** when:
  - Running under GDB or Valgrind
  - Need to inspect optimized-out variables
  - Debugging crashes with full stack traces
- **Use `gem5.fast`** only for:
  - Final production runs
  - When confident code is stable

---

## Debug Flags

### Flag Categories

Debug flags control what debug output is generated. SALAM uses a hierarchical naming system:

#### Parsing/Initialization
| Flag | Description |
|------|-------------|
| `SALAMParse` | IR parsing and instruction creation |
| `SALAMParseValue` | Value/operand creation during parsing |
| `SALAMParseFunc` | Function and basic block initialization |
| `SALAMConfig` | Hardware configuration loading |

#### Execution
| Flag | Description |
|------|-------------|
| `SALAMExec` | General execution flow and scheduling |
| `SALAMExecCompute` | Instruction computation details |
| `SALAMExecQueue` | Queue status and operations |
| `SALAMExecSchedule` | BB scheduling and instruction dispatch |
| `SALAMExecStall` | Stall detection (RAW, WAR, FU unavailable) |
| `SALAMExecBranch` | Branch and control flow decisions |
| `SALAMExecCall` | Function call/return handling |

#### Memory/Communication
| Flag | Description |
|------|-------------|
| `SALAMComm` | CommInterface general operations |
| `SALAMCommQueue` | CommInterface queue operations |
| `SALAMCommMMR` | Memory-mapped register access |
| `SALAMMemSPM` | Scratchpad memory operations |
| `SALAMMemReg` | Register bank operations |
| `SALAMMemAccess` | General memory access tracing |

#### DMA
| Flag | Description |
|------|-------------|
| `SALAMDMA` | General DMA operations |
| `SALAMDMAStream` | Stream DMA operations |
| `SALAMDMABuffer` | Stream buffer operations |
| `SALAMDMAFifo` | DMA FIFO operations |

#### Hardware Modeling
| Flag | Description |
|------|-------------|
| `SALAMHWInterface` | HW interface queries |
| `SALAMFU` | Functional unit allocation/availability |
| `SALAMCycles` | Cycle count lookups |
| `SALAMPower` | Power model calculations |

#### Statistics/Results
| Flag | Description |
|------|-------------|
| `SALAMStats` | Statistics collection and internal tracking |
| `SALAMResults` | Human-readable performance results output |
| `SALAMResultsCSV` | CSV format results for scripting/analysis |

### Compound Flags (Presets)

Use these for common debugging scenarios:

| Preset | Flags Included | Use Case |
|--------|----------------|----------|
| `SALAMQuick` | Exec, Comm, Stats | Lightweight debugging |
| `SALAMVerbose` | Exec, ExecCompute, ExecQueue, ExecStall, ExecBranch | Detailed execution |
| `SALAMAll` | Parse, Exec, ExecCompute, Comm, DMA, Stats, IOAcc, Results | Everything |
| `SALAMMemory` | Comm, CommQueue, MemSPM, MemReg, DMA, DMAStream | Memory subsystem |
| `SALAMParseAll` | Parse, ParseValue, ParseFunc, Config | All parsing |
| `SALAMStallDebug` | ExecStall, FU, ExecQueue, MemAccess | Stall analysis |
| `SALAMDataDebug` | MemSPM, MemReg, DMA, ExecCompute | Data corruption |
| `SALAMDMADebug` | DMA, DMAStream, DMABuffer, DMAFifo, Comm | DMA issues |
| `SALAMPerfDebug` | Stats, Results, ExecStall, FU, Cycles | Performance profiling |
| `SALAMDev` | Exec, ExecCompute, Comm, DMA, Stats, Results | Development |

### Usage Examples

```bash
# Single flag
./build/ARM/gem5.opt --debug-flags=SALAMExec configs/...

# Multiple flags
./build/ARM/gem5.opt --debug-flags=SALAMExec,SALAMComm,Cache configs/...

# Compound flag
./build/ARM/gem5.opt --debug-flags=SALAMVerbose configs/...

# Mix compound and individual
./build/ARM/gem5.opt --debug-flags=SALAMQuick,Cache configs/...

# Output to file
./build/ARM/gem5.opt --debug-flags=SALAMVerbose --debug-file=trace.out configs/...

# Time-bounded tracing
./build/ARM/gem5.opt --debug-flags=SALAMExec \
    --debug-start=1000000 \
    --debug-end=2000000 \
    configs/...

# List all available flags
./build/ARM/gem5.opt --debug-help
```

---

## GDB Debugging

### Using run_debug.sh

The `scripts/run_debug.sh` script simplifies GDB debugging:

```bash
# Basic GDB session
./scripts/run_debug.sh gdb 0 configs/SALAM/generated/fs_vadd.py

# Break at specific tick
./scripts/run_debug.sh gdb 1000000 configs/SALAM/generated/fs_vadd.py

# With additional gem5 arguments
./scripts/run_debug.sh gdb 0 configs/SALAM/generated/fs_vadd.py --mem-size=512MB
```

### Manual GDB Usage

```bash
gdb -x scripts/gdb/salam.gdbinit --args ./build/ARM/gem5.debug \
    --debug-break=1000000 \
    configs/SALAM/generated/fs_vadd.py
```

### SALAM GDB Commands

Once in GDB with the SALAM init file loaded, these commands are available:

| Command | Description |
|---------|-------------|
| `salam-help` | Show all SALAM GDB commands |
| `salam-break-compute` | Break at accelerator compute entry |
| `salam-break-dma` | Break on DMA response |
| `salam-break-schedule` | Break at BB scheduling |
| `salam-break-memreq` | Break on memory response |
| `salam-break-start` | Break at accelerator start |
| `salam-break-finish` | Break at accelerator finish |
| `salam-break-all` | Set all common breakpoints |
| `salam-events` | Dump event queue |
| `salam-tick` | Print current tick |
| `salam-flag-on "FLAG"` | Enable debug flag at runtime |
| `salam-flag-off "FLAG"` | Disable debug flag at runtime |

### Example GDB Session

```
(gdb) salam-break-all
Breakpoint set at CommInterface::start
Breakpoint set at LLVMInterface::compute
Breakpoint set at CommInterface::finish
All common SALAM breakpoints set

(gdb) run
...
Breakpoint 1, gem5::CommInterface::start() at comm_interface.cc:123

(gdb) salam-events
Events on queue:
  1000500: LLVMInterface::compute

(gdb) salam-flag-on "SALAMExecCompute"
Debug flag 'SALAMExecCompute' enabled

(gdb) continue
```

---

## DDD Debugging

DDD (Data Display Debugger) provides a visual interface for GDB:

```bash
# Install DDD
sudo apt install ddd

# Launch with SALAM
./scripts/run_debug.sh ddd 0 configs/SALAM/generated/fs_vadd.py
```

DDD features:
- Visual data structure display
- Graphical breakpoint management
- Source code navigation
- Variable watch windows

---

## Valgrind Memory Checking

### Using run_valgrind.sh

```bash
# Basic memory check
./scripts/run_valgrind.sh configs/SALAM/generated/fs_vadd.py

# With custom output file
VALGRIND_OUTPUT=my-valgrind.txt ./scripts/run_valgrind.sh configs/...

# With additional options
VALGRIND_OPTS="--gen-suppressions=all" ./scripts/run_valgrind.sh configs/...
```

### Manual Valgrind Usage

```bash
valgrind \
    --leak-check=full \
    --show-leak-kinds=definite,possible \
    --track-origins=yes \
    --suppressions=util/salam.supp \
    --log-file=valgrind-output.txt \
    ./build/ARM/gem5.debug configs/...
```

### Understanding Valgrind Output

```
==12345== LEAK SUMMARY:
==12345==    definitely lost: 0 bytes in 0 blocks     <- Real leaks!
==12345==    indirectly lost: 0 bytes in 0 blocks     <- Real leaks!
==12345==      possibly lost: 1,234 bytes in 56 blocks <- Investigate
==12345==    still reachable: 45,678 bytes in 789 blocks <- Usually OK
==12345==         suppressed: 123 bytes in 4 blocks    <- Filtered out
```

- **Definitely lost**: Confirmed memory leaks - fix these!
- **Possibly lost**: May be leaks - investigate
- **Still reachable**: Not freed but still referenced - usually acceptable
- **Suppressed**: Filtered by suppression file - known false positives

### Suppression File

The `util/salam.supp` file filters known false positives from:
- Python interpreter internals
- gem5 event system allocations
- SALAM IR parsing (freed at simulation end)

---

## Debug Scenarios

### "Why is my accelerator stalling?"

```bash
./build/ARM/gem5.opt --debug-flags=SALAMStallDebug configs/...
```

Look for:
- RAW hazard messages (data dependencies)
- FU unavailable messages (resource contention)
- Memory stall messages (cache misses, DMA delays)

### "Data is corrupted somewhere"

```bash
./build/ARM/gem5.opt --debug-flags=SALAMDataDebug configs/...
```

Trace data through:
- Scratchpad memory operations
- Register bank reads/writes
- DMA transfers
- Computation results

### "DMA isn't working right"

```bash
./build/ARM/gem5.opt --debug-flags=SALAMDMADebug configs/...
```

Check:
- DMA request/response timing
- Buffer fill levels
- Address translations
- CommInterface handshakes

### "IR parsing/setup failed"

```bash
./build/ARM/gem5.opt --debug-flags=SALAMSetupDebug configs/...
```

Verify:
- LLVM IR file loading
- Instruction parsing
- Basic block structure
- Hardware configuration

### "Performance analysis needed"

```bash
./build/ARM/gem5.opt --debug-flags=SALAMPerfDebug configs/...
```

Collect:
- Cycle counts
- Stall breakdown
- FU utilization
- Statistics summary

---

## Troubleshooting

### "Debug flags not producing output"

1. Check you're using `gem5.opt` or `gem5.debug` (not `gem5.fast`)
2. Verify flag name spelling (case-sensitive)
3. Check simulation reaches the code with debug output

### "GDB can't find symbols"

1. Use `gem5.debug` build
2. Ensure binary wasn't stripped
3. Rebuild with: `scons build/ARM/gem5.debug -j$(nproc)`

### "Valgrind is too slow"

1. Use a smaller benchmark
2. Disable unnecessary checks: `--leak-check=no`
3. Focus on specific code: use `--toggle-collect`

### "Too much debug output"

1. Use `--debug-start` and `--debug-end` to limit time range
2. Use `--debug-file` to write to file instead of console
3. Use more specific flags instead of compound flags
4. Pipe through `grep` to filter

### "Simulation crashes before producing output"

1. Use GDB to get backtrace: `./scripts/run_debug.sh gdb 0 configs/...`
2. In GDB: `run`, then `bt full` after crash
3. Enable core dumps: `ulimit -c unlimited`

---

## Additional Resources

- [gem5 Debugging Documentation](https://www.gem5.org/documentation/learning_gem5/part2/debugging/)
- [gem5-SALAM GitHub](https://github.com/TeCSAR-UNCC/gem5-SALAM)
- [Valgrind Manual](https://valgrind.org/docs/manual/manual.html)
- [GDB Documentation](https://www.gnu.org/software/gdb/documentation/)
