# SALAM Research Workbench

The workbench connects configuration editing to generated SALAM SimObjects/C++, simulator builds, staged benchmark compilation, real gem5 execution and independently checked results. It lives beside the simulator source in this fork; machine settings and run outputs remain local.

Start with the [functional-unit scheduling results](docs/FU_SCHEDULING_RESULTS.md), [packaging options](docs/PACKAGING.md), and [output and Git policy](docs/HYGIENE.md).

## Current supported environment

The validated local toolchain is Ubuntu 20.04 under WSL2, Python 3.8, LLVM/Clang 12, GCC 9 and ARM bare-metal tools. GUI acceptance used PySide6 6.2.4. The exact tested Python GUI packages are in `requirements-gui-validated.txt`. A current generic gem5 image is not interchangeable with this older SALAM toolchain.

This publication supports binding an **existing verified external runtime engine**. It does not yet promise a clean-machine installer or redistribute a compiled simulator. Keep that engine outside this checkout: generated staging directories must not be inside their source engine, and source/build receipts must not silently change when documentation or GUI files change.

## Bind an existing installation

The bootstrap validates existing build/source receipts and copies their exact files into ignored local evidence. It preserves the original source workspace and creates a local `workspace.json`. It refuses an engine inside this repository's workbench tree. Run its help for the explicit inputs:

```bash
cd /path/to/gem5-SALAM-dev/workbench
python3.8 -B -m salam_workbench.bootstrap_existing \
+  --source-workspace /path/to/existing-workbench/workspace.json
```

Then install the portable adapter into that independent runtime engine, saving its previous GUI source:

```bash
python3.8 -B -m salam_workbench.gui_hook \
+  --engine /absolute/path/to/external-configured-engine \
+  --evidence-dir "$PWD/evidence/gui-hook-install-1"
```

The historical fixed GEMM/variant/regression commands and their original engine remain available when their required historical receipts are supplied. The selected configuration engine can be a separate FU-capable build. Bootstrap binds existing provenance; it does not manufacture a successful build receipt.

## Open the GUI from Windows

Once bootstrapped, run the PowerShell launcher from Windows:

```powershell
.\workbench.ps1 -Action configurator
```

A Windows shortcut can invoke that same command. Unsigned scripts on a WSL UNC share may be blocked by PowerShell execution policy. A shortcut can instead invoke `wsl.exe` directly with the selected distro, Linux checkout directory and `-m salam_workbench.configurator_app`; it does not need a machine-wide policy change. WSLg displays the Linux Qt window on the Windows desktop. `-Inspect` checks the selected engine, build receipt and GUI hook without launching a simulation. Both drive-letter and `\\wsl.localhost\<distribution>\...` checkout paths are supported by the launcher.

The GUI loads the existing configurator from the external engine and selects this workbench package through `SALAM_WORKBENCH_ROOT`. Its apply action stages the request, regenerates hardware and builds an isolated variant when compiled defaults change, runs the benchmark, then checks the effective configuration and direct SALAM output. Failed or unsupported requests remain failures. An old engine without the matching capability/build evidence cannot silently claim functional-unit scheduling support.

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
