# Track A: configuration audit and PR #2429 comparison

This completes the first source-audit pass. No simulator implementation,
new build, numerical run or GUI qualification is claimed here.

The working branch is codex/native-gem5-milestone in
/home/jslycord/projects/gem5-salam-track-a (Ubuntu-24.04). It starts at the
protected f3f437a29b integration checkpoint. The qualified source worktree,
tag, runtime and official repositories are outside the write scope.

## What the audit establishes

Our current configuration has multiple distinct routes: topology generation,
runtime hardware overrides, compiled profile generation, GUI normalization,
gem5 scalar options and offline characterization. A GUI accepting a value,
a generated assignment, a C++ stored field and a scheduler consumer are
different evidence stages. The audit preserves that distinction.

Important findings:

- FU limit zero means unlimited in our pooled scheduler. PR #2429 instead
  derives a finite capacity from the static graph. Preserve our semantics.
  Instruction-cap zero is neutral; nonzero remains explicitly rejected.
- Logical instruction runtime_cycles already reaches CycleCounts and
  instruction construction. A separately stored InstConfig runtime value
  is not the active latency authority.
- FU stages/cycles, datatype and PPA fields are not automatically scheduling,
  pipelining or calibrated physical-model controls. Native clock binding
  occurs after final overrides. Profile period and operational clock are
  distinct.
- Retained paths, defaults, cache options and memory-port declarations have
  real disagreements. In particular, raw ConfigPath handling differs from
  the checked adapter; an omitted DMA interrupt can default to 200; omitted
  PIO wiring can be accepted by a validator that substitutes LocalBus; the
  cluster-cache branch is dormant; RegisterBank's native private port is
  scalar. See the records for exact route, applicability and search limits.
- Current PR #2429 already has a direct cluster factory, a normalized reader,
  a bare-metal stdlib board and one generated profile module. Those are
  useful designs. Its generic objects and scheduling policy require explicit
  adaptation before replacing our qualified ABI.

## Read the results

| Artifact | Purpose |
| --- | --- |
| [Semantic contract](SEMANTIC_CONTRACT.md) | Behavior and boundaries the port must preserve |
| [Core consumers](CORE_CONSUMERS.md) | C++ Params, actual scheduling/memory/statistics consumers and storage gaps |
| [Legacy/configurator consumers](LEGACY_CONFIG_CONSUMERS.md) | 56 grouped records covering paths, defaults, GUI, generators and offline tools |
| [Current PR comparison](UPSTREAM_2429_COMPARISON.md) | 14 adopt/adapt/defer/reject decisions with exact pinned code references |
| [Observed-key coverage](CONFIGURATION_COVERAGE.json) | Every census pattern linked to evidence or explicitly unresolved/out of scope |
| [Next implementation slice](NEXT_SLICE.md) | Normalized GEMM model, direct factory and executable acceptance matrix |
| [Source/evidence index](SOURCES.json) | Pinned commits, snapshots, review metadata and external evidence hashes |
| [Audit validation](AUDIT_VALIDATION.json) | Reference/hash/accounting checks and protection guards |

The census reads 276 tracked YAML files in named SALAM/workbench scopes and
retains 56,186 mapping-key occurrences, grouped into 348 patterns. These
are inventory counts, not working-control or bug counts. Seventy-seven
patterns belong to an archived CI workflow and are explicitly outside the
configuration denominator. Legacy clusterN examples lack a demonstrated
current topology route. The raw census, every occurrence and file hashes
remain outside Git in the evidence folder below.

There are 122 duplicate mapping-key occurrences in seven legacy files.
All repeated value nodes serialize identically; no conflicting-value
behavior was demonstrated. Keep the diagnostic and migration issue without
inflating it into 122 separate failures.

## Pinned comparison and durable evidence

- Our baseline: f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb.
- [PR #2429](https://github.com/gem5/gem5/pull/2429) head:
  b4ff9f5aaa0e4d3df9bf503df2212a278eb59645.
- Official develop inspection base:
  1754a3b1789c6fd616124f89116b8258600e8b85.
- Full independent reference snapshots/manifests:
  /home/jslycord/projects/salam-track-a-references-20261105.
- Windows evidence and tools:
  D:/kb_local_chatGPT/salam/track-a-20261105.
- A Windows-readable copy of this document package is saved there under
  package/ after validation.

The captured GitHub response contains 132 inline review threads, including
10 marked unresolved. Their resolved/outdated labels are retained as
metadata, not evidence of correctness. The actual pinned implementation,
rather than an old discussion alone, determines each comparison finding.
Raw review bodies are preserved in the external evidence folder.

Source-only checks validate JSON, reference line bounds and hashes, census
accounting, documentation whitespace and the change scope. Protected source
HEAD/cleanliness, checkpoint tag and qualified base-binary SHA are guarded.
They do not establish new runtime correctness or whole-engine leak/drain
qualification.

## Next action

Implement a side-effect-free normalized GEMM model, then a direct factory
alongside the retained builder. Keep our current typed ABI for the first
comparison. Prove effective Params, clocks, finite/unlimited FU behavior and
independent numerical output before replacing generated Python. Generic
Params and native SCons generation follow as separately qualified changes.

Josh assigned Gemini B1 and B3. No status is inferred and no Gemini or
official-repository work is modified by this audit.
