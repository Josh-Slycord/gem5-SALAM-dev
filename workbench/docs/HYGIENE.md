# Source, generated files, and run evidence

The repository publishes code, build inputs, small deterministic fixtures, and authored documentation. It does not publish a growing collection of local simulation runs.

## Tracked source

Keep simulator and workbench source, test code, configuration examples, benchmark inputs, and the materialized C++ instruction and functional-unit definitions required by SCons. Some of those build inputs live in a directory named generated; the build consumes them directly, so the directory name alone is not a reason to untrack them. Keep referenced LLVM IR fixtures, authored legacy config.ini inputs, and SystemC golden test logs for the same reason.

A new generated file belongs in Git only when a clean checkout needs it as a build input or a small, reviewed fixture and its regeneration path is documented.

## Local output

Keep simulation workspaces, raw direct SALAM JSON, gem5 statistics and config dumps, full traces, terminal logs, build binaries, release packages, virtual environments, caches, and machine-specific workspace.json outside the tracked source set. The workbench/evidence, workbench/runs, workbench/results, and workbench/releases trees are ignored. A checked result summary can report measured values and validation scope without committing every run artifact.

The legacy test runner writes TEST_RESULTS.md and test_results.json at repository root; a separate tests/test_results.json and two GUI log files were also previously tracked. They are now ignored and the old copies were preserved in a hash-verified archive before untracking. The backup script no longer stages the root reports.

Do not add broad ignore rules for *.log, *.ll, config.ini, or the entire generated source tree. They would obscure required golden logs, IR fixtures, authored configurations, and build source.

## Reproducible evidence

Each run should produce a durable local receipt with the request, source and toolchain identities, effective simulator configuration, numerical oracle result, direct SALAM output, and integrity hashes. Preserve failed runs and negative controls with their actual status. Public methods and result summaries should say which claims the saved evidence supports; raw output remains in local storage or an explicitly managed research archive.

Before publishing a source change, review the staged names and the untracked names. Confirm that no raw run directory, binary, machine-specific manifest, or private recovery file is included. Regenerate and test from the intended source revision, then record the corresponding local evidence identifier in the authored summary. Never use a broad cleanup command to make the tree look clean; archive unexpected output first.
