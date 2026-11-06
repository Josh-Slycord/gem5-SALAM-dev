# Track A: current PR #2429 source comparison

Local audit date: 2026-11-05. Created UTC: 2026-11-06T00:57:45.267266+00:00.
Pinned snapshots created UTC: 2026-11-06T00:43:57.010515+00:00.

Current PR #2429 already implements shared workload parsing, a direct cluster
factory, a bare-metal standard-library board and one generated profile data
module. These are strong native-integration starting points. They are not a
drop-in for our qualified engine: FU zero semantics, the generated Params ABI,
PPA contracts and LLVM assumptions differ.

This audit reads actual pinned code. Comparison is source-only; no simulator
builds/runs or production edits were performed. No pushes or official
repository
mutations were made. The qualified checkpoint remains untouched. JSON carries
exact source lines, SHA-256/Git
blob identities, impacts and required validation.

## Pinned sources

- Our baseline: `f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb` in `/home/jslycord/projects/gem5-salam-track-a`.
- [PR #2429](https://github.com/gem5/gem5/pull/2429) author head: `b4ff9f5aaa0e4d3df9bf503df2212a278eb59645` (`akanksha-sc/gem5`).
- Official develop inspection base: `1754a3b1789c6fd616124f89116b8258600e8b85` (`gem5/gem5`).
- Source snapshots/manifests: `/home/jslycord/projects/salam-track-a-references-20261105`.

Reviewer discussion links below preserve the question being answered.
Resolved/unresolved/outdated metadata is not evidence that current code passes
or fails. The pinned actual source determines the comparison.

## Decision matrix

| ID | Area | Decision |
|---|---|---|
| A01 | Shared parser and direct cluster factory | **adapt** |
| A02 | Bare-metal standard-library board | **adapt** |
| A03 | Single profile data module and SCons dependency graph | **adopt** |
| A04 | Generic FU/instruction Params ABI | **adapt** |
| A05 | Zero FU limit semantics | **reject** |
| A06 | Pipelined initiation interval | **defer** |
| A07 | Active latency versus descriptive metadata | **adapt** |
| A08 | Native compute/fabric clocks and final overrides | **adapt** |
| A09 | Provenance-aware physical characterization | **defer** |
| A10 | LLVM support and dependency policy | **reject** |
| A11 | Unsupported IR rejected in actual engine | **adapt** |
| A12 | Native metrics and direct invocation evidence | **adapt** |
| A13 | Queue safety and object-lifetime preservation | **reject** |
| A14 | Native TestLib and evidence reconciliation | **adopt** |

## Evidence and change impact

### A01: Shared parser and direct cluster factory

Current PR already embeds the normalized workload reader and directly
constructs SimObjects. Its native path does not require per-benchmark generated
Python. Paths are relative to the declaring YAML and recursive SysPath includes
reject.

**Our source:** [configs/SALAM/HWAcc.py:61](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/SALAM/HWAcc.py#L61); [configs/SALAM/HWAccConfig.py:117](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/SALAM/HWAccConfig.py#L117).

**Current PR source:** [src/python/gem5/salam/cluster.py:64](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/cluster.py#L64); [util/SALAM-tools/SALAM-Configurator/config_parser.py:54](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/SALAM-Configurator/config_parser.py#L54); [src/python/SConscript:256](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/SConscript#L256).

**Impact:** Adopt this architecture with an adapter for current workbench YAML,
leaf IR paths, class names and address allocation; schema compatibility is not
automatic.

**Preserve:** Every accepted field has an active consumer or a
pre-instantiation error; source/effective input identities stay recorded.

**Required evidence:** Roundtrip current GEMM YAML;
unknown-field/missing/include-cycle negatives; inspect config.ini and
independently check numeric output.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951548509).

### A02: Bare-metal standard-library board

PR SALAMArmBoard uses ArmFsWorkload, explicit ELF setter and direct attachment.
It requires a classic hierarchy exposing membus and bypasses Linux-specific
ArmBoard pre-instantiation setup.

**Our source:** [configs/common/Simulation.py:684](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/common/Simulation.py#L684); [src/hwacc/ComputeUnit.py:7](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/ComputeUnit.py#L7).

**Current PR source:** [src/python/gem5/salam/board.py:52](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/board.py#L52); [configs/example/gem5_library/salam/arm-baremetal-salam.py:82](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/configs/example/gem5_library/salam/arm-baremetal-salam.py#L82).

**Impact:** Add a separate native GEMM route using current engine first. The
lifecycle override is version-sensitive; validate against pinned develop. Keep
legacy runner available.

**Preserve:** Fixed CPU/single system scope; same ELF/exit
transport/independent output checks; qualified checkpoint untouched.

**Required evidence:** Actual board instantiate and config.ini wiring, clocks,
ELF; real seeded GEMM plus deliberate corruption; final scalar override
precedence.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951546390).

### A03: Single profile data module and SCons dependency graph

PR generates only _salam_profile.py, declares
config/instruction/FU/generator/power-parser inputs and embeds data in the
variant build. This is a cleaner target than our generated typed wrapper graph
and temporary text patching.

**Our source:** [src/hwacc/SConscript:61](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/SConscript#L61); [workbench/salam_workbench/hardware_codegen.py:165](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/workbench/salam_workbench/hardware_codegen.py#L165).

**Current PR source:** [util/SALAM-tools/hw_generator/SALAMGeneratedSources.py:135](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/hw_generator/SALAMGeneratedSources.py#L135); [src/salam/SConscript:64](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/SConscript#L64).

**Impact:** Adopt variant-local declared generation, coupled to A04 generic ABI
conversion. Do not remove wrapper outputs while C++ includes require them. This
exact PR still selects profile data at build time; it is not unrestricted hot
reload.

**Preserve:** Determinism, content hashes, rebuild provenance and capability
checks; fractional PPA stays floating point.

**Required evidence:** Clean/out-of-tree build; edit every input category and
verify rebuild; isolated profiles do not contaminate; unchanged input stable.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3909484005).

### A04: Generic FU/instruction Params ABI

PR uses generic FunctionalUnit/InstructionConfig entries with vector Params and
camelCase getters. Ours uses FunctionalUnitBase/InstConfigBase, generated typed
members and snake_case getters. Upstream Python data objects alone cannot
satisfy our C++ ABI.

**Our source:** [src/hwacc/HWModeling/src/functional_units.hh:4](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/src/functional_units.hh#L4); [src/hwacc/HWModeling/src/instruction_config.hh:4](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/src/instruction_config.hh#L4); [src/hwacc/HWModeling/src/hw_interface.hh:9](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/src/hw_interface.hh#L9); [src/hwacc/llvm_interface.cc:948](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L948).

**Current PR source:** [src/salam/FunctionalUnits.py:52](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/FunctionalUnits.py#L52); [src/salam/InstConfig.py:50](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/InstConfig.py#L50); [src/salam/HWModeling/functional_units.hh:54](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/HWModeling/functional_units.hh#L54); [src/salam/HWModeling/hw_interface.hh:72](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/HWModeling/hw_interface.hh#L72).

**Impact:** Own C++ changes: generic entries/constructors, vectors/ownership,
lookup/getter adaptation, HWInterface Params/includes, LLVMInterface iteration
and SCons. Preserve scheduler semantics; retire old wrapper dependency graph
only after no consumers remain.

**Preserve:** Unknown/duplicate ID rejection; opcode mapping; no live occupancy
at start/end; complete FU trace/replay.

**Required evidence:** Pure mapping/accessor fixtures then actual SimObject
ownership/config.ini, old/new GEMM numeric and trace parity, finite/unlimited
sweeps.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951548839).

### A05: Zero FU limit semantics

Actual PR C++ resolves limit=0 to one instance per reachable static instruction
and uses that finite pool. Our pool treats limit=0 as no occupancy cap. This is
a scheduling change, not configuration cleanup.

**Our source:** [src/hwacc/fu_scheduling_pool.hh:118](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/fu_scheduling_pool.hh#L118); [src/hwacc/llvm_interface.cc:948](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L948).

**Current PR source:** [src/salam/FunctionalUnits.py:57](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/FunctionalUnits.py#L57); [src/salam/llvm_interface.cc:1519](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1519).

**Impact:** Reject implicit replacement. Keep unlimited=0 for existing
profiles. A future static_graph sizing mode needs a named policy and schema
migration.

**Preserve:** Finite/unlimited behavior; per-instruction cap=0 means no extra
requested cap, not exemption from a finite FU cap.

**Required evidence:** Caps 0/1/2/4 with enough ready dynamic operations to
distinguish static sizing from unlimited; independent complete lease replay
with zero outstanding.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951548839).

### A06: Pipelined initiation interval

PR pool assigns per-instance nextIssue and allows overlap for interval>0; zero
is unpipelined. Our current pool is nonpipelined occupancy capacity. PR YAML
omits interval to mean zero; explicit interval must be >=1.

**Our source:** [src/hwacc/fu_scheduling_pool.hh:4](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/fu_scheduling_pool.hh#L4); [src/hwacc/fu_scheduling_pool.hh:118](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/fu_scheduling_pool.hh#L118).

**Current PR source:** [src/salam/HWModeling/fu_pool.cc:76](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/HWModeling/fu_pool.cc#L76); [src/salam/llvm_interface.cc:1591](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1591); [util/SALAM-tools/hw_generator/SALAMGeneratedSources.py:454](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/hw_generator/SALAMGeneratedSources.py#L454).

**Impact:** Defer until native configuration parity. Requires per-instance
accounting, tick conversion, completion leases and richer independent replay.

**Preserve:** Logging budget never changes scheduling; throughput separated
from operation latency; grant/deny/release audit retained.

**Required evidence:** Long-latency overlap microkernel; expected admission
ticks for intervals 1/2 and unpipelined; overflow and relaunch controls.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951548839).

### A07: Active latency versus descriptive metadata

Both engines execute instruction latency from CycleCounts. PR labels FU
stages/cycles/datatype fields descriptive and rejects obsolete
instruction-profile runtime_cycles/functional_unit_limit. Workload
runtime_cycles remains active. Our existing _apply_cycle_counts path is active.

**Our source:** [configs/SALAM/HWAccConfig.py:274](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/SALAM/HWAccConfig.py#L274); [src/hwacc/llvm_interface.cc:1338](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1338); [src/hwacc/HWModeling/generated/functionalunits/base.hh:113](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/functionalunits/base.hh#L113).

**Current PR source:** [src/salam/FunctionalUnits.py:64](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/FunctionalUnits.py#L64); [src/python/gem5/salam/cluster.py:325](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/cluster.py#L325); [util/SALAM-tools/SALAM-Configurator/config_parser.py:715](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/SALAM-Configurator/config_parser.py#L715); [util/SALAM-tools/hw_generator/SALAMGeneratedSources.py:242](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/hw_generator/SALAMGeneratedSources.py#L242).

**Impact:** Adopt one latency path with honest labels; move active legacy
runtime cycles into workload overrides; remove only redundant generated
storage; reject unsupported nonzero instruction caps; preserve name
normalization.

**Preserve:** GUI latency reaches actual CycleCounts; descriptive metadata is
not presented as execution control.

**Required evidence:** Latency sweep changes real issue/completion ticks while
numeric output stays equal; reject unsupported nonzero
memory/immediate-terminator latencies.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951548509).

### A08: Native compute/fabric clocks and final overrides

PR creates Compute/Fabric native domains and binds accelerator versus local
bus/DMA/memory; compute scheduling uses clockEdge. Our native engine already
uses clockEdge but requires retained integer-ns clock_period to match
clk_domain after final scalar overrides.

**Our source:** [configs/SALAM/HWAccConfig.py:391](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/SALAM/HWAccConfig.py#L391); [configs/common/Simulation.py:684](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/common/Simulation.py#L684); [src/hwacc/llvm_interface.cc:22](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L22); [src/hwacc/llvm_interface.cc:494](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L494).

**Current PR source:** [src/python/gem5/salam/cluster.py:106](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/cluster.py#L106); [src/python/gem5/salam/cluster.py:247](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/cluster.py#L247); [util/SALAM-tools/SALAM-Configurator/workload_config.py:514](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/SALAM-Configurator/workload_config.py#L514); [src/salam/llvm_interface.cc:1241](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1241); [configs/example/gem5_library/salam/arm-baremetal-salam.py:98](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/configs/example/gem5_library/salam/arm-baremetal-salam.py#L98).

**Impact:** Adapt direct native domains while reconciling legacy clocks only
after scalar overrides. First slice keeps integer-ns constraints; arbitrary
frequencies need replacing our constructor checks in
LLVMInterface/CommInterface/DMA and separate qualification.

**Preserve:** Edge alignment and no duplicate same-edge pass; independent actor
clocks; reset semantics; CPU switching/distributed roots remain unqualified.

**Required evidence:** Existing 10/3 ns plus nonaligned launches; independent
Compute/Fabric sweeps; config.ini; conflicting override negatives; repeated
launches around native reset.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951549136).

### A09: Provenance-aware physical characterization

PR has source JSON, implementation IDs, signatures, physical units/geometry and
incomplete-coverage policy for PPA accounting. Our SALAMPowerModel C++ is an
empty constructor; legacy coefficients elsewhere are not an interchangeable
calibrated model.

**Our source:** [src/hwacc/HWModeling/src/salam_power_model.cc:1](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/src/salam_power_model.cc#L1); [src/hwacc/HWModeling/generated/functionalunits/base.hh:32](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/functionalunits/base.hh#L32).

**Current PR source:** [src/salam/SALAMPowerModel.py:51](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/SALAMPowerModel.py#L51); [util/SALAM-tools/hw_generator/SALAMGeneratedSources.py:466](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/util/SALAM-tools/hw_generator/SALAMGeneratedSources.py#L466); [src/python/gem5/salam/cluster.py:289](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/cluster.py#L289).

**Impact:** Defer full migration after configuration/FU parity. Adopt
units/provenance/coverage vocabulary; never turn legacy configured coefficients
into calibrated results by renaming. C++ event accounting, memory observers and
inventory are required.

**Preserve:** Unknown is not zero; configured uncalibrated coefficients remain
labeled; observer cannot change numerical execution.

**Required evidence:** Synthetic energy ledger; missing/mixed units/geometry
negatives; observer enabled/disabled execution parity; source hashes/coverage
visible.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951548839).

### A10: LLVM support and dependency policy

Ours explicitly checks LLVM major 14 and typed-pointer IR. PR lists LLVM 11-20
for suffixed executable discovery, but explicit LLVM_CONFIG or PATH llvm-config
is not major-version checked by configure_llvm_for_salam. Link
flags/ABI-disable macros do not prove our engine supports that range.

**Our source:** [src/hwacc/SConscript:19](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/SConscript#L19); [src/hwacc/LLVMRead/src/value.cc:67](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/LLVMRead/src/value.cc#L67).

**Current PR source:** [SConstruct:466](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/SConstruct#L466); [src/salam/LLVMRead/value.cc:162](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/LLVMRead/value.cc#L162); [src/salam/LLVMRead/instruction.cc:1939](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/LLVMRead/instruction.cc#L1939).

**Impact:** Reject blanket version broadening and
LLVM_DISABLE_ABI_BREAKING_CHECKS_ENFORCING transplant. Keep optional LLVM14
gate until each toolchain/IR is tested. PR DataLayout handling is promising but
spans value/register/GEP/cast/comparison semantics, not a header-only import.

**Preserve:** Ordinary gem5 has no LLVM dependency; actionable wrong/missing
version errors; gem5 compiler/exception policy preserved; unsupported types
fail closed.

**Required evidence:** Non-SALAM build without LLVM; missing/wrong LLVM
negatives; exact executable/version/link flags recorded;
compiler/IR/pointer/type/address-space matrix.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r2252731328).

### A11: Unsupported IR rejected in actual engine

PR rejects atomics including atomic load/store and FenceInst before opcode
dispatch, and rejects recursion while constructing graph. Ours has explicit
unsupported-opcode fatal, but atomic load/store use ordinary Load/Store opcodes
and are not rejected by that switch alone.

**Our source:** [src/hwacc/llvm_interface.cc:1309](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1309); [src/hwacc/llvm_interface.cc:1380](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1380).

**Current PR source:** [src/salam/llvm_interface.cc:776](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L776); [src/salam/llvm_interface.cc:1659](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1659); [src/salam/llvm_interface.cc:1891](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1891).

**Impact:** Plan own C++ pre-dispatch atomic/Fence rejection and explicit
bounded recursion checks; compare existing unconditional CFG guard before
transplant. Workbench preflight supplements, not substitutes for, native
boundary checks. No implementation in this audit.

**Preserve:** Actual simulator negative modules exit nonzero with IR context;
rejected IR cannot proceed to numeric oracle.

**Required evidence:** Assembler-valid atomic load/store/RMW/cmpxchg/fence;
direct/indirect recursion policy; unsupported scalar/vector/aggregate modules
through native and GUI routes.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951549752).

### A12: Native metrics and direct invocation evidence

PR has execution/per-unit native stats and quiescence assertion. Ours
additionally emits invocation JSON/full FU JSON and resettable
completedInvocations/invocationTicks. Whole-file engine replacement would
change observable contracts.

**Our source:** [src/hwacc/llvm_interface.cc:30](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L30); [src/hwacc/llvm_interface.cc:1034](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1034); [src/hwacc/fu_scheduling_pool.hh:161](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/fu_scheduling_pool.hh#L161).

**Current PR source:** [src/salam/HWModeling/hw_interface.hh:115](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/HWModeling/hw_interface.hh#L115); [src/salam/llvm_interface.cc:186](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L186); [src/salam/llvm_interface.cc:1286](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1286).

**Impact:** Adapt native stats patterns without losing direct JSON/replay
contract. Keep pass counts distinct from elapsed duration, tick-weighted
averages distinct from pass-sampled ones, and specify native-reset versus
invocation-file lifetime.

**Preserve:** No output-banner-only pass; no overwritten invocation files; zero
outstanding leases; reset does not erase independent invocation evidence.

**Required evidence:** Two launches with native reset; reconcile full numeric
output, JSON/native complete/tick counters and independent FU replay;
truncation explicit.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951549007).

### A13: Queue safety and object-lifetime preservation

Our response helper pins blocked/in-callback heads and avoids iterator
underflow; CommInterface snapshots packet direction before ownership transfer.
Both engines explicitly release graph edges on finalize. Front-end migration
does not justify whole-engine/device overwrite.

**Our source:** [src/hwacc/response_queue.hh:13](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/response_queue.hh#L13); [src/hwacc/comm_interface.cc:103](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/comm_interface.cc#L103); [src/hwacc/comm_interface.cc:142](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/comm_interface.cc#L142); [src/hwacc/llvm_interface.cc:1072](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1072).

**Current PR source:** [src/python/gem5/salam/cluster.py:285](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/python/gem5/salam/cluster.py#L285); [src/salam/llvm_interface.cc:1294](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/src/salam/llvm_interface.cc#L1294).

**Impact:** Reject wholesale engine/device replacement. Review upstream hunks
separately with behavior tests; preserve queue, float conversion,
clock-overflow and teardown repairs. Helper tests do not prove all real
SimObject backpressure/drain cases.

**Preserve:** Response ordering, retry/callback packet lifetime, bounded float
conversion/clock guards, fresh graph per invocation.

**Required evidence:** Helper regressions plus actual SimObject forced
request/response backpressure, synchronous callbacks and bypass/drain/lifetime
cases as separate gates.

### A14: Native TestLib and evidence reconciliation

PR contains TestLib suites, board wiring assertions and expected-suite checker
rejecting missing/skipped/zero tests. Source presence is useful design
evidence, not proof these tests passed in this audit or with our engine.

**Our source:** [workbench/docs/UPSTREAM_READINESS.md:104](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/workbench/docs/UPSTREAM_READINESS.md#L104); [src/hwacc/SConscript:3](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/SConscript#L3).

**Current PR source:** [tests/gem5/salam/README.md:3](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/tests/gem5/salam/README.md#L3); [tests/gem5/salam/test_salam_stdlib.py:80](https://github.com/akanksha-sc/gem5/blob/b4ff9f5aaa0e4d3df9bf503df2212a278eb59645/tests/gem5/salam/test_salam_stdlib.py#L80).

**Impact:** Adopt suite/results reconciliation and actual board config
assertions alongside independent numerical/negative workbench checks. Label
helper/SimObject/full-simulation evidence separately; custom profiles require
isolated builds/default restoration.

**Preserve:** No passing zero-test run; exact binary/source/profile identity;
source-only findings never upgrade runtime qualification.

**Required evidence:** Enumerate expected IDs; run bounded suites then
reconcile XML; injected missing-suite/incorrect-output controls fail.

[Related reviewer question](https://github.com/gem5/gem5/pull/2429#discussion_r3951546390).

## Smallest next implementation slice

1. **Freeze compatibility mapping.** First slice keeps current generated FU/instruction ABI and LLVM14 gate. Normalize GEMM workload, profile references, addresses/ports, leaf IR and actor clocks. Every accepted field maps to a consumer or rejects.

2. **Build narrow direct factory.** Use PR parser/factory organization but create our current CommInterface, LLVMInterface, HWInterface, CycleCounts, FunctionalUnits, HWStatistics, InstConfig, InstOpCodes, SALAMPowerModel and SimulatorConfig children. Match existing wiring/address/IR contracts. Fixed compiled unit set initially; new arbitrary units need later ABI migration.

3. **Add native bare-metal GEMM route.** Adapt board pattern with explicit ELF, classic cache/membus/GIC and final override-to-clock reconciliation. Keep old runner. No C++ rewrite is intrinsically needed for existing typed objects, supported scalar IR and integer-ns clocks.

4. **Qualify real parity before generic conversion.** Old and direct routes: same seeded GEMM, independent full output and deliberate corruption, config.ini mapping, caps 0/1/2/4, latency sweep, 10/3 ns clocks, two launches/native reset, direct/native metrics and full FU lease replay.

5. **Convert generic Params and declared profile generation.** Then own C++/Params/header/SCons conversion A03/A04 without static-count zero or new initiation intervals; preserve trace/native stats. Only retire legacy dependency graph after complete consumer search and explicit compatibility decision.

6. **Separate behavior changes.** Atomic/recursion engine fail-closed hardening, pipeline intervals, static sizing, arbitrary clocks, LLVM expansion and characterized PPA each need separately declared semantics and tests.

The first direct-factory experiment can use existing compiled typed objects; a
C++ rewrite is not intrinsically required. Full generic profile migration does
require own C++/Params/header/SCons changes. Separating these phases makes
numerical, timing and trace regressions attributable.

## Clean upstream candidate scope

Fresh candidate on pinned upstream develop; no whole-fork or whole-PR merge.

Include in the first bounded import:

- optional SALAM opt-in registration and bounded LLVM14 dependency handling.
- required compute/communications/memory engine and correctness helpers.
- CycleCounts/FU/InstConfig/HWInterface dependencies required by that engine.
- native Group metrics and bounded test-visible observation/replay contract.
- one direct parser/factory and bare-metal native GEMM example.
- small deterministic workload and numerical/negative TestLib fixtures.

Keep outside the first core candidate or defer:

- Workbench GUI/server/report packaging remains in user fork initially.
- full benchmark corpus, historical experiments and generated outputs.
- legacy generated-code front ends unless a documented transition needs them.
- physical PPA migration, initiation intervals and static-graph zero sizing.
- LLVM version expansion, Ruby/distributed/CPU-switch configurations.

A whole-fork merge is not a reviewable scope merely because ancestry counts
improve. Import the actual engine/configuration/test dependency closure. A
reader without its FU/InstConfig/HWInterface/metrics dependencies is not a
self-contained SALAM core.

Preserve source attribution and every required license/copyright notice. Do not infer new ownership. Scope is a proposal, not approval to delete legacy code. [Reviewer license question](https://github.com/gem5/gem5/pull/2429#discussion_r3909457012).

### Tree scale (metadata only)

| Comparison | Added | Changed | Removed | Identical |
|---|---:|---:|---:|---:|
| Our baseline vs pinned develop | 2083 | 486 | 25 | 10564 |
| PR head vs pinned develop | 241 | 8 | 0 | 11067 |

Ours/current-develop delta includes unrelated upstream drift. It is neither
patch scope nor an ahead/behind commit count. Counts compare tracked blob
paths, not lines; renames are not inferred. JSON records scope buckets.

## Gaps and qualification boundary

- No configuration migration or production edits implemented in Track A.
- No current-PR/proposed native-GEMM build or simulation executed. Existing qualification remains independently scoped.
- Full field-by-field schema compatibility belongs to companion consumer inventories. This comparison traces architecture and selected active contracts.
- Pipelined/static sizing need explicit new policies and independent traces if adopted.
- Actual SimObject forced backpressure, bypass/drain/lifetime, external-call and full IR semantics remain bounded gaps.
- No whole-file review of all upstream devices/algorithms and no whole-PR quality/support claim.

Read alongside the companion core and legacy consumer inventories and parent
Track A report. Source references demonstrate the cited paths, not a new
simulation pass.
