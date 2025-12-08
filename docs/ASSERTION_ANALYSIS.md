# gem5-SALAM Assertion Analysis

Analysis of 145 assertions across 18 files in `src/hwacc/`.

## Summary by File

| File | Count | Priority |
|------|-------|----------|
| instruction.cc | 38 | HIGH - Core LLVM execution |
| operand.cc | 18 | MEDIUM - Type handling |
| registers.hh | 14 | LOW - Register operations |
| value.cc | 11 | MEDIUM - Value type handling |
| scratchpad_memory.cc | 10 | HIGH - Memory operations |
| llvm_interface.cc | 7 | HIGH - Main interface |
| stream_dma.cc | 5 | MEDIUM - DMA operations |
| io_acc.cc | 5 | MEDIUM - Accelerator I/O |
| function.cc | 5 | LOW - Function handling |
| register_bank.cc | 6 | LOW - Register file |
| dma_write_fifo.cc | 6 | MEDIUM - DMA FIFO |
| registers.cc | 6 | LOW - Register impl |
| basic_block.cc | 3 | LOW - BB handling |
| comm_interface.cc | 2 | HIGH - Communication |
| stream_buffer.cc | 2 | MEDIUM - Buffers |
| hw_interface.cc | 2 | LOW - HW interface |
| stream_port.hh | 4 | LOW - Port handling |
| noncoherent_dma.cc | 1 | MEDIUM - DMA |

## Critical Assertions (Should be Error Handling)

These assertions indicate user-facing errors that should produce helpful error messages:

### 1. Unsupported LLVM IR Constructs
**Files**: operand.cc, instruction.cc, value.cc

```cpp
assert(0); // We do not support this nested ConstantExpr
assert(0); // The value is not a supported type of llvm::Constant
assert(0); // Type is invalid for a register
```

**Recommendation**: Convert to `panic()` or `fatal()` with descriptive messages:
```cpp
panic("SALAM does not support nested ConstantExpr in LLVM IR. "
      "Simplify your kernel or use a supported construct.");
```

### 2. Configuration/Setup Errors
**Files**: io_acc.cc, stream_buffer.cc

```cpp
assert(length > 0);        // Zero-length transfer
assert(!running);          // Started while already running
assert(streamSize != 0);   // Invalid stream configuration
```

**Recommendation**: Use `fatal()` for configuration errors:
```cpp
fatal_if(length <= 0, "DMA transfer length must be positive, got %d", length);
fatal_if(running, "Accelerator started while already running");
```

### 3. Memory Address Errors
**Files**: scratchpad_memory.cc

```cpp
assert(AddrRange(pkt->getAddr(), ...).contains(pkt->getAddrRange()));
```

**Recommendation**: Use `panic()` with address details:
```cpp
panic_if(!range.contains(pkt->getAddrRange()),
         "Access to 0x%lx size %d outside scratchpad range",
         pkt->getAddr(), pkt->getSize());
```

## Assertions to Keep (Internal Consistency)

These are appropriate as assertions - they check internal invariants that should never fail unless there's a bug:

### Type Checking
```cpp
assert(irtype->isIntegerTy());
assert(irtype->isFloatingPointTy());
assert(valueTy == llvm::Type::PointerTyID);
```

### State Machine Invariants
```cpp
assert(outstandingPkts.size());  // Retry without outstanding packets
assert(!packetQueue.empty());    // Processing empty queue
assert(isBusy[idx]);             // Port not busy during completion
```

### LLVM IR Structure Validation
```cpp
assert(iruser);
assert(inst);
assert(callInst);
assert(callee);
```

## Assertions in Release Builds

Note: Standard `assert()` is removed in release builds (`-DNDEBUG`).

For critical checks that must remain:
- Use gem5's `panic()` / `panic_if()`
- Use gem5's `fatal()` / `fatal_if()`
- Use gem5's `warn()` / `warn_if()` for non-fatal issues

## Recommended Changes

### High Priority (User-Facing)

1. **operand.cc:296,299** - Unsupported LLVM construct
2. **operand.cc:398** - Invalid register type
3. **value.cc:265** - Unknown type
4. **instruction.cc:398,407,417** - Unsupported instruction

### Medium Priority (Configuration)

5. **io_acc.cc:230-231,267-268** - Invalid accelerator configuration
6. **stream_buffer.cc:167,176** - Invalid stream configuration
7. **scratchpad_memory.cc:128** - Address range validation

### Low Priority (Keep as Assertions)

- Register type checks (value.cc)
- Internal state checks (comm_interface.cc)
- LLVM pointer validations (llvm_interface.cc)

## Example Refactoring

### Before
```cpp
assert(0); // We do not support this nested ConstantExpr
```

### After
```cpp
fatal("SALAM Error: Unsupported LLVM IR construct - nested ConstantExpr\n"
      "  Location: %s\n"
      "  Solution: Compile kernel with -O1 or higher to simplify IR\n"
      "  Or refactor source to avoid complex constant expressions",
      irval->getName().str().c_str());
```

## gem5 Error Handling Functions

| Function | Behavior | Use When |
|----------|----------|----------|
| `panic(msg)` | Print and abort | Internal error / should never happen |
| `panic_if(cond, msg)` | Conditional panic | Assertion-like checks |
| `fatal(msg)` | Print and exit cleanly | User/config error |
| `fatal_if(cond, msg)` | Conditional fatal | Validation checks |
| `warn(msg)` | Print warning | Non-fatal issues |
| `inform(msg)` | Print info | Status messages |

## Next Steps

1. Convert `assert(0)` calls to `panic()` with messages (8 locations)
2. Convert configuration assertions to `fatal_if()` (6 locations)
3. Add user-friendly error messages for unsupported IR constructs
4. Document remaining assertions as intentional internal checks