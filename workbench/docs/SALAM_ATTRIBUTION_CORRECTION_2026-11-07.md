# SALAM attribution correction — 7 November 2026

This record adds missing source-specific credit to the retained reviewer
phases without rewriting published commits or changing simulator source.
It expands the earlier four-source audit to **fourteen verified original
commits by Akanksha Chaudhari**. Credit applies to the named implementation
regions; it does not transfer ownership of whole files or the SALAM framework.

The inspected downstream code is pinned to
`e33b9a0d4b2f5a22b89c4bf1d4ed4b34f5db3f9d`. The earlier upgrade checkpoint is
`f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb`. References to later lifecycle
repairs describe the inspected downstream line; they do not claim the older
upgrade branch already contains those later code changes.

## Retained import records

Phase 1 is retained as `45474cb28f785ea5c1a54e6ec09d8cebc38450c3` and
`6721f18e2bdd1c44c7a9c0b19a59b7f265ef7b24`. Phase 2 is retained as
`6e9645aca843a5222100fa33ab86e81367850e84` and
`4704eeca5884b39f5e32af4b8f142ff814f57c80`. The raw/revised pairs have the
same simulator implementation; their tree differences are confined to the
maintainer metadata. They are alternate import histories, not two separate
original contributions. Both histories remain reachable from the inspected
fork. The original upstream source commits themselves are not its ancestors.

The phase records identify Joshua as author/committer but omit individual
source-author and source-SHA credit. Existing documentation already names
the upstream PR author generally. This correction supplies the patch-specific
credit; it does not claim that no acknowledgement existed elsewhere.

## Verified original sources

All fourteen source commits record **Akanksha Chaudhari** as author and
committer. The table links immutable originals in the upstream-development
repository. P1 anchors refer to `6721f18e...`; P2 anchors refer to
`6e9645ac...` (the code is unchanged in its revised record).

