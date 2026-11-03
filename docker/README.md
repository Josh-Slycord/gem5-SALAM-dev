# gem5-SALAM Pre-compiled Docker $\to$ WSL2 Distro

This directory formalizes an automated, reproducible pipeline to build and package **gem5-SALAM** (pinned to branch `codex/gem5-26-upgrade` at commit `9c83f862e4ce96f85680e255c12164106e79986d`) as a self-contained, pre-compiled native **WSL2** distribution.

---

## Why this Architecture?

1. **Pre-compiled Simulator & Accelerators:** Compiling gem5 from source takes 20–40 minutes and requires exact versions of GCC, Clang/LLVM 14, Python 3.10, and SCons. By compiling inside Docker, you build the binary once; subsequent WSL spin-ups take **under 15 seconds**.
2. **Total Isolation:** The resulting WSL virtual disk (`ext4.vhdx`) lives on secondary storage (`D:\wsl_instances\...`) instead of cluttering your `C:\` drive or mutating your existing WSL distributions (`Ubuntu-20.04`).
3. **Pre-configured Workbench GUI & Benchmarks:** All dependencies (`PySide6`, `numpy`, `networkx`, `pydot`, `pytest`, `libgl1`, `libegl1`, `libxkbcommon0`), cross-compilers (`arm-none-eabi`, `aarch64-linux-gnu`), ARM bootloaders, and benchmark bitcode are pre-installed and pre-compiled.
4. **Disposability:** If you ever experiment, break libraries, or want a fresh baseline, you can delete the distro with `wsl --unregister gem5-salam-prebuilt` and re-import from the exported tarball in seconds without re-compiling.

---

## File Contents

* **`Dockerfile`**: The multi-step build recipe based on `ubuntu:22.04` (Jammy):
  * Pins Clang 14 / LLVM 14 as default compiler and config generator (required for SALAM typed-pointer IR).
  * Installs Python 3.10, SCons, Protobuf, tcmalloc, HDF5, Boost, PNG.
  * Installs ARM baremetal toolchains (`gcc-arm-none-eabi`, `libstdc++-arm-none-eabi-newlib`, `libnewlib-arm-none-eabi`) and 64-bit cross-compiler (`gcc-aarch64-linux-gnu`).
  * Installs PySide6 Qt6 GUI runtime libraries for seamless WSLg desktop rendering.
  * Creates user `jslycord` with passwordless sudo and configures `/etc/wsl.conf` to boot directly into that user with systemd enabled.
  * Clones `Josh-Slycord/gem5-SALAM-dev` at `9c83f862e4ce96f85680e255c12164106e79986d`.
  * Pre-compiles ARM32 & ARM64 bootloaders (`system/arm/bootloader/*`).
  * Pre-compiles `build/ARM/gem5.opt` with SALAM accelerators enabled (`--with-salam LLVM_CONFIG=/usr/bin/llvm-config-14 PROTOCOL=CHI USE_KVM=0`).
  * Pre-compiles GEMM hardware bitcode (`clang -emit-llvm -I/usr/include/newlib`) and software ELF (`main.elf`).
  * Configures `workbench/workspace.json` and `.bashrc` aliases.
* **`build_gem5_wsl.ps1`**: The end-to-end PowerShell orchestrator:
  1. Builds the Docker image.
  2. Exports the filesystem to `D:\wsl_backups\gem5-salam-prebuilt.tar`.
  3. Registers it with WSL2 under `D:\wsl_instances\gem5-salam-prebuilt`.

---

## Quick Start

### 1. Requirements
* Docker Desktop running on Windows (with WSL2 backend enabled).
* Available disk space on `D:\` (~15–20 GB for Docker build cache, ~8–12 GB for the final rootfs tarball/WSL vhdx).

### 2. Run the Full Build & Import
Open PowerShell as your user and run:
```powershell
cd D:\kb_dev\gem5-salam-workbench\docker
.\build_gem5_wsl.ps1
```

### 3. Launching Your Instance
Once complete, open a terminal or run:
```powershell
wsl -d gem5-salam-prebuilt
```

You will land directly in `/home/jslycord/gem5-SALAM-dev` as `jslycord` with all paths configured:

* **Run GEMM simulation:** `run-gemm`
* **Launch Desktop GUI:** `workbench`
* **Inspect GUI headless:** `salam-inspect`
* **Direct gem5 binary:** `gem5 --build-info`

---

## Advanced Options

```powershell
# Re-import a new WSL instance from an already exported tarball (takes ~10 seconds):
.\build_gem5_wsl.ps1 -SkipBuild -SkipExport -DistroName "gem5-test-instance" -WslInstallDir "D:\wsl_instances\gem5-test"

# Only build the Docker image without exporting or importing to WSL:
.\build_gem5_wsl.ps1 -NoImport -SkipExport
```
