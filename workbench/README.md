# SALAM Research Workbench

The workbench connects configuration editing to generated SALAM SimObjects/C++, simulator builds, staged benchmark compilation, real gem5 execution and independently checked results. It lives beside the simulator source in this fork; machine settings and run outputs remain local.

Start with the [functional-unit scheduling results](docs/FU_SCHEDULING_RESULTS.md), [packaging options](docs/PACKAGING.md), and [output and Git policy](docs/HYGIENE.md).

## Current supported environment

The validated local toolchain is Ubuntu 20.04 under WSL2, Python 3.8, LLVM/Clang 12, GCC 9 and ARM bare-metal tools. GUI acceptance used PySide6 6.2.4. The exact tested Python GUI packages are in `requirements-gui-validated.txt`. A current generic gem5 image is not interchangeable with this older SALAM toolchain.

This publication supports binding an **existing verified external runtime engine**. It does not yet promise a clean-machine installer or redistribute a compiled simulator. Keep that engine outside this checkout: generated staging directories must not be inside their source engine, and source/build receipts must not silently change when documentation or GUI files change.

## Use the integrated desktop Workbench

Open **SALAM Workbench** from the Windows desktop or Start menu shortcut. The
window combines the installed benchmark library, configuration editor, run
monitor, recorded results, SALAM metrics and system topology. The library
inspects actual source layouts; missing inputs and unsupported layouts remain
visible with their reasons.

**Configured simulation** applies the visible system, accelerator and hardware
settings. The existing pipeline stages the configuration, regenerates guest and
topology code, rebuilds an isolated simulator variant when required, and checks
the resulting simulation. **Verified reference workload** runs the reviewed
fixed GEMM, BFS, Needleman–Wunsch, FFT or stencil3d workload against its recorded
reference engine. Editor settings do not apply in reference mode.

Save and reload source-bound JSON presets from the configuration toolbar. Presets
retain system settings, accelerator connections, functional-unit limits,
instruction timing and hardware-profile edits. A changed source configuration
is rejected rather than silently accepting a stale preset.

The results view keeps recorded status separate from the current evidence
assessment. It exposes direct SALAM accelerator metrics, gem5 system statistics,
validation checks, bounded text/log previews and source provenance. Metric
filters and side-by-side comparisons preserve units and measurement scope.
Missing power, energy or area data remains unavailable; model parameters do not
become measurements of physical hardware.

**SALAM process** is an interactive conceptual diagram of the configured
workflow, with selectable stages and related hash-verified evidence from
the selected run. It identifies fixed reference and historical workflows
as separate paths; related filenames alone do not prove a stage passed.

**System topology** displays each run's original `config.dot.svg` with pan,
zoom and fit controls. The graph describes instantiated gem5 SimObjects and port
connections, not runtime activity. Original DOT/PDF files remain available, and
the viewer rechecks their recorded hashes. Display sanitization leaves original
evidence bytes unchanged.

One simulation job runs at a time. The request is locked while its backend and
raw-result verification run. Keep the window open until the job finishes;
force cancellation of simulator/build process trees is not implemented. Prior
attempts and failed outputs remain available in ignored local evidence. History
discovery and artifact previews are bounded so large research archives do not
freeze the interface. Unavailable or changed evidence remains explicit.

To reproduce the production-window acceptance flow with real simulations:

```bash
python3.8 -B scripts/verify_workbench_window.py \
  --cases configured:gemm,reference:bfs,reference:fft,reference:nw,reference:stencil3d,reference:gemm
```

This exercises the actual Qt selectors and Run button, edits GEMM memory/timing
and multiplier capacity, rechecks raw results, and saves metric tables and
topology renders. It uses Qt offscreen rendering; a visible Windows launch is a
separate check. Source-only hosted CI does not run these simulations.

## Bind an existing installation

The bootstrap validates existing build/source receipts and copies their exact files into ignored local evidence. It preserves the original source workspace and creates a local `workspace.json`. It refuses an engine inside this repository's workbench tree. Run its help for the explicit inputs:

```bash
cd /path/to/gem5-SALAM-dev/workbench
python3.8 -B -m salam_workbench.bootstrap_existing \
  --source-workspace /path/to/existing-workbench/workspace.json
```

Then install the portable adapter into that independent runtime engine, saving its previous GUI source:

```bash
python3.8 -B -m salam_workbench.gui_hook \
  --engine /absolute/path/to/external-configured-engine \
  --evidence-dir "$PWD/evidence/gui-hook-install-1"
```

The historical fixed GEMM/variant/regression commands and their original engine remain available when their required historical receipts are supplied. The selected configuration engine can be a separate FU-capable build. Bootstrap binds existing provenance; it does not manufacture a successful build receipt.

## Open the GUI from Windows

Once bootstrapped, run the PowerShell launcher from Windows:

```powershell
.\workbench.ps1 -Action configurator
```

A Windows shortcut can invoke that same command. Unsigned scripts on a WSL UNC share may be blocked by PowerShell execution policy. A shortcut can instead invoke `wsl.exe` directly with the selected distro, Linux checkout directory and `-m salam_workbench.configurator_app`; it does not need a machine-wide policy change. WSLg displays the Linux Qt window on the Windows desktop. `-Inspect` checks the selected engine, build receipt and GUI hook without launching a simulation. Both drive-letter and `\\wsl.localhost\<distribution>\...` checkout paths are supported by the launcher.

The desktop window embeds the existing configurator from the external engine and selects this workbench package through `SALAM_WORKBENCH_ROOT`. Its apply action stages the request, regenerates hardware and builds an isolated variant when compiled defaults change, runs the benchmark, then checks the effective configuration and direct SALAM output. Failed or unsupported requests remain failures. An old engine without the matching capability/build evidence cannot silently claim functional-unit scheduling support.

## Check and reproduce

```bash
python3.8 -B -m salam_workbench.checks --tier fast
python3.8 -B -m salam_workbench.checks --tier config
QT_QPA_PLATFORM=offscreen python3.8 -B -m salam_workbench.checks --tier gui
```

Each invocation creates a unique ignored evidence directory with source snapshots and check receipts. Simulation is explicit; see [FU results](docs/FU_SCHEDULING_RESULTS.md) for the nine-run controlled experiment command. The GUI acceptance helper is `scripts/verify_gui_apply.py`.

Use the workbench's `hardware_codegen` / configurator entry points for generation. They stage the recovered generators with validated Float/profile/default-getter repairs, execute them, and verify their output. Direct invocation of historical root generator scripts bypasses those repairs and is not the supported generation path.

## Coverage boundaries

Prior checkpoints cover fixed GEMM, BFS, Needleman–Wunsch, FFT and stencil3d datasets with independent checks; the new controlled scheduling study covers scalar integer multiplication in GEMM. The GUI can apply supported configuration groups, but every possible topology, hardware profile and benchmark combination has not been validated. Memory/control resource admission, pipelined FUs, nonzero per-instruction caps and a clean-host appliance remain open work.

The original WSL engines and recovered research archives are preserved. Official TeCSAR repositories are read-only reference sources; this fork is the publication and integration target.
