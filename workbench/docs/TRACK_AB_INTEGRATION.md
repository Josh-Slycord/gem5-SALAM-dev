# Reviewed Track A/B integration

Implementation revision: `13bbe024fd9e480196125eecaf0783435180c029` on `codex/track-ab-integration-20261106`.

Qualification status: passed within the bounded acceptance below. The [checkpoint JSON](TRACK_AB_INTEGRATION_CHECKPOINT_2026-11-06.json) records the frozen implementation and every required evidence gate.

## Integrated scope

Track A input was `1460634fdef5edf20680ea560e07a2e01422e808`. Gemini's handoff was pinned to `70b817c764438f8b1236ed809a0508bd1a32a048`, based on `f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb`. Its later dirty documentation branch was excluded.

The accepted subset comprises the bounded bare-metal UART write fix (`fcab9da560`), repaired provenance audit (`3c3f594d9b`), canonical generator templates (`6ede49d574`), and two production response-queue helper regressions selected from `70b817c764`. These were integrated with the normalized GEMM configuration, direct factory, header generation and wrapper generation from Track A. The current typed C++ interfaces remain in place.

Canonical generation produces 129 files identical to the compiled default source. It preserves Float power/area fields, optional instruction-cap defaults, zero-is-unlimited FU limits and CLI model/period/profile selection. Local hardening rejects duplicate/mixed generator forms and malformed canonical occupancy templates even when the capability marker is unavailable. Root/tools generator copies remain identical. The capability marker comes from the accepted generator change; it does not claim the excluded C++ changes.

The UART verifier now requires fresh absolute evidence, private build outputs, argv-only child commands, finite timeouts, explicit ARM CPU selection, unchanged input identities and one exact structured simulator exit line. Host observations of exact UART bytes are distinguished from argument/errno assertions performed by the guest. A separate actual legacy-source run demonstrates that the old ignored-length implementation fails the same contract; a saved pass flag is insufficient.

## Provenance corrections

The original B3 inventory claimed a pinned f3 commit but read working-tree bytes. Independent review found one incorrect row among 301: the patched UART source was labeled as the old commit's content. Its original rows are retained with a historical/unverified warning; original bytes remain recoverable in Git.

The new [303-entry inventory](PROVENANCE_INVENTORY_TRACK_AB_2026-11-06.md) reads immutable Git blobs, modes and object IDs at the integration implementation pin. Its companion JSON retains hashes and path history. History paths use literal pathspecs. Dirty, deleted and untracked worktree files cannot supply content. Independent verification checked all 303 entries and all selected capability hashes. Name/token/path classifications remain unverified search hints. Notices and commit metadata do not establish original authorship, governing terms or clearance.

## Deferred B4 work

The process-global Value/Instruction live counters and zero assertions in an individual LLVMInterface finalizer are excluded. One accelerator may finish while another still owns graph nodes; a global zero condition does not establish per-instance teardown correctness. Their associated C++ changes require a separate ownership/lifetime design and real multi-accelerator/repeated-launch validation.

The accepted two tests call real queue helpers. Three other added tests manually imitate drain state, DMA chunking and register staging without invoking the corresponding production components; they are excluded from coverage claims. Actual SimObject retry, reentrancy, drain, DMA bypass/timing, RegisterBank delta-cycle and whole-graph lifetime tests remain open. No sanitizer or whole-engine leak-freedom claim is made by this integration.

## Validation boundaries

The source suites cover the frozen workbench code. Real numerical qualification covers fixed 8x8 int32 GEMM under nine clock/capacity/latency/base-address configurations, not arbitrary workloads or sizes. The matrix independently compares compiler-visible headers, IR, ELF load images, every output, effective configuration, native clocks/statistics/reset behavior and complete FU traces. Full ELF debug bytes need not match; both builders run a canonical guest only after load-image parity is established.

Actual Qt acceptance edits visible controls, dispatches the real QProcess/backend, and reopens saved evidence through the production completion gate. These GUI cases use the retained generated route; the normalized native route is qualified separately by the real GEMM differential study. Offscreen Qt rendering is used; this does not retest the Windows shortcut/WSL launcher. FFT and stencil acceptance require fresh hardware profile generation and real SCons rebuilds. The changed area and characterization-latency coefficients are synthetic transport tests, not physical calibration. Operational instruction cycles are checked separately.

Derived corrupt-output controls retain guest success and valid transport hashes while requiring independent numerical rejection in the actual result widgets. They are explicitly copied-data controls, not additional simulator runs.

## Reproduction and local evidence

