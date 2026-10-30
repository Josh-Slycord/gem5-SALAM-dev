# gem5-SALAM Research Workbench

gem5-SALAM models custom accelerators from LLVM IR inside the gem5 system simulator. This development fork connects its recovered hardware configurator to checked generation, isolated builds, real simulations and independently verified results.

**[Start with the workbench guide](workbench/README.md)** · [Scheduling results](workbench/docs/FU_SCHEDULING_RESULTS.md) · [Windows, Docker and VM options](workbench/docs/PACKAGING.md)

## What works now

- Live Qt configuration editing through generation, optional simulator rebuild and actual guest execution.
- Source/build capability checks and effective SimObject configuration witnesses.
- Scalar functional-unit admission with direct SALAM grant/deny/release traces and independent replay.
- Numerical reference checks, intentional wrong-output controls and source-bound run receipts.
- A portable source layout with machine settings, experiment outputs and build caches kept local.

The controlled 8 × 8 integer GEMM reproduces 1,054 accelerator cycles with unlimited multipliers, 4,126 with capacity two, and 8,206 with capacity one. Each case ran twice; an unused-unit control left timing unchanged. A separately compiled wrong result was rejected. These are simulated accelerator invocation measurements, with nonpipelined scalar occupancy semantics. See the [evidence scope and limitations](workbench/docs/FU_SCHEDULING_RESULTS.md).

## Get the source

```bash
git clone https://github.com/Josh-Slycord/gem5-SALAM-dev.git
cd gem5-SALAM-dev/workbench
```

The validated environment is Ubuntu 20.04 under WSL2, Python 3.8, LLVM/Clang 12, GCC 9 and ARM bare-metal tools. The current bootstrap binds an existing external, verified engine and its build-source metadata. Follow the [binding and GUI instructions](workbench/README.md); this source publication is not a clean-machine installer or prebuilt simulator release.

WSLg can display the Linux Qt GUI on the Windows desktop. A Windows shortcut can launch it without opening a WSL terminal. The [packaging guide](workbench/docs/PACKAGING.md) compares that approach with a pinned Docker environment, an exportable WSL appliance, a full VM and a future native Windows front end.

## CI scope

[CI scope](docs/CI.md) distinguishes source-only unit and generation checks from the local numerical simulations. The hosted job uses a pinned Ubuntu 20.04 container, read-only permissions and immutable action pins. Legacy whole-tree style/type debt and the separate simulator nightly are documented explicitly.

## Source, evidence and upstream

The repository contains source, required materialized build inputs, deterministic fixtures and authored findings. Raw simulation output, machine-specific configuration and binaries remain in ignored local storage. [Output and Git policy](workbench/docs/HYGIENE.md) explains those boundaries.

This fork incorporates official main history through a reviewed merge while preserving the validated scheduling code, newer bindings and Python 3 configuration support. [Integration decisions](workbench/docs/UPSTREAM_INTEGRATION.md) distinguish imported source and compile checks from full simulation acceptance. Official TeCSAR repositories remain reference sources.

Memory/control admission, pipelined functional units, nonzero per-instruction limits, broader topology/profile coverage and fresh-host packaging remain open. Historical setup and project resources are preserved in the [legacy simulator reference](docs/LEGACY_SIMULATOR_SETUP.md).
