# gem5 26 migration

This branch ports the validated SALAM accelerator model to the pinned
[gem5 v26.0.0.0 release](https://github.com/gem5/gem5/releases/tag/v26.0.0.0)
(`fed0e07e930fecf1e73dce94dd44e69a5bf70c46`). It preserves the working
gem5 21-based `main` at `48fe84fa2f1c52e95fbc2382d62f26013fa78cd7`.
The original Ubuntu 20.04 runtime, GUI binding and Windows shortcut remain
available independently of this branch.

## Upstream review and port boundary

[Upstream PR #2429](https://github.com/gem5/gem5/pull/2429) was reviewed before
porting, at head `b4ff9f5aaa0e4d3df9bf503df2212a278eb59645` on 2026-10-30.
It was open and unmerged at that snapshot. Its style/metadata checks do not
establish simulator or numerical validation.

That PR introduces a substantially different SALAM implementation and
functional-unit model. In particular, zero limits mean inferred static
instances there, whereas this workbench's accepted scheduler uses zero for
unlimited units. Its events also do not implement our complete event-replay
contract. This port therefore retains the validated SALAM model, generator
and independent numerical checks; it uses the upstream work as an API/build
reference rather than replacing those contracts wholesale.

The two repository histories were unrelated. The migration records both real
parents and explicitly uses gem5 21.1.0.1
`082f0835b098887f0fdb89db908b59221b027686` as a content comparison base.
Obsolete working-tree copies were preserved outside the isolated checkout
with a hash manifest. The original checkout was not used as a porting target.

## Isolated toolchain

The current port uses Ubuntu 24.04, GCC 13, Python 3.12, SCons 4.8.1 and matched
LLVM/Clang 14. The modern GUI lock is
`requirements-gui-gem5-26-validated.txt`; the legacy lock remains separate.
Exact installed tools and package records belong to the local build evidence.

Opt in through `configuration_engine.toolchain_profile` in this branch's
private `workspace.json`, with ID `gem5-26-retained-salam`. Absolute tool paths
may be provided explicitly. With no profile, legacy command selection remains
unchanged. The profile selects tools; it does not establish a successful build.

gem5 26 consumes `CXX` and `PYTHON_CONFIG` from the process environment. Merely
passing `CXX=...` or `PYTHON_CONFIG=...` as SCons arguments does not select them.
The modern adapter binds and records the environment explicitly. LLVM flags
are queried without importing LLVM's C++ language/exception policy into gem5.

An explicit build example, after installing the documented prerequisites:

```sh
export PYTHONNOUSERSITE=1
export CXX=/usr/bin/g++
export PYTHON_CONFIG=/usr/bin/python3.12-config
/path/to/isolated/venv/bin/python -m SCons build/ARM/gem5.opt \
  --with-salam LLVM_CONFIG=/usr/bin/llvm-config-14 -j8
```

Build both source-provided ARM bootloaders before configured simulations:

```sh
make -C system/arm/bootloader/arm CROSS_COMPILE=arm-none-eabi-
make -C system/arm/bootloader/arm64 CROSS_COMPILE=aarch64-linux-gnu-
```

The generated workspace stages and hashes the selected boot binaries.
These boot outputs and simulator results are ignored by Git; their sources,
recipes and validation receipts are retained.

## Compatibility changes

- SALAM's optional SCons integration uses explicit SimObject registrations,
  modern ARM build guards and per-variant CACTI/LLVM linking.
- Request/response ports use current gem5 constructors; scratchpad timing
  randomness uses the modern per-object random source.
- Both copies of the hardware generator emit the modern build guards. The
  capability marker is reissued from verified source bytes without claiming
  that a source declaration proves compiled behavior.
- Generated ARM system setup uses current workload, CPU and connection APIs.
  CPU requests and their effective ARM classes are recorded separately.
- Build provenance includes public headers, build tools and Kconfig inputs,
  as well as simulator sources. Modern receipts snapshot effective Kconfig.
- Modern ARM32 output transfer uses checked 32-bit semihosting slots; the
  historical result header and its legacy ABI remain unchanged.
- Staged LLVM 14 compilation uses the selected ARM target SDK and explicit
  include path. `-ffp-contract=off` retains supported scalar floating-point
  operations. Preflight rejects known unsupported FNeg/FMA forms; complete
  LLVM instruction validation remains unimplemented.
- Source-bound outer self-checks retain the selected virtual environment's
  executable path. Only the two derived SLICC PLY cache files are excluded
  from compiled source identity; real parser sources remain fingerprinted.
- Imported official automation jobs are restricted to `gem5/gem5`. Personal
  workbench validation runs separately with read-only workflow permissions.

The existing SALAM MMIO region at `0x10020000` is retained. The optional SCMI
mailbox uses that region only when SCMI is explicitly attached; its class
definition alone is not evidence that our generated systems attach it.
Actual configured address ranges remain part of simulation verification.

## Open the separate workbench

Bind the modern profile only in this branch's private workspace. From Windows
PowerShell in its `workbench` directory, use:

```powershell
.\workbench.ps1 -Action configurator
```

The existing desktop shortcut still opens the preserved gem5 21 installation.
The recorded modern GUI tests use the actual Qt Run action and backend in
offscreen mode; a manual Windows desktop review is separate.

The GUI currently uses eight build workers. Its backend CLI supports
`--jobs 1`. GCC 13 internal compiler crashes occurred in generated upstream
Python-module compilation; an unchanged-source serial rebuild recovered the
stencil profile. Failed records remain failed. The recovery and subsequent
GUI cache reuse are documented separately from FFT's successful fresh GUI
rebuild. The compiler failure's root cause remains unproven.

## Acceptance and evidence

Acceptance requires a real simulator build and fresh configured GEMM, FFT
and stencil runs through the production GUI's QProcess route. Each must
preserve generated-input provenance, full independent numerical checks,
effective configuration witnesses and complete required scheduling replay.
Deliberately corrupted output must be rejected even when guest/recorded pass
markers remain present. Regeneration and profile rebuilds must be exercised.

Standalone C++ tests and source-only Python/Qt tests complement those checks;
they do not substitute for running the accelerator. Whole-guest statistics
retain their scope and are not labelled as accelerator-only or physical
hardware measurements.

Fixed-reference execution is initially refused on the modern profile until
its separate historical harness has been validated there. Legacy reference
workloads remain available in the preserved Ubuntu 20.04 environment. Manual
launch scripts, checkpoints, optional Ruby/SCMI systems, other ISAs and
physical power accuracy require separate coverage before support claims.

See the [validation record](GEM5_26_VALIDATION.md),
[qualification limits](GEM5_26_KNOWN_GAPS.md), and
[local evidence index](GEM5_26_EVIDENCE_INDEX.md). Raw run artifacts and
binaries remain local ignored evidence with recorded hashes. This branch
is published separately and remains unmerged into the working `main`.
