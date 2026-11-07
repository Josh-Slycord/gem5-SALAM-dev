# SALAM contributors and source credit

This development fork builds on the [gem5 project](https://github.com/gem5/gem5),
the [TeCSAR-UNCC gem5-SALAM framework](https://github.com/TeCSAR-UNCC/gem5-SALAM)
and their contributors. Existing source notices, `LICENSE`, `COPYING` and
original Git histories remain authoritative records; this page is not an
exhaustive contributor list or copyright determination.

## Mainline-integration contributions

**Akanksha Chaudhari (`akanksha-sc`) is the recorded original author of
fourteen upstream-development commits whose implementations are adapted,
in whole or in identified part, by the retained reviewer-integration series.**
These include floating remainder semantics, RegPort lifetimes and retries,
scratchpad response ordering, static graph-reference release, DMA functional
write bypass, LLVM validation and native execution-statistics implementation.
The [source-by-source correction](workbench/docs/SALAM_ATTRIBUTION_CORRECTION_2026-11-07.md)
and [machine-readable origin map](workbench/docs/provenance/SALAM_SOURCE_ORIGINS.json)
give full source SHAs, retained import records, exact scope and partial-port
boundaries. These are source contributions, not merely a general thank-you.

The work is associated with [gem5 PR #2429](https://github.com/gem5/gem5/pull/2429).
A commit URL in the gem5 object store does not establish upstream acceptance.
The related [authorship/integration discussion](https://github.com/Josh-Slycord/gem5-SALAM-dev/pull/3#issuecomment-6697279516)
includes Matt Sinclair, Akanksha Chaudhari and Bobby R. Bruce; their individual
source and review roles must not be inferred to be identical. Thank you to
Matt for raising the attribution gap. The gem5 release history imported by
merge retains its original authors, including Bobby R. Bruce's recorded
v26 release commit.

## Fork adaptations and subsequent work

Joshua Slycord's fork records integration into the retained `src/hwacc` ABI,
workbench/configuration work, validation, and subsequent repairs. Those
activities are distinct from authorship of the upstream implementations
above. Later bit-access helpers, queue/reentrancy repairs, clock adapters,
independent numerical checks and lifecycle/drain tests have their own
commits and boundaries in the correction record. These statements do not
assign Joshua sole authorship of every adjacent line or certify unresolved
source origins.

This forward correction leaves older published author fields and commit IDs
intact while supplying missing source-specific credit visibly. It does not
create a joint-authorship endorsement, contributor signoff, license clearance
or a claim that the complete mainline SALAM port has been imported.

For future integrations, follow the provenance requirements in `AGENTS.md`:
preserve original author metadata for unchanged imported patches, record
source author/full SHA and adaptation scope for altered patches, and resolve
uncertain origins rather than assigning them to the integrator by default.
