# SALAM Execution Trace Visualizer & WSL2 Containerization

This document records the design, implementation, and integration of the **cycle-accurate execution trace visualizer** and the **automated Docker-to-WSL2 pre-built distribution pipeline** for the gem5-SALAM research workbench (gem5 v26.0.0.0 upgrade).

---

## 1. Background & Motivation

While the existing Workbench GUI (`salam_workbench`) provides system configuration editing, static metric tables, and Graphviz SimObject topology layouts, it lacked a dynamic, cycle-by-cycle visual representation of how hardware accelerators execute in real time. 

Additionally, building gem5-SALAM from source requires precise versions of Clang/LLVM 14, Python 3.10, and cross-compilers, taking 20–40 minutes per compile. To provide a reproducible, turnkey research environment, this work establishes:
1. An automated Dockerfile that packages and pre-compiles the entire simulation engine, bootloaders, and benchmark suites into an isolated WSL2 distribution.
2. A lightweight, standalone microarchitectural execution visualizer that transforms raw cycle-by-cycle event traces into an interactive timeline dashboard.

---

## 2. Docker & WSL2 Appliance Architecture

The container recipe in `docker/` builds a clean, disposable **Ubuntu 22.04 LTS (Jammy)** environment:
* **LLVM 14 & Typed-Pointer IR:** Configured as the system default (`clang-14`, `llvm-14`, `llvm-config-14`), fulfilling gem5 26's strict SALAM SCons requirements.
* **Baremetal & 64-bit Cross-Compilers:** Installs `gcc-arm-none-eabi`, `libnewlib-arm-none-eabi`, and `gcc-aarch64-linux-gnu`.
* **Automated Pre-compilation:**
  * Compiles ARM32 (`boot.arm`) and ARM64 (`boot.arm64`) bootloaders.
  * Compiles `build/ARM/gem5.opt` with `--with-salam LLVM_CONFIG=/usr/bin/llvm-config-14 PROTOCOL=CHI USE_KVM=0`.
  * Pre-compiles GEMM benchmark hardware bitcode (`clang -emit-llvm -I/usr/include/newlib`) and software binary (`main.elf`).
* **WSL2 Integration:** Configures `/etc/wsl.conf` with default user `jslycord` and systemd enabled. The rootfs is exported to secondary storage (`D:\wsl_instances\gem5-salam-prebuilt\ext4.vhdx`), preserving host `C:\` capacity.

---

## 3. Microarchitectural Trace Visualizer

### 3.1 Event Stream Contracts
During execution, SALAM's `Observability` subsystem emits cycle-by-cycle JSON records to `observability/fu-scheduling-<accelerator>.invocation-1.json`:
* `grant`: `{"event": "grant", "cycle": C, "tick": T, "uid": UID, "opcode": OP, "fu_id": FU, "lease_id": L}`
* `release`: `{"event": "release", "cycle": C, "tick": T, "uid": UID, "opcode": OP, "fu_id": FU, "lease_id": L}`

### 3.2 Span Extraction & Multi-Lane Stacking
The generator (`workbench/visualizer/export_salam_visualizer.py`):
1. **Pairs Grants and Releases:** Matches each `lease_id` into a distinct execution span with exact cycle duration, tick latency, and LLVM opcode identification.
2. **Sub-Lane Allocation:** For units with simultaneous parallel execution (e.g. GEMM's 8 concurrent integer multipliers), assigns virtual sub-lanes so concurrent operations render in parallel rows without visual overlap.
3. **Concurrency Area Curve:** Accumulates per-cycle active functional unit counts to plot an aligned concurrency curve below the Gantt matrix.

### 3.3 Interactive Dashboard Capabilities
* **Time Scrubber & Playback:** Allows playing through cycles with variable speed (1x, 2x, 5x, 10x) or scrubbing manually.
* **Stable Layout (Anti-Jitter):** Fixed-height cards and scroll containers prevent DOM layout jumping as active instruction counts vary across cycles.
* **Structural Hazard Tracking:** Directly highlights when instruction stalls occur due to FU allocation limits (`denials > 0`).

---

## 4. Verification & Validation Evidence

* **Simulator Execution:**
  * GEMM executed end-to-end on `DerivO3CPU` timing model with `PROTOCOL=CHI`.
  * Terminal output confirmed: `Job complete. Checking result. Comparing CPU run to accelerated run. Check Passed.`
* **Visualizer Export:**
  * Parsed 4,352 trace events, extracting 2,176 completed instruction spans across 271 cycles.
  * Zero unreleased grants remaining.
  * Verified HTML output: `BM_ARM_OUT/gemm_run/visualizer.html`.
* **Workbench GUI Offscreen Verification:**
  * Ran `QT_QPA_PLATFORM=offscreen python3 -m salam_workbench.configurator_app --inspect`.
  * Result: `"state": "ready"`, all 5 workbench tabs and 43 catalog benchmarks initialized cleanly.
