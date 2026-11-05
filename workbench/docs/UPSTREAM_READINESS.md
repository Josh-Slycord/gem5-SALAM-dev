# Upstream readiness for Josh's SALAM workbench

Review snapshot: **5 November 2026**. This is a preparation and evidence
register, not a submission to gem5 and not a claim of upstream acceptance.

The immediate checkpoint integrates the packaging/visualization contribution
from [our PR #3](https://github.com/Josh-Slycord/gem5-SALAM-dev/pull/3).
The next milestones should answer the questions already raised on
[gem5 PR #2429](https://github.com/gem5/gem5/pull/2429), using this fork's
implementation and independently reproducible evidence.

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
- The review below separates source inspection from runtime reproduction.
  No new simulator regression for these findings was run while writing this
  document. Existing qualification is bounded by
  [GEM5_26_VALIDATION.md](GEM5_26_VALIDATION.md) and
  [GEM5_26_KNOWN_GAPS.md](GEM5_26_KNOWN_GAPS.md).

Akanksha's replies also point to
[gem5-salam-develop-clocked-working](https://github.com/akanksha-sc/gem5/tree/gem5-salam-develop-clocked-working)
for additional scheduling, PPA, cycle tracking and stdlib work. That is an
important comparison lead, not verified integration into our fork. Preserve
original authorship and review each selected change against our zero-limit
semantics, complete FU replay and numerical checks. Do not wholesale replace
our engine or describe another contributor's work as ours.

## What reviewers actually asked

Priorities below are our proposed ordering. They are not priorities assigned
by upstream maintainers. “P0” means resolve or explicitly gate before a claim
of broad correctness or an upstream submission; it does not mean the
packaging-only checkpoint changed these engine paths.

| ID / priority | Reviewer concern and source | Upstream discussion state | This fork: inspected state and required evidence |
| --- | --- | --- | --- |
| U01 / P0 | Jason Lowe-Power asked how reviewers can establish correctness, non-regression and maintenance cost, and requested a logically reviewable contribution rather than one large dump. [2025-08-04](https://github.com/gem5/gem5/pull/2429#issuecomment-3152676127); Giacomo agreed and requested verifiers/style alignment [2025-08-07](https://github.com/gem5/gem5/pull/2429#pullrequestreview-3096297334). | General discussion, with author/maintainer replies reporting tests and proposing integration stages; not a blanket approval. | Our 661-check and six-case evidence is stronger than guest markers, but is not the entire upstream regression suite. Prepare a small patch series, architecture/read-path guide, native TestLib/GTest coverage, default-build non-regression and clean-host reproduction. Keep GUI/appliance convenience separately reviewable from simulator changes. |
| U02 / P0 | LLVM must not become a dependency of ordinary gem5 builds; linker flags must be handled correctly. [Dependency](https://github.com/gem5/gem5/pull/2429#discussion_r2252731328), [linking](https://github.com/gem5/gem5/pull/2429#discussion_r3888887820). | Inline threads resolved; later author reported opt-in setup and an LLVM link-test branch. | `SConstruct` adds `--with-salam`; `src/hwacc/SConscript` gates LLVM queries and uses `MergeFlags` for shared-link flags, with a deliberate LLVM 14 floor/ceiling. Existing SALAM build passed. Still require CI proving a default non-SALAM build without LLVM, supported opt-in builds, and actionable missing/wrong-version failures. Source CI alone is insufficient. |
| U03 / P0 | An unsupported opcode must fail explicitly rather than become a successful zero-cycle operation. Validate types and external calls too. [Bobby Bruce](https://github.com/gem5/gem5/pull/2429#discussion_r3951549752). | Resolved upstream. | Our `llvm_interface.cc::createInstruction` default still warns and creates `BadInstruction` unless mapped to a constrained FU. `ir_toolchain.py` rejects known `fneg`/fused-call cases only. Add a complete support boundary, fatal diagnostics with IR location, and negative actual-simulator tests. Three correct numerical workloads do not establish unsupported-IR rejection. |
| U04 / P0 | Register-bank timing responses can re-enter and delete a request before the caller finishes accessing it. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550093). | Resolved upstream. | Our `comm_interface.cc::tryRead(RegPort*)` and write counterpart access the request after `sendPacket`. Source risk matches the reported pattern; runtime reproduction in this fork remains pending. Add a synchronous-response reproducer/ASan target, establish ownership, then fix without changing timing accidentally. |
| U05 / P0 | DMA write-FIFO functional/bypass operation reads destination bytes instead of writing queued bytes; preserve routing. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550193). | Resolved upstream. | Our `dma_write_fifo.cc::resumeEmptyFunctional` still uses `physProxy.readBlob` and writes into its buffer. Timing positives do not exercise bypass. Either correctly implement selected-port writes or reject the mode explicitly; test equal destination bytes in timing and bypass cases. |
| U06 / P0 | Scratchpad shared response queue must obey the blocked head port's retry state under concurrent traffic. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550288). | Resolved upstream. | Our `scratchpad_memory.cc` still checks the new request's `retryResp[idx]` when scheduling one shared dequeue event. Add a forced-backpressure two-port test, then use correct shared-head gating or per-port queues. This needs protocol evidence, not just final output equality. |
| U07 / P0 | Opcode identifiers used as map keys were not initialized. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550530). | Resolved upstream. | Our `HWModeling/src/opcodes.cc` still inserts `counter_inst`, `sitofp_inst` and other members absent from its initializer list; the header has no defaults. Audit supported IDs, initialize legitimate entries and disable unused entries with explanation. Test deterministic map contents and sanitizer behavior. |
| U08 / P0 | LLVM `frem` requires the correct remainder semantics. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951550649). | Resolved upstream. | The active non-AP path in `LLVMRead/src/instruction.cc` still uses `std::remainderf/remainder`. Add float/double numerical opcode tests (including signs and exceptional inputs), compare to the matched LLVM semantics, then correct the operation. GEMM/FFT/stencil acceptance is not coverage of every opcode. |
| U09 / P0 | Execution graph ownership cycles can retain previous launches. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951549542). | Resolved upstream, current-location thread. | `basic_block.hh` and `instruction.hh` retain owning `shared_ptr` graph edges. Do not infer a demonstrated leak merely from pointer types: audit teardown and queued users. Require repeated-launch lifetime/leak evidence, explicit graph ownership, and safe cleanup after pending packets/events. |
| U10 / P1 | Existing instructions must be remappable to a custom FU with a complete, working tutorial; inventing an opcode number does not implement a new instruction. [Original](https://github.com/gem5/gem5/pull/2429#discussion_r3827697361), [clarification](https://github.com/gem5/gem5/pull/2429#discussion_r3984422730), [remaining proxy failure](https://github.com/gem5/gem5/pull/2429#discussion_r3984995472). | Three tutorial threads unresolved, despite intermediate fixes/replies; locations outdated. | Our tested knob coverage changes existing units, latency/limits and compiled profile fields. It does not establish arbitrary new FU registration, remapping or new instruction behavior. Add one end-to-end relocation-independent tutorial that regenerates, registers, rebuilds, witnesses the mapping and checks output. Unsupported examples must be clearly disabled, never presented as runnable features. |
| U11 / P1 | Use one normalized schema/defaults across simulation, header generation and offline tools; reject unused/unknown settings. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951548509). | Unresolved, current location. | Workbench validation and receipts exist, but legacy `salam_config`, configurator and offline consumers coexist. Inventory all keys and defaults, make one typed contract, reject unsupported keys, and compare every consumer on omitted/default/invalid fields. Do not claim every GUI knob works from schema acceptance. |
| U12 / P1 | Avoid writing executable Python configuration as strings; prefer maintained factories/components. [Factory](https://github.com/gem5/gem5/pull/2429#discussion_r3909524253), [stdlib direction](https://github.com/gem5/gem5/pull/2429#discussion_r3951546390). | Factory thread resolved after upstream author changed architecture; stdlib thread unresolved. | This fork still generates system Python through `SALAM-Configurator/fs_template.py` and calls legacy `Simulation.run`. Build a maintained accelerator component/configuration adapter, preserving generated configuration witnesses. A kernel/disk-oriented ArmBoard is not automatically compatible with our bare-metal route. |
| U13 / P1 | Generate changing hardware sources through SCons, rather than require a custom tracked-source branch per technology/profile. [Review and follow-up](https://github.com/gem5/gem5/pull/2429#discussion_r3909484005). | Unresolved; follow-up acknowledges current compromise but recommends build integration. | Our isolated variant generation/rebuilds are real and verified, but not native SCons dependency generation. Keep variant isolation and provenance, then add declared inputs/outputs, deterministic generation and rebuild/cache-invalidation tests. Never ignore hand-written source indiscriminately. |
| U14 / P1 | Use native accelerator statistics with normal dump/reset semantics and ROI boundaries. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951549007). | Unresolved, current location. | Our invocation JSON/FU event streams are real; no custom SALAM `statistics::Group` or probe registration was found. Add native groups alongside raw evidence, reconcile two invocations and reset/dump behavior, and keep whole-guest versus accelerator-only scope explicit. |
| U15 / P1 | Clock-domain changes must affect accelerator/DMA event timing consistently. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951549136). | Unresolved, current location. | `ComputeUnit` is a plain SimObject; LLVM/communication paths multiply manual periods by 1000 and schedule relative ticks. Port to clocked objects/helpers and explicit domains, then prove tick scaling and baseline timing equivalence. Merely setting `clk_domain` does not fix this. |
| U16 / P1 | Repeated instruction/FU parameter wrappers could be common configuration data types. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3951548839). | Unresolved, current location. | Generated wrapper pairs remain. Evaluate a common typed data representation after correctness/schema contracts; preserve opcode-specific execution behavior. This need not require simulator-independent engine extraction. |
| U17 / P1 | Fractional PPA fields must survive configuration, and reported values must use one documented model. [Types](https://github.com/gem5/gem5/pull/2429#discussion_r3888887836), [model consistency](https://github.com/gem5/gem5/pull/2429#discussion_r3888887838). | Resolved upstream, with author stating the full reporting path lived on another branch. | Float parameters and compiled profile witnesses exist here. Legacy `LLVMInterface::printResults` still contains separate hard-coded coefficients; `SALAMPowerModel` remains an empty SimObject. Preserve model estimates as uncalibrated, label the legacy printout, and require activity-count/units reconciliation before native power integration or physical claims. |
| U18 / P1 | Enable cycle tracking through actual parameters or stop presenting unreachable code as a supported feature. [Review](https://github.com/gem5/gem5/pull/2429#discussion_r3888887861). | Resolved upstream after author identified implementation on another branch. | Our `HWModeling/src/hw_statistics.hh` still has `cycle_tracking=false`; the constructor does not expose a switch. Current workbench/FU JSON is a separate implemented path. Mark this legacy scaffold inactive; do not enable it without buffer/lifetime tests and a consumer. |
| U19 / P0 before submission | Audit file-specific provenance/license obligations and maintainers instead of applying a blanket special notice. [License](https://github.com/gem5/gem5/pull/2429#discussion_r3909457012), [ownership](https://github.com/gem5/gem5/pull/2429#discussion_r2193177427). | License thread unresolved; original maintainer thread resolved. | No legal/provenance audit completed in this checkpoint. Preserve existing notices; create an origin/license manifest for original SALAM, gem5, LLVM, generated data, CACTI and new code. Obtain correct maintenance commitments from people; do not invent owners or remove notices speculatively. |
| U20 / P1 | Document supported environments, workload/resource layout, native m5ops and optional offline-tool behavior. [Ubuntu](https://github.com/gem5/gem5/pull/2429#discussion_r3485233960), [m5ops](https://github.com/gem5/gem5/pull/2429#discussion_r3322311057), [CACTI no-SPM](https://github.com/gem5/gem5/pull/2429#discussion_r3971471287). | These threads resolved with author/reviewer follow-ups. | Our supported, source-bound profile remains Ubuntu 24.04/LLVM 14 with recorded limits. The new Ubuntu 22.04 appliance is a separate recipe until built/imported/qualified. Add a fresh-host test and relocatable versioned workload resources. Empty CACTI output for a RegisterBank-only workload is not evidence that the tool failed or that SRAM power was modeled. |

## Resolved findings that still guide regression tests

Do not blindly port an old reviewer suggestion: several were fixed in upstream
and some are independently fixed here. In this fork the instruction
configuration base initializes its members, functional-unit profile fields use
floating point, and `genHeaderFiles` pairs each cluster with its own saved
header. These are source observations, not new runtime tests.

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
- The PR #3 visualizer/appliance can become a useful delivery checkpoint while
  the engine readiness rows above remain open. Correctness findings must be
  visible in release notes and must not be hidden by a polished dashboard.
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
  two monolithic audit aborts. This packaging checkpoint does not establish
  their cause or resolve them; see the existing known-gaps record.
