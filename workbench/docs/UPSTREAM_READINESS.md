# Upstream readiness for Josh's SALAM workbench

Review snapshot: **5 November 2026**. This is a preparation and evidence
register, not a submission to gem5 and not a claim of upstream acceptance.

The original register compared the packaging/visualization contribution from
[our PR #3](https://github.com/Josh-Slycord/gem5-SALAM-dev/pull/3).
The **5 November integration follow-up** updates this fork's status for
[our PR #4](https://github.com/Josh-Slycord/gem5-SALAM-dev/pull/4), against code
head `b73fb354a0cb80c640666788f4bb1269261145b4`. The upstream capture below
remains historical: no official discussion, resolution flag or acceptance
status was refreshed by this follow-up. The remaining work still answers the
questions raised on [gem5 PR #2429](https://github.com/gem5/gem5/pull/2429),
using this fork's implementation and independently reproducible evidence.

The final RegisterBank adapter follow-up adds typed-parser compatibility and
AST-bound guards after the real stencil GUI preflight refused the changed
constructor form. The current source fixture has **742 tests with zero skips**
(352 fast, 326 configuration, 64 GUI). The native binaries, configuration
fingerprints and earlier native/clock/reset proof remain unchanged.
Final consolidated GUI evidence is linked in the integration checkpoint.

## SimObject lifecycle follow-up (7 November 2026)

The isolated lifecycle work adds production drain and callback-order fixes,
opt-in real-SimObject fixtures, independent overlapping accelerator restarts,
and deliberately failing numerical/ownership controls. See the
[lifecycle regression](SIMOBJECT_PROTOCOL_TESTS.md) for reproducible commands
and bounded claims, and the
[dated validation record](SIMOBJECT_LIFECYCLE_VALIDATION_2026-11-07.md) for
actual outcomes. These additions do not revise the historical upstream
review inventory or replace the preserved qualified checkpoint. Checkpoint
serialization/restore, full-engine sanitizer coverage and remaining port
protocols are still separate gates.

## Attribution correction (7 November 2026)

[Specific original-source credit](../../SALAM_CREDITS.md) now identifies
fourteen verified Akanksha Chaudhari source commits adapted in the retained
reviewer phases. The [origin map](provenance/SALAM_SOURCE_ORIGINS.json) and
[correction record](SALAM_ATTRIBUTION_CORRECTION_2026-11-07.md) distinguish
original implementation, retained adaptations, subsequent fixes and unresolved
leads. This is a forward documentation correction: existing commits/notices
and qualified checkpoints remain intact. It does not close repository-wide
licensing, exhaustive authorship or upstream-acceptance gates.

## Provenance and interpretation

- Upstream PR author: `akanksha-sc`; branch `gem5-salam-develop`.
  Head at review: `b4ff9f5aaa0e4d3df9bf503df2212a278eb59645`; open and unmerged.
- Local comparison: PR #3 original head
  `91fcf24bc60cda21a4d5fb6a480a60a5060d58fe`, whose simulator code matches
  the port at `9c83f862e4ce96f85680e255c12164106e79986d`.
- The connected GitHub discussion inventory contains **298** timeline items
  (issue comments, review submissions and inline comments) and **132** inline
  threads: **122 resolved, 10 unresolved**. The machine-readable
  [thread index](UPSTREAM_REVIEW_2429.json) preserves IDs, authors, dates,
  paths and resolution/outdated flags without copying the full discussion.
- A resolved upstream thread is historical status in *that PR*. It does not
  prove a matching fix exists in this fork. Conversely, do not reopen an
  already answered question in the plan simply because its initial comment
  remains visible. “Outdated” describes a diff location, not resolution.
- The original review separated source inspection from runtime reproduction.
  The fork-status column now includes the later integration evidence summarized
  below. The original upstream head, discussion counts, authorship and thread
  flags are preserved; a fork fix does not resolve an official review thread.
  Retain the earlier [validation](GEM5_26_VALIDATION.md) and
  [known-gaps](GEM5_26_KNOWN_GAPS.md) records as historical evidence.

Akanksha's replies also point to
[gem5-salam-develop-clocked-working](https://github.com/akanksha-sc/gem5/tree/gem5-salam-develop-clocked-working)
for additional scheduling, PPA, cycle tracking and stdlib work. That is an
important comparison lead, not verified integration into our fork. Preserve
original authorship and review each selected change against our zero-limit
semantics, complete FU replay and numerical checks. Do not wholesale replace
our engine or describe another contributor's work as ours.

## Fork evidence added by the integration follow-up

The [integration checkpoint](GEMINI_INTEGRATION_CHECKPOINT_2026-11-05.md) and
its [machine-readable status](GEMINI_INTEGRATION_CHECKPOINT_2026-11-05.json)
are the follow-up authority for exact source/binary identities and remaining
qualification gates. They are finalized separately from this review register.
This is not a claim of full upstream readiness, license clearance or a SALAM
stdlib implementation.

- Both the [push source-validation run](https://github.com/Josh-Slycord/gem5-SALAM-dev/actions/runs/42085821685)
  and [PR source-validation run](https://github.com/Josh-Slycord/gem5-SALAM-dev/actions/runs/42085867896)
  passed at the code head above: **738** independently discovered workbench
  tests and **129/129** generated-source matches. Native helper sanitizer and
  statistics-reader controls also passed. Source CI did not build/run gem5.
- **28 registered native GTests passed through SCons** on the integration
  engine. These test production helpers, FU bookkeeping and constructor
  propagation; they do not constitute every full-SimObject timing scenario.
- A separately built simulator completed **two GEMM launches with different
  seeded inputs and a native statistics reset between them**, at both **10 ns
  and 3 ns** native SALAM periods. Both launches in each run matched all 64
  outputs against independent integer/NumPy calculations. Real domains were
  witnessed on all five SALAM actors, and native counters reconciled with the
  direct invocation observations in both reset windows. Wrong-period and
  wrong-window controls were rejected; FU replay subsequently passed.
- Each GEMM launch recorded **337 compute passes**, including its immediate
  initial pass. Elapsed times were **3,360,000 ticks at 10 ns** and
  **1,008,000 ticks at 3 ns**, an exact 0.3 ratio for these runs. Reset windows
  report one started/completed invocation while direct IDs remain 1 then 2.
  This validates these complete-invocation windows, not arbitrary partial ROI,
  every clock ratio or identical timing to the historical unaligned scheduler.

The local reset evidence remains outside the public source tree under
`D:/kb_local_chatGPT/salam/gemini-integration-20261105/`:
`native-reset-10ns-uart-fixed/complete-qualification.json` and
`native-reset-3ns-uart-fixed/complete-qualification.json`. These preserve the
original numerical receipts, source/binary hashes, native window checks and
FU replay. Their external driver used bounded UART output after exposing the
legacy transport limitation recorded in U20; the production syscall was not
silently repaired as part of that fixture.

## What reviewers actually asked

Priorities below are our proposed ordering. They are not priorities assigned
by upstream maintainers. “P0” means resolve or explicitly gate before a claim
of broad correctness or an upstream submission. A narrower integration
regression pass does not close the remaining engine and maintenance gates.

| ID / priority | Reviewer concern and source | Upstream discussion state | This fork: inspected state and required evidence |
| --- | --- | --- | --- |
| U01 / P0 | Jason Lowe-Power asked how reviewers can establish correctness, non-regression and maintenance cost, and requested a logically reviewable contribution rather than one large dump. [2025-08-04](https://github.com/gem5/gem5/pull/2429#issuecomment-3152676127); Giacomo agreed and requested verifiers/style alignment [2025-08-07](https://github.com/gem5/gem5/pull/2429#pullrequestreview-3096297334). | General discussion, with author/maintainer replies reporting tests and proposing integration stages; not a blanket approval. | The integration now has 738 source-only workbench tests, 28 registered native GTests, 129 generated-source matches, and separate real two-launch numerical/reset evidence described above. This remains smaller than the whole upstream regression suite. Prepare a small patch series, architecture/read-path guide, default-build non-regression and clean-host reproduction; keep GUI/appliance tooling separately reviewable. |
| U02 / P0 | LLVM must not become a dependency of ordinary gem5 builds; linker flags must be handled correctly. [Dependency](https://github.com/gem5/gem5/pull/2429#discussion_r2252731328), [linking](https://github.com/gem5/gem5/pull/2429#discussion_r3888887820). | Inline threads resolved; later author reported opt-in setup and an LLVM link-test branch. | `--with-salam` gates the LLVM/SALAM path; shared link flags use `MergeFlags`, with LLVM 14 deliberately supported. The integration simulator and native test targets build and run. Default non-SALAM builds without LLVM and actionable missing/wrong-version opt-in build failures still need dedicated CI evidence. The central clock hook imports SALAM lazily only when actual SALAM actors exist; its non-SALAM source test is not a default simulator build. |
| U03 / P0 | An unsupported opcode must fail explicitly rather than become a successful zero-cycle operation. Validate types and external calls too. [Bobby Bruce](https://github.com/gem5/gem5/pull/2429#discussion_r3951549752). | Resolved upstream. | Source repaired: unsupported instruction creation fails with opcode/IR text, and LLVM value-type/external-call validation replaces silent fallback. Three LLVM 14 assembler-valid negative leaf modules now reach the actual integration simulator: `atomicrmw`, `i128` and `<2 x i32>` each exit nonzero with the matching SALAM fatal and injected IR text. Effective leaf paths, source/binary hashes and unchanged inputs are recorded; no numerical oracle passed or ran. Local evidence: `native-ir-negative-20261105T1900Z/qualification.json` under the integration evidence root above. This partially covers U03; a complete opcode/type/call support matrix and actual external-call negatives remain open. |
| U04 / P0 | Register-bank timing responses can re-enter and delete a request before the caller finishes accessing it. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550093). | Resolved upstream. | Source repaired: register-port request bookkeeping is published before ownership transfer, retry counters capture packet direction before a synchronous response can delete it, and narrow debug reads are bounded. Production response-queue helpers have sanitizer/GTest reentrancy controls. Full RegisterBank/CommInterface synchronous-response SimObject reproductions, with timing/lifetime evidence, remain open; a numerical GEMM pass does not close them. |
| U05 / P0 | DMA write-FIFO functional/bypass operation reads destination bytes instead of writing queued bytes; preserve routing. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550193). | Resolved upstream. | Source repaired: `resumeEmptyFunctional` consumes FIFO chunks and issues selected-port `dmaAction(WriteReq, ...)`, replacing destination reads through the system proxy. Chunk lifetime relies on the synchronous atomic-noncaching path. Real selected-port timing-versus-bypass destination/routing comparisons remain open; ordinary timing GEMM does not exercise this mode. |
| U06 / P0 | Scratchpad shared response queue must obey the blocked head port's retry state under concurrent traffic. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550288). | Resolved upstream. | Source repaired: scratchpad and register-bank queues use the production `response_queue.hh` helper, preserving blocked/in-callback heads, stable ordering and correct shared-head scheduling. Native helper tests exercise backpressure, retry/head changes, reentrancy and tick overflow. A real multi-port forced-backpressure SimObject scenario is still required before broad protocol acceptance. |
| U07 / P0 | Opcode identifiers used as map keys were not initialized. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550530). | Resolved upstream. | Source repaired: retained opcode members are initialized from Params, while unused legacy counter/signed-conversion members and their invalid map insertions were removed. The built integration no longer contains the cited uninitialized members. Keep deterministic opcode-map and unsupported-ID regression coverage; constructor/source inspection is not exhaustive IR semantic coverage. |
| U08 / P0 | LLVM `frem` requires the correct remainder semantics. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550649). | Resolved upstream. | The active non-AP float/double path now uses the production `floatingRemainder` helper with `std::fmod` semantics. Native helper cases cover quotient truncation, signs, signed zero and exceptional inputs, alongside bounded float-bit access. Full opcode execution and the dormant alternate AP backend remain separate qualification boundaries; GEMM/FFT/stencil do not cover every instruction. |
| U09 / P0 | Execution graph ownership cycles can retain previous launches. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951549542). | Resolved upstream, current-location thread. | Explicit graph-edge release was added at finalization, including branch/switch/phi/call ownership paths. Two different-input GEMM launches now pass in one simulator process at both tested periods. This is positive repeated-launch evidence, not a full-engine leak/sanitizer proof; queued-user teardown, long-run lifetime and leak accounting remain open. |
| U10 / P1 | Existing instructions must be remappable to a custom FU with a complete, working tutorial; inventing an opcode number does not implement a new instruction. [Original](https://github.com/gem5/gem5/pull/2429#discussion_r3827697361), [clarification](https://github.com/gem5/gem5/pull/2429#discussion_r3984422730), [remaining proxy failure](https://github.com/gem5/gem5/pull/2429#discussion_r3984995472). | Three tutorial threads unresolved, despite intermediate fixes/replies; locations outdated. | Existing FU limits, latency/profile fields and generated consumer delegation are tested; constructor propagation is now checked against actual generated subclasses. Arbitrary custom-FU registration/remapping and a relocation-independent tutorial still need end-to-end regeneration, registration, rebuild, mapping and numerical evidence. New opcode numbers alone remain unsupported behavior. |
| U11 / P1 | Use one normalized schema/defaults across simulation, header generation and offline tools; reject unused/unknown settings. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951548509). | Unresolved, current location. | Workbench contracts reject known unsupported fields and retain layered effective-setting witnesses; both configurator parsers now fix optional DMA argument mapping and integer port counts, with header/template/path regressions. Multiple legacy/offline schemas still coexist. One normalized typed contract and cross-consumer omitted/default/invalid-field tests remain open; parser acceptance is not proof of every GUI knob. |
| U12 / P1 | Avoid writing executable Python configuration as strings; prefer maintained factories/components. [Factory](https://github.com/gem5/gem5/pull/2429#discussion_r3909524253), [stdlib direction](https://github.com/gem5/gem5/pull/2429#discussion_r3951546390). | Factory thread resolved after upstream author changed architecture; stdlib thread unresolved. | This fork still generates system Python and calls legacy `Simulation.run`; parser/template repairs and centralized clock binding do not implement a stdlib board or remove executable string generation. Build a maintained accelerator component/YAML adapter with configuration witnesses. A kernel/disk-oriented ArmBoard is not automatically compatible with the bare-metal route. |
| U13 / P1 | Generate changing hardware sources through SCons, rather than require a custom tracked-source branch per technology/profile. [Review and follow-up](https://github.com/gem5/gem5/pull/2429#discussion_r3909484005). | Unresolved; follow-up acknowledges current compromise but recommends build integration. | Isolated variant regeneration/rebuild and configuration-aware cache identity are retained; default generation matches all 129 tracked artifacts and generated subclasses must delegate correctly to shared constructors. This is not SCons-native hardware-profile dependency generation. Declared build inputs/outputs and broader generation/cache-invalidation cases remain open; preserve hand-written source. |
| U14 / P1 | Use native accelerator statistics with normal dump/reset semantics and ROI boundaries. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951549007). | Unresolved, current location. | Native `statistics::Group` instrumentation now exists for LLVM execution, communication and DMA/stream paths alongside direct JSON. Real two-launch tests at 10/3 ns reconcile started/completed invocations, compute passes, durations, logical requests/bytes and categories across native resets, rejecting wrong windows/periods. Native averages are tick-weighted, unlike direct pre-pass queue samples. Arbitrary partial-invocation ROI interpretation, probes and broader lifecycle/drain cases remain open. |
| U15 / P1 | Clock-domain changes must affect accelerator/DMA event timing consistently. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951549136). | Unresolved, current location. | Compute/communication/DMA actors now use ClockedObject domains and native edge scheduling. Dedicated domains derive from explicit integer-ns `clock_period` after final scalar overrides; C++ rejects inconsistent/zero periods and invalid service delays. Five actors are witnessed at 10/3 ns, with numerical/reset evidence and the GEMM elapsed ratio above. Native edge alignment changes first-interval semantics; CPU switching, dual/distributed roots and broader clock combinations remain explicitly unqualified. |
| U16 / P1 | Repeated instruction/FU parameter wrappers could be common configuration data types. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951548839). | Unresolved, current location. | C++ instruction/FU base classes now share Params constructors, generator output delegates to them, and actual generated-consumer checks plus GTests verify propagation. Named opcode/FU SimObject wrappers and their generated files remain for compatibility; empty Python mixins were removed. This is constructor consolidation, not conversion to one data-only SimObject or SCons profile generation. |
| U17 / P1 | Fractional PPA fields must survive configuration, and reported values must use one documented model. [Types](https://github.com/gem5/gem5/pull/2429#discussion_r3888887836), [model consistency](https://github.com/gem5/gem5/pull/2429#discussion_r3888887838). | Resolved upstream, with author stating the full reporting path lived on another branch. | Fractional configured coefficients and profile witnesses remain. `LLVMInterface::printResults` now lists those configured FU coefficients as uncalibrated inputs, without hard-coded fallback coefficients or an aggregate power/area claim. `SALAMPowerModel` remains a scaffold. Activity/units reconciliation, native power integration and physical calibration remain open; no measured power accuracy is established. |
| U18 / P1 | Enable cycle tracking through actual parameters or stop presenting unreachable code as a supported feature. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3888887861). | Resolved upstream after author identified implementation on another branch. | `HWStatistics.cycle_tracking` is exposed but True now fails explicitly because the legacy history buffer is unsafe and has no complete sample consumer. Scratch counters are fully initialized. Native statistics and invocation/FU JSON are the supported, separately scoped outputs; this deliberately does not enable legacy per-cycle history. |
| U19 / P0 before submission | Audit file-specific provenance/license obligations and maintainers instead of applying a blanket special notice. [License](https://github.com/gem5/gem5/pull/2429#discussion_r3909457012), [ownership](https://github.com/gem5/gem5/pull/2429#discussion_r2193177427). | License thread unresolved; original maintainer thread resolved. | No repository-wide legal/provenance audit completed in this integration. Existing notices remain; the proposed maintainer email was not adopted without current evidence. An origin/license manifest for SALAM, gem5, LLVM, generated data, CACTI and new code, plus correct maintenance commitments, remains a prerequisite before submission. Do not remove notices or invent ownership. |
| U20 / P1 | Document supported environments, workload/resource layout, native m5ops and optional offline-tool behavior. [Ubuntu](https://github.com/gem5/gem5/pull/2429#discussion_r3485233960), [m5ops](https://github.com/gem5/gem5/pull/2429#discussion_r3322311057), [CACTI no-SPM](https://github.com/gem5/gem5/pull/2429#discussion_r3971471287). | These threads resolved with author/reviewer follow-ups. | The source-bound Ubuntu 24.04/LLVM 14 route is exercised; appliance import, fresh-host portability, versioned workload resources and native m5ops migration remain separate gates. The legacy `benchmarks/common/syscalls.c::_write_r` ignores len and calls NUL-terminated `gem5_print(ptr)`; the reset test needed bounded UART output in its external fixture. Production transport repair remains open. Seeded workbench drivers already use bounded output, so their checks are not invalidated by that fixture failure. No blanket UART-transport claim is made; no-SPM CACTI output also remains workload-scoped. |

## Resolved findings that still guide regression tests

Do not blindly port an old reviewer suggestion: several were fixed in upstream
and some are independently fixed here. In this fork the instruction
configuration base initializes its members, functional-unit profile fields use
floating point, and `genHeaderFiles` pairs each cluster with its own saved
header. The integration adds generated-consumer/native tests and bounded
runtime evidence, while the full-SimObject cases above remain open.

Keep regression cases for constructor propagation, fractional coefficients,
optional DMA interrupt settings, integer connection port counts, preserved
custom header regions (including marker variants), CLI fallback/boolean
argument handling, non-import-time generators and no-build snapshots.
The index records those original comments and their resolved status. The
[DPRINTF/DPRINTFS question](https://github.com/gem5/gem5/pull/2429#discussion_r2193332862)
was answered and accepted; do not list native `DPRINTFS` as an invented SALAM
API or remove the instance debug gate without checking its intended behavior.

## Proposed upstream patch series

This ordering is our engineering proposal, informed by the review:

1. **Correctness and support boundary:** isolate U03-U09 with small native
   reproducers and negative tests; fix or explicitly reject unimplemented
   modes. Re-run numerical/FU replay after any engine change.
2. **Opt-in build and maintenance:** demonstrate ordinary gem5 builds without
   LLVM, supported opt-in link jobs, required license/maintainer decisions and
   style checks. Exclude unrelated GPU/syscall/test changes.
3. **Configuration and generated sources:** normalized schema, path-independent
   workload identity, deterministic SCons generation, one working FU-remapping
   tutorial and recorded effective settings.
4. **Native observability and lifecycle:** statistics/ROI parity, clocks,
   request/response backpressure, drain and idle checkpoint tests. Mid-kernel
   serialization remains a separate larger project.
5. **Portable examples and optional Workbench:** a small, versioned workload
   resource and a native TestLib entry point; keep GUI, Windows appliance and
   visualization as separately reviewable tooling.

Do not submit the entire historical merge history or bulk evidence/binaries.
Prepare a clean series based on the then-current upstream development branch,
retaining authorship and a clear comparison against PR #2429. Submitting,
commenting on or replacing an official PR is outside this checkpoint.

## Checkpoint boundaries and retained legacy ideas

- Existing GEMM/FFT/stencil positives, independent numerical rejection and FU
  replay remain required. A normal exit, a guest pass string, a rendered
  visualizer or skipped CI is not a numerical pass.
- The integration adds real native clocks/statistics and bounded correctness
  repairs beyond PR #3 packaging. The linked integration checkpoint records its
  delivery status; open engine/readiness rows remain visible in release notes.
- Legacy December 2025 debug integration is useful diagnostics, not native
  statistics. The December configuration-consolidation plan remains useful.
  The recovered `salam-core` abstraction is a scaffold, not an active engine
  split. January toolkit analytics should consume current evidence rather than
  restore a second runner.
- The old eleven-tool ecosystem roadmap is a research backlog. Native metrics,
  validated memory selection and one optional RTL correlation should precede
  broad external integrations. Old “approved” labels and time estimates are
  historical text, not current authorization or tested compatibility.
- Preserve the known GCC failures, inconsistent native hash observations and
  two monolithic audit aborts as historical evidence. A new successful build
  does not retrospectively establish their causes or resolve every case; see
  the existing known-gaps record and current integration checkpoint.