See [native generation](NATIVE_GENERATION.md) for the generation differential harness. Run all `salam_workbench.checks` tiers (`fast`, `config`, `gui`) and reconcile discovery against selected IDs, with no skipped or duplicate tests. Use new evidence directories for every acceptance attempt.

Private runtime clones need the current native Python modules deployed and a full configuration binding. GUI manifest build/generation receipts must be relative paths inside the selected project's evidence directory; they may be byte-identical copies of genuine external receipts. Do not edit receipt contents to manufacture success. Fresh GUI rebuild tests intentionally reject reused variants; use an independent runtime/cache for a new cold acceptance or the explicitly named rebuilt-profile reuse mode when evaluating a verified cache.

Local task/evidence index: `D:\kb_local_chatGPT\salam\track-ab-integration-20261106`. Full simulator evidence remains under `/home/jslycord/projects/salam-track-ab-integration-20261106` and this worktree's ignored `workbench/evidence`. The Windows review package carries the patch and high-level receipts. Raw outputs and binaries remain outside Git.

The qualified checkpoint tag, original qualified source/runtime, legacy main, original Track A checkout and official repositories are preserved. The integration has its own branch and checkpoint.


## Completed acceptance

| Check | Verified result |
| --- | --- |
| Source suites | 953 unique tests: 386 fast, 503 configuration, 64 GUI; no missing, extra, duplicate or skipped tests; all 153 current source files match |
| Native helpers | Actual XML confirms 13 response-queue + 4 linked FU-pool tests, with no failure, error, disabled or skipped cases |
| Canonical defaults | 129 generated outputs match current compiled default source byte identities |
| Provenance | 303 immutable Git-blob entries; 3 identical generator pairs; 8 capability hashes in each of source/runtime; attribution hints remain unverified |
| GEMM differential | 9 pairs, 18 processes, 36 GEMM launches, 72 total actor invocations and 2304 observed values; 4 rejection controls |
| Separate numerical review | Own integer arithmetic and ELF parser; bound to the final study receipt; zero positive mismatches |
| GUI | Real offscreen Qt/QProcess: GEMM 64, FFT 1024 complex rows, stencil 16384 outputs; all independent oracle rows checked |
| Rebuilds | FFT/stencil require and pass fresh profile regeneration + real simulator rebuild witnesses |
| Copied-output controls | Both production readers and actual Qt result widgets reject one incorrect value despite guest success and valid transport hashes; these are not additional simulator runs |
| UART | Actual exact 45-byte positive output; actual baseline-source canary/failure output independently rejected |
| Preservation | Approved WSL relocation hashes match; refreshed post-move protected refs/checkouts/binary independently match; official repositories received no writes |

The 2304 observed values reuse two 64-value fixtures across configurations and builders; they are not 2304 distinct fixture positions. The GEMM study uses the normalized route; the GUI cases use the retained generated route.

The rebuilt-variant cloner now copies and fingerprints only the native factory package initializer and normalizer, while excluding workbench results. Missing, linked, drifting or stale dependencies fail before simulation; six focused regressions cover the repair.

Full timeline trace validation passed. The exported visual preview can be bounded; its actual coverage is:
| Workload | Rendered spans | Total spans | Preview limited |
| --- | ---: | ---: | --- |
| gemm | 2176 | 2176 | false |
| fft | 20000 | 70682 | true |
| stencil3d | 20000 | 205362 | true |

Rendered metrics include explicitly unavailable placeholders and nonfinite generic counters. Only available direct SALAM rows contribute to the direct measured-value count. Partial system-mapping checks remain recorded as partial. Synthetic PPA coefficient edits test transport, not physical calibration.

Interrupted attempts, including the host-storage failures, remain preserved and do not contribute passes. Original whole-graph lifetime, multi-accelerator ownership and production SimObject protocol/drain tests remain deferred.

The curated review package includes source/test inventories, final study/UART/GUI/control receipts, native XML, default parity, post-move preservation and the reviewed Track A-to-integration patch. Raw simulator outputs and binaries remain local and outside Git. The package manifest records every included file hash.


Separate saved-data audits recomputed all 1024 complex FFT outputs with an independent trigonometric DFT and Parseval check, and all 16384 stencil outputs with coordinate-defined six-neighbor arithmetic including boundary preservation. Each covers one seed-47 fixture and does not independently qualify FU traces or physical PPA calibration.

An initial stencil audit compared an intermediate Makefile hash with the final toolchain-adapted bytes; the exact source, immutable before/after images, recorded recipes and actual compiler/run-input identities now verify that two-stage transition, while the failed audit remains labeled historical.
