# Upstream integration and retained fork behavior

This integration merges official `TeCSAR-UNCC/gem5-SALAM` main at `6910a2efd2f8cc0accb26d0be45f579dc6d5d826` into Josh's fork. The compared fork main was `42539ecca54ff0fed455a7afe0bda0603554e360`; their merge base was `b5bc950e99b77a935ea80b4664eb6cdf4327add0`. Before integration, Git reported 346 commits ahead and 350 behind.

Many historical patches are equivalent under different commit IDs. The integration retains the existing histories and uses a normal merge with reviewed file resolutions. It does not rewrite history, force-push, or use an `ours` merge strategy to hide missing work. The official repository is a fetch-only reference; its local push URL is disabled.

## Resolution policy

The actual merge index had 653 conflict paths: 109 three-way content conflicts, 332 add/add conflicts, 160 fork-only paths, 43 obsolete base-only paths, two fork/base paths, two upstream/base paths, and five upstream-only LeNet paths. Some 169 paths in the preliminary comparison differed only in line endings. The larger actual conflict count also includes rename/delete cases and newly published scheduler paths.

| Area | Resolution and reason |
| --- | --- |
| Scalar scheduler and materialized hardware models | Keep validated fork admission/lease code, generated Float parameters, capability declaration and source mappings. |
| Python integration | Keep Python 3 `configparser`, `types.ModuleType`, safe configuration loading, FU registries and configurable profiles. Several upstream versions would restore older behavior. |
| C++ compatibility and diagnostics | Keep the fork's includes, null guards, diagnostics, GUI publisher and `owner->debug()` spelling. |
| pybind11 | Keep the coherent newer fork library from the GCC/Python compatibility update, including its docs/tests. Do not mix older upstream stubs or test files into it. |
| `SConstruct` | Keep the validated GCC/BFD defaults. Optional upstream lld/mold switches remain deferred until separately built and validated. |
| Bare-metal runtime | Retain original `baremetal/` inputs, including `common/fake.iso`, syscalls and Interrupt/Simple boot files. Automatic rename matching to unrelated LeNet files does not make them interchangeable. |
| Existing validation benchmarks | Preserve root-relative IR resolution, the validated 8 × 8 integer GEMM, BFS `extern` declaration, DMA initialization and required includes. |
| Upstream benchmark additions | Retain LeNet design layouts and MobileNet profile/configuration additions. These additions are available source; they are not newly claimed as passing simulation benchmarks. |
| Upstream tools | Retain relocated configurator, hardware-generator and CACTI helper sources. The checked workbench adapter remains the supported generator path. |
| Obsolete renamed paths | Preserve stage blobs and any merge-only worktree files in local evidence before clearing obsolete index entries. Keep the fork's legacy successors. |

The source-only compiled-input fingerprint after resolution was identical to the measured scheduler engine: `3f99894985051727fef026ffc3a2cfed2e47ddd08e359e3e5294142e71ffc66f`. This comparison covers `src`, `ext`, `build_opts`, `site_scons` and root SCons entry points. It permits the existing verified binary to be used for the same build inputs; it does not imply every imported benchmark or legacy helper has been executed.

Raw conflict snapshots, exact per-path decisions and archived generated reports remain local. See [source/output policy](HYGIENE.md) and [scheduling evidence scope](FU_SCHEDULING_RESULTS.md).

## Benchmark checks during integration

MobileNet width selectors now retain the original 0.35 default and accept explicit 0.75 and 1 profiles. ARM preprocessor checks passed all three widths and rejected two simultaneous selectors. The mergesort `CHECK` compares every result with its sorted reference and signals guest failure on a mismatch. ARM syntax compilation passed; an extracted exact-check host harness exercised both passing and intentionally failing arrays. These are compile/predicate checks, not full gem5 simulation results for those benchmarks.

## Open work

Validate the imported LeNet/MobileNet designs with their own numerical oracles before adding passing result claims. Review historical duplicate generator entry points and consolidate them through the checked workbench API. Validate optional linker selections and newer Linux toolchains as separate builds. Keep saved branches until their unique research threads have been deliberately integrated or archived.
