# Gemini review integration: provenance and limits

This is an independent comparison of the completed Gemini reviewer branch against the preserved gem5 26 checkpoint. It is not an upstream acceptance decision.

Gemini's final public source is b9c798893d53e8565943aed6678a151434d4a5f1 on [codex/pr2429-reviewer-compliance](https://github.com/Josh-Slycord/gem5-SALAM-dev/tree/codex/pr2429-reviewer-compliance). It reorganized its six phase commits after the earlier d3d493 snapshot. Both histories are retained in separate private archival branches; the final source was clean when captured. The original Gemini checkout and its notes were read only throughout.

## Preserved material

- [Original Gemini phases and loose configurator files](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/preservation/gemini-pr2429-20261105).
- [Completed Gemini source and capture manifest](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/preservation/gemini-final-20261105), with remote readback verified.
- [Standalone workbench history](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/preservation/standalone-workbench-20261105), including saved branch history and restore verification.
- Local full bundles and exact SHA-256 manifests remain in D:/kb_local_chatGPT/salam/preservation-integration-20261105. The standalone full bundle was restored into an independent bare repository and passed git fsck --full.
- The existing research archive, E: recovery collection, working main and gem5-26-checkpoint-20261105 remain intact. Contract/employer material under the local_only tree remains local.

Private archival branches are recovery snapshots. Their historical results and workspace bindings are not current release evidence. Generated builds, caches and duplicate reproducible outputs are deliberately excluded from new public source commits.

## Accepted implementation direction

The integration retains the useful memory ownership, retry, IR validation, native clock/statistics and shared constructor work. Additional independent repairs address response-queue ordering/reentrancy, bounded floating-point bit access, debug overreads and packet direction reads after ownership transfer.

The generated FU/instruction consumer check now fails closed when an actual subclass stops delegating to the shared base. Empty Python mixins were removed. Default regeneration must match all 129 generated artifacts. Fractional power/area/energy fields are checked separately from the intentionally integer fu_latency field.

Native timing uses dedicated domains derived from the explicit legacy clock_period parameter, after scalar overrides are applied. Clock-domain overrides and CPU switching are rejected where that path is unqualified. A matching nominal period does not promise an identical initial tick: native clockEdge aligns to a clock grid.

The final configurator parser, MobileNet path-selection and content-based template fixes are adopted selectively. The native clock adapter in the maintained full-system template remains in place.

## Why the finished source was not accepted wholesale

Gemini's tracker reports 662 pytest tests, four GTests and a successful build/GEMM run. The bounded read-only inspection found the binary and corresponding GEMM output, configuration and statistics, but no persistent full pytest/GTest result report. Reported counts remain attributed to Gemini.

Its final GEMM files expose a clock discrepancy: clock_period=10 is recorded on DMA, CommInterface and LLVMInterface, while all inherit the system domain at 1000 ticks (1 ns). The direct SALAM JSON reports the same 1000-tick period, 603 compute passes and 602000 elapsed ticks. Thus the smoke run does not establish legacy 10 ns compatibility.

The final hygiene regex also excludes ordinary workbench files, and the fallback installer overwrites hooks and checks filesystem content instead of staged Python blobs. The integration preserves the maintained checks and provides safe opt-in installation rather than importing that fallback.

## Explicitly open

- Cache controls: final AccCluster parameters are not wired through all generated paths and late overrides. They are deferred, not advertised as GUI capability.
- Omitting a DMA interrupt retains the default interrupt 200; it does not disable interrupt signaling.
- Native cycles counts compute passes, including the immediate first pass. It is not generally elapsed_ticks / clock_period.
- Native queue averages are tick-weighted; direct invocation JSON queue samples use a different sampling rule.
- PPA output contains configured, uncalibrated coefficients. No physical power/energy accuracy is established.
- Native statistics reset reconciliation is distinct from numerical correctness. Reader controls are not a real two-invocation/reset execution.
- Full SimObject backpressure/reentrancy, selected-port bypass, repeated-launch memory ownership and negative actual SALAM IR tests remain separate gates.
- A SALAM stdlib board, direct YAML board construction, repository-wide license clearance, and upstream review acceptance are unfinished.
- The proposed maintainer email was not adopted without current contact evidence.

Machine-readable counterpart: GEMINI_REVIEW_COMPARISON_2026-11-05.json. Final build/run qualification is recorded separately and must name the exact tested source and binary.
