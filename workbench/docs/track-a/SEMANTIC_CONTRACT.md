# Track A configuration compatibility contract

Status: source-audited migration targets, 2026-11-05 America/New_York.
No new simulator execution or qualification is claimed by this document.

Our source baseline is f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb.
The protected integration tag and qualified runtime remain the reference.
PR #2429 is compared at b4ff9f5aaa0e4d3df9bf503df2212a278eb59645;
its develop base is pinned separately in the evidence index.

## Scheduling and instruction configuration

| Input / mechanism | Baseline behavior to preserve | Migration requirement |
| --- | --- | --- |
| FU limit == 0 | Unlimited pooled occupancy; still tracked and released. | Never reinterpret as static graph count. PR #2429 uses that different policy. |
| FU limit > 0 | Caps outstanding dynamic leases for that FU ID. | Preserve admission, denial, release and per-launch reset witnesses. |
| Instruction functional_unit == 0 | No FU lease for that instruction. | Keep distinct from an unlimited nonzero FU ID. |
| Instruction functional_unit_limit == 0 | Neutral: no separate instruction cap; a finite FU limit still applies. | Nonzero remains explicitly unsupported until a separately tested policy exists. |
| Logical instructions.*.runtime_cycles | HWAccConfig writes CycleCounts; instruction creation reads that path. | Keep one latency authority and preserve zero-cycle instruction values. |
| InstConfigBase.runtime_cycles | Separately stored value; storage alone does not schedule latency. | Do not switch to it accidentally during generic-Params migration. |
| FU cycles / stages / datatype metadata | Stored/model metadata with bounded no-consumer findings in the audit. | Do not promise initiation-interval or pipeline behavior from these fields. |

Memory/control/call paths keep their separate zero-cycle and scheduling\nrestrictions; a forwarded CycleCounts value is not proof that arbitrary\nnonzero latency is supported for every LLVM opcode.\n\nThe authoritative FU path is LLVMInterface::tryAcquireFU/releaseFU into
FUSchedulingPool. The retained Instruction::hasFunctionalUnit returns false;
reactivating the old HWInterface accounting path would risk dual accounting.
Zero occupancy at invocation start and balanced leases at completion are
migration invariants, separate from graph-allocation leak tests.

Source anchors in our pinned tree:
- configs/SALAM/HWAccConfig.py:274 (logical latency forwarding).
- src/hwacc/llvm_interface.cc:908 (pooled admission/release).
- src/hwacc/llvm_interface.cc:948 (model registration and instruction-cap rejection).
- src/hwacc/llvm_interface.cc:1339 (instruction construction).
- src/hwacc/fu_scheduling_pool.hh:127 (zero/finite limit behavior).
- src/hwacc/LLVMRead/src/instruction.hh:81 (retained legacy FU hook).

## Clocks, power and physical characterization

Native clock translation must occur after the final scalar overrides and CPU
setup, immediately before instantiate, as the current adapter does. Retain
integer nanosecond compatibility inputs and reject unsupported direct domain
replacement, CPU switching and multi-system configurations explicitly.
Do not move clock binding earlier merely to make the new factory smaller.

The five-nanosecond characterization-profile directory is not proof that the
accelerator runs at five nanoseconds. The retained operational default is
10 ns; every run must expose its effective native clock domain.

PPA coefficients remain uncalibrated characterization metadata with declared
units (mW, pJ, ns, um^2 in the observed profiles). Propagation into Params or a
statistics object is not validation of physical accuracy. Offline CACTI's
fixed 45 nm policy must remain distinct from a 40 nm FU profile. There is no
established rule for scaling coefficients to a different clock or technology.
Do not invent one.

Source anchors:
- configs/SALAM/HWAccConfig.py:391 (native clock boundary and checks).
- configs/common/Simulation.py:684 (final binding location).
- benchmarks/sys_validation/gemm/configs/hw_interface/functional_units/40nm_model/5ns/default_profile/integer_multiplier/integer_multiplier.yml:29
  (coefficient units; the directory encodes characterization context).
- See CORE_CONSUMERS and LEGACY_CONFIG_CONSUMERS for the separate power/CACTI routes.

## One validated model, several consumers

The next implementation slice should normalize input once, before simulator,
header and offline-tool consumers diverge. Preserve source file/line and
explicit/default origin for every normalized field. Expose a consumer status:
effective, metadata-only, explicitly unsupported, or unresolved. A field
cannot be advertised as effective merely because it is accepted by a GUI.

The following are implementation requirements, not claims of existing support:

1. Detect duplicate keys before PyYAML dictionary construction. The census
   found 122 repeated keys across seven legacy files; all repeated value
   nodes serialize identically. No conflicting-value bug was demonstrated.
   A migration diagnostic can explain identical historical duplicates;
   strict input must not silently lose competing definitions.
2. Define unknown-key handling and per-device key applicability. Current
   acceptance of a stream-only option on another memory type is not proof
   of an active consumer.
3. Resolve paths relative to an explicit source/project root, retaining the
   distinction among IrPath, ConfigPath, legacy tools HWPath and SysPath.
   Root and tools configurators currently disagree. Do not normalize them
   by string concatenation or by treating an old .ini example as YAML.
4. Make address, alignment, interrupt, port cardinality and PIO connection
   defaults identical in the factory, headers and validation output.
   An omitted PIOMaster must not validate as connected if the raw builder
   emits no connection.
5. Keep declared port-vector cardinality separate from the actual C++ port
   implementation. RegisterBank multiport support needs its own executable
   fixture before a factory can expose it.
6. Treat cache construction and unsupported export hooks as unresolved until
   their actual connection/consumer is established; do not preserve no-op
   switches as working controls.
7. Record normalized schema, profile, generated-input and simulator-source
   identities. Python/YAML evidence alone cannot certify the binary.

## Build and adoption boundaries

Use the current PR's schema/factory and build-tree generation patterns as
reviewable reference designs. Its generic instruction/FU objects are not
ABI-compatible replacements for our named generated wrappers. Its scheduling
policy is also different. Adapt front-end structure while retaining our
qualified numerical, clock, statistics, trace and reset behavior.

A build-tree SCons action must declare every profile/template dependency,
avoid writing into tracked source, and remain gated behind opt-in SALAM.
The default build must not require LLVM. Explicit LLVM selection must validate
the supported major; a discovery-name list is not a tested support matrix.

Start with an isolated direct GEMM factory whose effective configuration can
be compared with the retained builder. Then prove requested changes reach
real simulation with numerical oracles and deliberate failure controls.
Do not claim LLVM 11-20 compatibility, new physical modeling, a complete
stdlib board, or full memory/drain/leak qualification from this audit.

## Parallel-work contract

Track A owns normalization, factory interfaces, SCons/build integration and
the integration branch. Josh assigned Gemini B1 (bounded UART writes) and B3
(provenance/licensing review). Their status is not inferred here and their
worktrees are not edited. Integration must preserve the qualified checkpoint;
official repositories receive no writes, requests, comments or pushes.

Required merge gates for the first implementation slice are recorded in
NEXT_SLICE.md. The current audit does not satisfy those runtime gates.
