# SALAM native safety regressions

The native GTests use the same header helpers as the production response
queues and instruction writeback code:

- response_queue.test.cc checks empty insertion, early/equal timing,
  per-address ordering, blocked and in-callback head pinning, head-port
  retry state and next-event time selection.
- float_bits.test.cc checks four/eight-byte bitcasts, zero extension,
  signed zero and NaN payloads, integer conversions, truncation, and
  LLVM frem-compatible remainder semantics.

Both targets are registered outside the optional SALAM/LLVM build gate.
They depend only on the standard library and gem5's existing GTest support.
Expected native target names are:

    scons build/ARM/hwacc/response_queue.test.opt
    scons build/ARM/hwacc/float_bits.test.opt

The targeted integration check also compiled these exact test sources
against vendored GTest with AddressSanitizer, UndefinedBehaviorSanitizer
and checked libstdc++ iterators. The recorded commands and source hashes
are retained in the checkpoint's native-safety/validation.json receipt.
Standalone helper tests do not establish actual SimObject backpressure,
drain, or end-to-end simulator correctness. Those remain separate
integration checks.

## LLVM semantic reference inputs

The ir/frem.ll and ir/phi-swap.ll files each return zero under LLVM 14
when their expected mathematical behavior holds:

    lli-14 src/hwacc/tests/ir/frem.ll
    lli-14 src/hwacc/tests/ir/phi-swap.ll

The PHI case swaps two values across the back edge and catches a sequential
interpretation of peer PHIs. These commands check LLVM's reference
semantics; they do not claim SALAM executed either fixture. A simulator
harness must separately observe and compare their results.