| Original source | Retained phase and implementation | Attribution boundary |
| --- | --- | --- |
| [5c1077e5: FRem truncation-toward-zero remainder semantics](https://github.com/akanksha-sc/gem5/commit/5c1077e5c606625475c413fb26a110988fc2589c) | P1; `LLVMRead/src/instruction.cc:1481,1495` | Float/double std::fmod substitutions; adjacent memcpy changes are separate. Later floatingRemainder/float_bits refactoring preserves this semantic fix. |
| [f84e0a19: RegPort request lifetime and retry handling](https://github.com/akanksha-sc/gem5/commit/f84e0a19dff1a35193d2749d2ad2cc74c6e26730) | P1; `comm_interface.cc:125,137,692,733,749,777; comm_interface.hh:145` | Retry queue, send-result handling, pointer clearing and remainingAfter guards adapted to the retained ABI. Later packet-ownership, send-attempt and drain changes remain separate. |
| [cb334503: Scratchpad response-head and retry ordering](https://github.com/akanksha-sc/gem5/commit/cb334503c1330066ac3a48538e2681231d9247d5) | P1; `scratchpad_memory.cc:418,436; scratchpad_memory.hh` | Distinctive scheduleNextResponse and retry-reset scheduling hunks. Later shared response-queue/reentrancy changes remain separate. |
| [773419b2: Static execution-graph reference release](https://github.com/akanksha-sc/gem5/commit/773419b2dde83e8d5e611fcd7ee75f99253afdbf) | P1; `LLVMRead/src/{basic_block,function,instruction,value}.{cc,hh}; llvm_interface.cc:867` | releaseGraphEdges APIs/method bodies and finalization calls, adapted field/layout names. This credits the static cycle-release implementation, not all lifetime, ownership or later drain work. |
| [3cddf5c6: DMA write-side functional bypass](https://github.com/akanksha-sc/gem5/commit/3cddf5c6aec651f8353a4f487683048f59d622fa) | P1; `dma_write_fifo.cc:126` | DmaWriteFifo::resumeEmptyFunctional body, chunk buffering, comments and debug string. |
| [432f50d8: Predicate-specific ICmp operands](https://github.com/akanksha-sc/gem5/commit/432f50d8ee5633e5eab50572a9cd55f17a169b78) | P1; `LLVMRead/src/instruction.cc:2917,2944` | Signed-i1 rejection and signed/unsigned operand strategy; legacy formatting expanded. |
| [a9bfa096: Removal of uninitialized opcode identifiers](https://github.com/akanksha-sc/gem5/commit/a9bfa096701fc5eb435aefce2fd25c8ab041dc4d) | P1; `HWModeling/src/opcodes.cc:5; HWModeling/src/opcodes.hh:14` | Ten identifiers and ten associated usage entries removed; verified deletion hunks. |
| [6de0a5d7: Unsupported LLVM opcode diagnostics](https://github.com/akanksha-sc/gem5/commit/6de0a5d7c358b3c5d5a98c9aaefb63ad7d682b95) | P1; `llvm_interface.cc:1243` | Fatal diagnostic with rendered IR and raw_ostream include. The preexisting constrained-FU guard is separate. |
| [c81a0c9e: LLVM value/register type validation](https://github.com/akanksha-sc/gem5/commit/c81a0c9ede3acbede1b47da70c6f4fae8ac9354f) | P1; `LLVMRead/src/value.cc:67,95` | Allowed-width switch, intentional void/label handling and diagnostics; formatting adapted. |
| [0d502bda: Unsupported LLVM call-target rejection](https://github.com/akanksha-sc/gem5/commit/0d502bdad85c26506eb647cc361643cbc19b1494) | P1; `LLVMRead/src/instruction.cc:3416` | Call::initialize rejects indirect/unresolved and declaration-only call targets. |
| [8bcc3deb: Function-declaration skip in loop analysis](https://github.com/akanksha-sc/gem5/commit/8bcc3deb45a3b11bf45bf3503cd34fa7a13dea2d) | P1; `llvm_interface.cc:601` | Four-line declaration-skip hunk and its explanatory comment. |
| [032d6e1a: Bounded register reads and entry-PHI handling](https://github.com/akanksha-sc/gem5/commit/032d6e1a92f7545dd7f6aa84c0f3a0a4feb825e7) | P1; `LLVMRead/src/value.cc:239,251; llvm_interface.cc:33` | readTargetBytes helper/bounded reads and PHI snapshot/queue blocks. Other scalar, call and memory-dependency changes in the larger original commit are not established as imported. |
| [c2010d3b: Iterative basic-block traversal and CFG-cycle rejection](https://github.com/akanksha-sc/gem5/commit/c2010d3b96f033596ef9b4d0c089f438301d0c8f) | P1; `llvm_interface.cc:33` | ActiveFunction::scheduleBB traversal, visited-block guard, diagnostic and comments. Other validation/fixtures in the larger original are not established as imported. |
| [932cb66b: Native execution-statistics groups and counting](https://github.com/akanksha-sc/gem5/commit/932cb66bba9bd771683af36800ad176a15cad234) | P2; `llvm_interface.cc:26,57,82,92,98,106,112,131` | ExecStats constructor/descriptions and regStats match directly; count/category/occupancy methods are adapted. Upstream cumulative totals updates and SALAMIssue debug calls are omitted. Later native-clock adapters/reset reconciliation are separate. |

Paths in the table are relative to `src/hwacc/`. Upstream uses `src/salam/`;
its LLVMRead paths also omit the retained fork's extra `src/` component.
The two upstream `HWModeling/opcodes` files likewise map into the retained
`HWModeling/src/` directory; the structured map records those exact exceptions.
The [structured map](provenance/SALAM_SOURCE_ORIGINS.json) records full SHAs,
source dates/files, full commit-show digests, both import records and the
review method. The digests include fuller commit metadata and diff; they are
not patch-only hashes. Exact capture arguments and context are recorded.
Public Git metadata and actual added/deleted code were inspected; matching
subjects, API names or similar design goals alone were not sufficient.

## Later downstream work stays separately attributable

At the inspected `e33b9a0d...` code:

- `FRem::compute()` reaches `gem5::salam::floatingRemainder()`; the helper
  in `float_bits.hh` uses `std::fmod`. That retains the credited remainder
  semantic fix through a later bit-access refactor, without attributing the
  whole helper implementation to the original remainder patch.
- RegPort and scratchpad handling carry subsequent packet-ownership,
  reentrancy and queue work. The original retry/lifetime/order fixes above
  are credited separately from those later adaptations.
- Static `releaseGraphEdges()` contributions precede the later drain work.
  The `e33b9a0d...` drain/restart fixtures, logical-request publication fixes,
  request-attempt statistics and delta-event drain handling are subsequent
  work, not a claim to have originally authored the credited graph release.
- Source integration at `bcb4fad6...` and subsequent Track A/B qualification
  added independent compatibility, clock/reset, numerical and configuration
  checks. Test success does not establish original intellectual authorship.

## Phase inventory and open origins

| Retained phase | Revised record | Status |
| --- | --- | --- |
| 1 | `6721f18e2bdd1c44c7a9c0b19a59b7f265ef7b24` | 13 scoped upstream patches verified; adjacent changes not exhaustively attributed |
| 2 | `4704eeca5884b39f5e32af4b8f142ff814f57c80` | native statistics source verified; clock-domain provenance unresolved |
| 3 | `564dcad1fdd95e4fcd6fa48de998f886b910ecd3` | constructor implementations differ; exact source derivation unresolved |
| 4 | `6c9e5af23d23982a0bd1f801a917c53c79685e89` | screened only; exact source attribution remains under review |
| 5 | `bcbcc33fd10f5de462efdc58f8ab5269b83ac416` | screened only; exact source attribution remains under review |
| 6 | `b9c798893d53e8565943aed6678a151434d4a5f1` | screened only; exact source attribution remains under review |

The pinned upstream review snapshot is
`b4ff9f5aaa0e4d3df9bf503df2212a278eb59645`: 113 total commits / 102 non-merge
commits screened. Direct distinctive-hunk review supports the fourteen
rows above. A lightweight signed-line screen elsewhere is only a source lead.
The live PR snapshot on 7 November has 132 commits at
`70e05ff81c13951d90a22c332929753be8b7b3ca`; it was open and unmerged when
checked. Completeness against that newer head is not established.

Unresolved leads remain explicit in the structured map:

- `6185341e...` clock domains: generic clock API overlap is insufficient.
- `06c204df...` constructor consolidation: the original uses fixed generic
  SimObjects, while the retained implementation keeps per-entry types with
  templated bases. Similar goals do not establish identical code derivation.
- `c981b557...` cache Param descriptions and the phase-four header/configurator
  candidates need complete hunk review. Phases four through six are not
  certified as either wholly local or wholesale imports.

## Correction and verification boundary

The forward remedy is the visible README acknowledgement, root credits,
this correction and the structured origin map. Older commits, published
history, existing notices, `LICENSE` and `COPYING` are preserved. No original
Git author fields are retroactively changed, no fake coauthor/signoff is
added, and no contributor's institutional copyright holder is guessed.

This correction is documentation/attribution only. Simulator source and
compiled-input fingerprints remain unchanged; the existing numerical
qualification is retained as dated evidence rather than presented as a new
runtime test. Repository-wide licensing, copyright clearance, complete
historical authorship and the unresolved source leads above remain open.
