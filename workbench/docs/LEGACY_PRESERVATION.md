# Historical standalone Workbench preservation

Preserved on **5 November 2026**. This records historical source and reasoning;
the old status tables, pass counts and plans do not describe current gem5 26
qualification.

## Where the history lives

The [private standalone archive](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/preservation/standalone-workbench-20261105)
retains the complete standalone Workbench Git history at source commit
**62bcd16bc90d5b6dac993c4a5c7ff559a2c771df**, followed by preservation metadata
commit **961182113f5b2cec837b3b0df36e606c00ae01dc**.
Access requires permission to that private repository.

The archive is a separate branch. It was not merged into the simulator and did
not change private main. The original standalone checkout remains unchanged.

Its [preservation index](https://github.com/Josh-Slycord/gem5-SALAM-dev-private/tree/961182113f5b2cec837b3b0df36e606c00ae01dc/.preservation/standalone-20261105)
contains the 154-file source/configuration/document manifest, comparison
inventory, restore result, filename-only credential-path check and integration
recommendations. Every curated snapshot payload matches its root file at the
preserved source commit, so duplicate source copies were not published.

The local all-ref bundle has SHA-256
**875069ef4a2bdf831d811aeaf473481a7243e68b88a626045d04736580a2c52f**.
An independent bare restore passed full object verification and reproduced all
saved refs. The remote branch was fetched back and its published head verified.

## What was missing from the integrated tree

Comparison was against qualified checkpoint
**85045fe8b7695b8d2c5bb618553ecd1cff7c24d8**. There were **32 Markdown documents
and seven JSON/CSV/patch artifacts** absent at the same integrated relative
path. Missing paths do not prove their ideas are absent or unimplemented.

Two other absent paths were standalone Git-ignore and CI configuration, whose
responsibilities moved to repository-root policies in the integrated project.
No additional missing implementation path was established by this comparison.
Most module differences represent older versions; hashes alone do not justify
replacing newer implementations.

## Useful threads to reconnect

| Historical material | Current use |
| --- | --- |
| Statistics stash review and disposition | Preserve the exact 26-file reconciliation and old baseline identities. Compare selected ideas against current source; never apply the complete old stash automatically. |
| Output, memory-event, observability-contract and model-data audits | Feed metric-semantics tests: units, scope, exact denominators, availability, and characterized-versus-measured values. New native statistics must preserve these distinctions. |
| M4 workload audit and additional-benchmark documents | Retain unsupported layouts and validation scope when expanding beyond the currently qualified benchmark families. Old pass markers do not establish current coverage. |
| Unified project plan, backlog and source map | Preserve project rationale and recovered-source mapping. Reconcile open tasks into the current plan rather than reviving old statuses or tool owners. |
| M3 GEMM observability and statistics-integration records | Retain earlier accepted source/evidence identities. They do not qualify a later gem5 26 engine, native-statistics path or physical power model. |

The exact source documents and path inventory are accessible through the
private archive. Current upstream proof obligations remain in
[UPSTREAM_READINESS.md](UPSTREAM_READINESS.md).

## Preservation boundaries

Current ignored raw evidence, rebuildable binaries and bulk outputs were not
duplicated by this source-preservation package. Some old relative evidence
links still point to the unchanged original standalone tree. The private Git
history also retains older tracked runs and machine-binding versions.

A filename-only check covered 541 historical object-path entries and found no
credential-like path names. Credential values were not inspected; this is not
a claim of a content credential audit. Restricted contract code and unrelated
personal archives were outside this preservation task.
