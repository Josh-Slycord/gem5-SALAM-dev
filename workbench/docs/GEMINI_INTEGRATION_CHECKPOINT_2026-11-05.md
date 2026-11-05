# Retained gem5 26 integration checkpoint — 5 November 2026

The completed Gemini reviewer work has been independently repaired and qualified on an isolated runtime. The qualified implementation commit is b73fb354a0cb80c640666788f4bb1269261145b4. This checkpoint targets Josh's gem5 26 upgrade branch. Working main, the previous gem5-26-checkpoint-20261105 tag, and official repositories remain unchanged. Gemini's checkout and notes were read only.

## What changed

- Preserved standalone history, both Gemini histories and final planning notes, plus three independently restored Git bundles in private archival branches.
- Repaired packet ownership/retry reads, response queues and floating-point bit access.
- Added native clock/statistics integration with final scalar-override ordering, real per-actor domains and reset-window reconciliation.
- Verified real shared C++ constructor consumers and all 129 generated outputs.
- Fixed configurator parsing/path/template handling; made variant fingerprints cover configuration dependencies and verify cached copies.
- Preserved maintained validation checks and safe opt-in hook installation.

## Evidence

| Check | Observed result |
|---|---|
| Source gates | 742 independently discovered workbench tests, zero skips; final exact-head CI is required before merge |
| Native GTests | 28 pass through actual gem5 SCons registration |
| Sanitizers | Same 28 helper tests pass with ASan, UBSan and checked STL using the actual new build headers |
| Default generation | All 129 generated artifacts match |
| Configuration generation | 20 actual CLI generation/AST checks across both builders; not 20 simulations |
| Actual GUI runs | GEMM 64, FFT 1,024 and stencil 16,384 outputs checked; seed 47; NumPy has zero mismatches |
| Native GUI evidence | All five accelerator/DMA actors in each run use verified 10 ns domains; native/direct invocation counters reconcile |
| Repeated launch / reset | Two distinct inputs per process at 10 ns and 3 ns; all 256 outputs pass guest CPU, strict host oracle and NumPy; eight native reset-window reconciliations and eight FU replays pass |
| Clock effect | GEMM retains 337 compute passes while elapsed ticks change from 3,360,000 to 1,008,000, exactly 0.3 |
| Real wrong output | A deliberately corrupted second-launch result is rejected by guest and both independent references |
| Invalid IR | Valid LLVM 14 atomicrmw, i128 and vector fixtures reach actual SALAM and fail with clear opcode/type diagnostics |
| GUI rejection | Two derived output corruptions retain guest-pass/hash-valid evidence but display independent validation failure |

The GUI FFT path generated and rebuilt its own hardware variant. Stencil's exact default variant was built in parallel through the same checked API, then the GUI verified and reused that source/binary/configuration fingerprint. GEMM uses the new independently rebuilt base. Runtime FU limits/cycles, edited memory and scalar RegisterBank settings are witnessed in the real runs. The stencil GUI first refused a changed parser anchor before launch. The repair recognizes the two reviewed constructor forms, binds patches to actual Variable methods and preserves strict guards. All three GUI cases were repeated with the final tooling identity; the native binaries and configuration fingerprints remained unchanged. These cases do not claim a fresh custom fractional-profile rebuild for every benchmark; that is separate from the constructor and generated-field checks.

A count named cycles measures compute passes, including the immediate first pass. It is not generally elapsed_ticks / period. Native queue averages are tick-weighted; direct JSON queue samples use a different sampling rule. Process-lifetime invocation IDs continue across native statistics resets.

## Preservation and reproducibility

Public source and final exact-head checks: [PR #4](https://github.com/Josh-Slycord/gem5-SALAM-dev/pull/4). Initial 738-test source CI (342872e015): [push validation](https://github.com/Josh-Slycord/gem5-SALAM-dev/actions/runs/42085821685) and [PR validation](https://github.com/Josh-Slycord/gem5-SALAM-dev/actions/runs/42085867896).

Private recovery: [all Git bundles](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/preservation/recovery-bundles-20261105), [native qualification inputs and receipts](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/preservation/gemini-integration-qualification-20261105), and [legacy preservation inventory](LEGACY_PRESERVATION.md).

The machine-readable companion records exact source, toolchain/build receipts, binary hashes, GUI/NumPy/native receipts and archive publications. Local evidence lives under /home/jslycord/projects/salam-gemini-integration-20261105 and D:/kb_local_chatGPT/salam/gemini-integration-20261105. Failed setup/transport/orchestration attempts remain preserved. The successful GEMM GUI run is reused only after its unchanged source identity and recorded evidence are checked.

Reproduce helper coverage with workbench/scripts/verify_native_helpers.py; add --generated-headers from the actual SALAM-enabled build for the FU/Params suite. Reconcile one accelerator per native reset window with src/hwacc/tests/verify_native_stats.py. Numerical correctness remains a separate required check.

## Remaining boundaries

Whole-engine leak freedom and ASan, forced SimObject backpressure/bypass/drain cases, broader LLVM behavior, stdlib board migration, native SCons hardware generation, useful cache GUI controls and file-specific license/maintenance clearance remain open. Historical failed GCC/debug-object and stencil audit experiments remain in the earlier evidence; successful new runs do not retroactively clear them.

The retained legacy _write_r ignores byte length. The reset qualifier uses bounded UART; the production syscall was not repaired here. Initial printf transport failures remain failed evidence.

PPA output describes configured, uncalibrated coefficients. It does not establish aggregate physical power/energy accuracy. Large raw run/build outputs remain local; the private evidence package is curated. No employer/contract local_only material was published.

See [the Gemini comparison](GEMINI_REVIEW_COMPARISON_2026-11-05.md) and [current upstream readiness](UPSTREAM_READINESS.md) for exact adoption/defer decisions.
