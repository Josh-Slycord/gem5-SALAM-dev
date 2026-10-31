# gem5 26 port: validation record

**Source-validation snapshot, 31 October 2026 UTC. Configured GEMM/FFT/stencil port qualification is complete for the tested scope. The upgrade remains on a separate unmerged branch, with the known limitations and unresolved stability failures recorded below.** This document describes a local port and its observed evidence. It is not a publication performance claim or a declaration that all configurations are supported. The integration branch is `codex/gem5-26-upgrade`; repository delivery and hosted CI are reported separately from this pre-publication source-validation snapshot. Josh's working `main` remains `48fe84fa2f1c52e95fbc2382d62f26013fa78cd7`. Official repositories have not been changed.

Six real GUI numerical cases are complete across GEMM, FFT and stencil, using distinct seeds 17 and 23 for each family. The final independent aggregate passed: **34,944 complete outputs compared, zero mismatches and 12 complete FU invocations replayed**. Stencil23 uses an explicitly bounded-process composite after two failed monolithic audit attempts; the failures remain unresolved and are not relabelled as passed. The original stencil fresh GUI build remains failed; its successful serial recovery and later GUI cache reuse are reported separately.

## Implementation and preservation

The port integrates the pinned gem5 v26.0.0.0 release `fed0e07e930fecf1e73dce94dd44e69a5bf70c46` into an isolated Ubuntu 24.04 checkout and runtime. Upstream [PR #2429](https://github.com/gem5/gem5/pull/2429) was reviewed first; its captured head is `b4ff9f5aaa0e4d3df9bf503df2212a278eb59645`, open and unmerged at the recorded snapshot. It is a design/reference input, not evidence that this local implementation is the official PR or that upstream has accepted it.

The Ubuntu 20.04 working engine, its build receipt, workspace file and `main` baseline were preserved and compared against the before-port identities; a fresh check immediately before branch publication passed again, including the genuine configured-engine receipt. An observed Ubuntu 20.04 user-session startup warning remains documented; no repair, relaunch or configuration change is claimed. The old configured binary remains SHA-256 `1c8f96ca73535df2f5019d5ac74c7c3bf134ad0618e51f69fd62d6a0388f1e05`. This is a bounded preservation check of the recorded files, not a byte comparison of every WSL file. The legacy guest-result header is byte-identical to working main, SHA-256 `31e407229f8d837774bdb501deea2fc3b49df8dc76232820e89d4a4af26bb744`.

The modern sealed base simulator is an actual ARM build, version 26.0.0.0, linked against LLVM 14. It runs ordinary embedded Python without `M5_OVERRIDE_PY_SOURCE`. Its binary SHA-256 is `a1e3bfc878857a3d438379de60992cd37beaed11d3d56bb0581b0704d784e295`; compiled-source digest `dec3657244dc83dfe224aca33822dcfe20489fbf1d28125c2d40b3647635120c`; source-inputs digest `356a0069459c1dc0afc1b6914c4bf9a47a09df8abd1d81f63dd51a6f6bc3a43d`. The genuine build receipt has SHA-256 `8a48c006cece1944b11561c0412373e4a3e7f23e8b4eaaeb40173b8ca300e5e4`.

## Completed checks and current qualification

| Layer | Observed result | Scope |
|---|---|---|
| Workbench outer tiers | **661 passed:** fast 310, config 289, GUI 62 | Proper wrapper invocations; exact discovered/selected inventory; no skips, failures, errors, duplicates or missing tests; source unchanged. |
| Native gem5 PyStats | **18 passed** in the ordinary embedded engine | Selected `tests/pyunit/pystats` directory, not the entire upstream Python test suite. |
| Retained C++ components | **2 standalone executables passed** under C++20 | Synthetic functional-unit pool and statistics collector tests; not two gem5 GTest suites or simulation proof. |
| Ordinary GEMM baseline | **64 outputs passed** | Fresh seed 17, TimingSimple CPU, 2 GB memory, genuine sealed base receipt; full host oracle and separate NumPy reader. |
| Current GUI GEMM seed 17 and 23 | **Both passed**, including independent replay | Actual Qt Run action, regeneration, real simulator, full 64 outputs each, distinct input and raw-output hashes. |
| Current GUI FFT seed 17 | **Passed**, including independent pair replay | Fresh required profile rebuild; real simulator; full 1,024 complex outputs. |
| Current GUI FFT seed 23 | **Passed**, including independent pair replay | Verified rebuilt-profile reuse; same genuine rebuilt binary, different generated input and output. |
| Current GUI stencil seed 17, recovered profile | **Passed, including independent replay** | Real Run action, genuine serial-built profile verified and reused; all 16,384 outputs agree. This is not a fresh GUI rebuild success. |
| Current GUI stencil seed 23, recovered profile | **Passed; independent bounded-process composite** | Real Run action, same serial-built profile verified and reused; all 16,384 outputs agree and full traces pass. Two monolithic audit attempts remain failed; no single-process full-audit success is claimed. |
| Hosted GitHub CI | **Not run at this pre-publication source-validation snapshot** | Local workflow checks passed. Current branch delivery and hosted status belong to the PR checks and separate delivery record. |

The current workbench tests and current GEMM/FFT/stencil GUI runs use frontend source digest `e587aa003eace020e3db9ec7040d78ddeba980426b761d10aeb428a7e8926875`. The GUI driver uses the product's Qt interface with a real Run click and no mocked backend results. The rendered acceptance path is Qt offscreen; this does not claim a manual Windows interaction or UX review. FFT's fresh and reused profiles use simulator SHA-256 `86a6901ecd222aa1062bbf66b917eef9fbc92658d0b314d3a22432bc69d9a418`.

The independent FFT pair replay compared all 1,024 complex values per seed; recorded maximum absolute errors were approximately `6.04e-14` and `8.17e-14`. The generated-profile comparison matched all 130 recorded generated files. Numerical agreement is limited to these tested inputs, shapes and tolerances.

Configuration receipts separately witness parameters, memory transport, functional-unit settings and generated/rebuilt hardware profiles. The bare-metal setting remains **partial**: the actual workload class is recorded, but the existing witness does not fully map it to the requested bare-metal field. Other witnessed settings do not resolve that gap. GEMM changed CPU, instruction latency and functional-unit limits together; its runs do not isolate a causal functional-unit speedup.

### Independent replay scope and native audit failures

Independent raw numerical algorithms import no workbench oracle or pass flag. Provenance, GUI and FU trace replays use the current production verifiers; they do not claim an independently implemented scheduler model. The final aggregate binds each case's input/output hashes, actual engine and compiled-source identity, normal simulator exit, complete event inventory, effective profile and transport checks.

Two monolithic stencil23 independent audit processes failed with native `free(): invalid pointer` aborts before a complete audit result. Their exact failed attempts and hashes remain linked in the final aggregate. A separate explicit composite then completed every original assertion across **fresh bounded ordinary processes**, each with actual normal return code 0: raw source/engine/history/input/output/NumPy/profile checks; exact two-file FU inventory; target and top inspect phases; target and top direct replay phases; and the unmodified production completion adapter. No allocator flags, forced exits or swallowed aborts were used. The composite and its assembler also exited normally. This qualifies those completed gates for this fixed case; it does not establish a successful one-process audit or resolve the native aborts.

The broader stability investigation remains open: compiler internal errors, earlier transient binding rejections and these native aborts have no established cause. A bounded Windows WHEA provider query and recent Ubuntu24 kernel fault-pattern query reported no matching entries; that observation does not rule out hardware, OS, compiler, allocator, filesystem or code faults. Exact query errors, corrected commands and outputs are retained. No hardware or WSL setting was changed and no causal attribution is made.

## Controls against a false pass

Each forced-guest-pass control actually executes the ordinary sealed simulator with a genuine build receipt. Seed 31 inputs deliberately corrupt one output while forcing the guest to print `Check Passed` and exit normally. The host must still reject the complete raw output through `independent_full_output_failed`; a missing file, malformed output or timeout is insufficient.

| Control | Complete output compared | Native/guest result | Independent result |
|---|---:|---|---|
| GEMM | 64 scalar values | Return code 0, normal `m5_exit`, guest passed | Host and separate NumPy reader each reject exactly one intended value at index 0. |
| Stencil3D | 16,384 scalar values | Return code 0, normal `m5_exit`, guest passed | Host and separate NumPy reader each reject exactly one intended value at index 0. |
| FFT, corrected unfused frontend v2 | 1,024 complex values | Return code 0, normal `m5_exit`, guest passed | Host and separate NumPy reader each reject exactly one intended value at index 0. |

A separate completed GUI corruption control copies the accepted GEMM output and changes one word from `-108` to `-107`. It preserves the guest's passed marker, normal-exit evidence and valid transport hashes. Both full 64-value production and separate NumPy comparisons reject exactly that value, and the actual Qt validation widgets display a failed assessment. All 316 original files remain unchanged. This tests re-evaluation of copied real output; no simulator rerun or additional accepted benchmark is represented. The exact maintained Qt harness also rejected one altered FFT value out of 1,024 and one stencil value out of 16,384, while the separate NumPy baseline checks passed and corrupted checks failed with exactly one mismatch. Both widgets failed only the independent numerical check; valid transport and guest-exit evidence remained intact. All 633 original FFT/stencil files remained unchanged. Together with GEMM, these copied-output GUI controls cover all three families; the original failed combined GUI batch retains its failed state even though its individual FFT case passed.

These are successful **failure-detection controls**, counted separately from passed benchmark runs. The original FFT control timed out with known unsupported LLVM 14 constructs present; the corrected unfused control passed. The exact point of the original hang was not established. The timed-out attempt is preserved as a failure finding and is not counted as a valid negative control. Stencil explicitly uses the existing scalar register-bank `Ports=1` configuration. No vector-port feature was added to make the test pass.

## Compatibility work supported by the evidence

- **Guest output ABI:** modern ARM32 semihosting reads 32-bit argument slots. The older 64-bit slot packet could print a guest success message before failing to produce a file. The modern-only adapter now emits checked `uint32_t[5]` slots and rejects overflow. Source-bound native ABI controls and ordinary real output runs support the repair; legacy packet bytes remain unchanged.
- **Compiler and target headers:** actual selected clang/ARM GCC tools replace hardcoded LLVM 12 assumptions in staged build and independent input checks. LLVM 14 IR compilation receives explicit target SDK paths (`--sysroot=/usr/lib/arm-none-eabi` and `-isystem /usr/lib/arm-none-eabi/include`). These flags apply to target compilation, without host-global include variables.
- **Floating-point IR:** the default clang 14 FFT emitted one unsupported `fneg` and two `llvm.fmuladd.f64` calls. A real bounded compile proved that `-ffp-contract=off` produces the supported unfused scalar form, with none of those instructions and successful LLVM verification. Modern staged recipes enforce this policy. The new preflight detects these known gaps; it is not a complete proof of LLVM opcode support.
- **Native APIs and configuration:** the port updates SimObject registration, ARM CPU aliases, current port names, retained helper APIs and build requirements. System construction uses validated semantic template markers rather than fixed line positions. Missing/duplicate markers are rejected and tested.
- **Native PyStats:** a stale selected upstream test imported a removed `SerializableStat`. The replacement exercises the current typed JSON visitor with nested groups, vectors, primitive values and permitted null metadata. A deliberately wrong child ordering fails its test. The removed API was not reinstated and the test was not skipped.

## Reproducibility boundaries

The observed environment is Ubuntu 24.04, Python 3.12.3, host GCC/G++ 13.3, ARM GCC 13.2.1 and LLVM 14.0.6. Exact executable and linker-library hashes are in the toolchain/build receipts. The GUI/tooling virtual environment is separate: PySide6 6.8.3, NumPy 1.26.4, NetworkX 3.2.1, PyYAML 6.0.3, pydot 1.4.2, SCons 4.8.1, ply 3.11 and packaging 24.2. The native simulator uses system Python modules, including PyYAML 6.0.1 and pydot 1.4.2; it does not inherit the virtual environment's entire dependency set.

Installed packages do not establish compiled features. Actual generated build flags show HDF5, PNG and Capstone disabled; protobuf, zstd and SystemC enabled. KVM build flags identify **x86 KVM**, not usable ARM acceleration under WSL. POSIX clock availability is enabled while its use is disabled. Only the selected ARM configuration is qualified here.

Actual GEMM leaf PIO regions retain DMA at `0x10020000`, top at `0x10020040` and GEMM at `0x10020080`. Optional SCMI/mailbox objects are absent from the actual run, so they do not alias that DMA address. This is a scoped observation of the instantiated topology, not an arbitrary future memory-map guarantee. Native `config.dot` and rendered SVG artifacts exist (one captured graph contains 80 nodes and 67 edges). A graph demonstrates configuration connectivity, not numerical or timing accuracy.

SALAM invocation metrics and whole-guest gem5 statistics retain their different scopes. CPU execution, startup and memory traffic can affect whole-guest measurements. Power/energy values remain **uncalibrated model estimates**; neither these runs nor the graph establishes silicon power, transistor size accuracy or publication-ready performance validation.

GCC 13 has produced internal compiler faults during generated Python-module compilation. An earlier exact target succeeded when retried serially with unchanged source and compiler hashes. The later stencil fault occurred even while profile builds were sequential, each using eight workers. These records do not establish a root cause (memory pressure, WSL, compiler or source defect). Failed receipts and caches were preserved. A genuine production `build_engine` recovery in the same variant cache passed with `-j1` and unchanged source/compiler bindings. The resulting binary SHA-256 is `31509767be4541c839abd7efb8a2b95a0037a159f9a23d4c12086564462329ec`, with compiled-source digest `b6720d1ff296385cd35a291388c09852e758f12d55aaec2b56741d0c1e59445b`. All six original failed records remain unchanged. This successful serial build does not relabel the original failed GUI attempt or substitute for the separately completed numerical runs. The CLI accepts `--jobs 1` for a conservative rebuild; the current GUI uses its default eight workers and has no equivalent exposed job-count control. Do not fabricate a success marker or relabel the failed GUI build as passed.

Recovery also exposed **unexplained verification rejections**. The first strict publish attempt rejected the base engine's source binding, and an independent first round later rejected its binary binding. The mismatched value/inventory at those exact rejection points was not captured. Subsequent unmodified production checks passed for both base and recovered engines; independently captured production return values, native `sha256sum` and stable file-descriptor reads agreed with the recorded binary hashes. Both 9,860-file source inventories were stable in two rounds, with no changed or unstable files; loaded checked functions matched freshly loaded current source. These later observations do not explain the earlier rejections or establish ongoing host integrity. The rejected attempts remain failed and no RAM, WSL, filesystem, cache or concurrent-writer cause is assigned. A subsequent run of the **unchanged strict sealer** passed every normal gate and atomically published the recovered profile marker. It rechecked 130 generated outputs, 15 generation inputs, 130 overlay before-images, both genuine engine/build bindings and full variant/profile validation before publication. The real stencil seed-17 GUI then passed complete host numerical validation and FU/observability replay using that verified recovered profile. Independent stencil17 replay passed. The seed-23 real GUI also passed host full-output and trace checks using the same recovered profile, and its subsequent bounded-process composite completed all original independent audit assertions with ordinary normal exits. The final six-case aggregate passed. Both stencil GUI cases are verified cache reuse of the actual serial recovery, not fresh GUI rebuild successes. These later successes do not erase the earlier failed build or verification attempts.

## Reproduction commands

Use a separately prepared modern workspace, `workbench/requirements-gui-gem5-26-validated.txt`, a genuine build receipt for the selected engine/profile and a fresh evidence directory for each invocation. The GUI driver reads the configured workspace. Run the module commands from the checkout's **workbench directory**. GUI evidence must stay under that directory's `evidence/` tree because the driver validates its path. Replace every example path and unique suffix before running.

```sh
cd /path/to/checkout/workbench
PYTHON=/absolute/path/to/modern-venv/bin/python

PYTHONNOUSERSITE=1 "$PYTHON" -m salam_workbench.checks \
  --tier fast --engine /path/to/sealed-engine --evidence-root evidence/repro-fast-unique
# Repeat with --tier config and --tier gui, using separate evidence paths.

PYTHONNOUSERSITE=1 "$PYTHON" -m salam_workbench.configurator run \
  --engine /path/to/sealed-engine --spec /path/to/experiment.json \
  --build-receipt /path/to/genuine-build.json --evidence-dir evidence/repro-run-unique \
  --jobs 1

PYTHONNOUSERSITE=1 "$PYTHON" scripts/verify_workbench_window.py \
  --cases configured:fft --input-seed 17 --require-rebuilds \
  --evidence-dir evidence/repro-gui-fft17-unique
# A separate seed-23 invocation may use --verify-rebuilt-profiles for cache qualification.

PYTHONNOUSERSITE=1 "$PYTHON" scripts/verify_numpy_outputs.py \
  --fixture /path/to/input-fixture.json --raw-output /path/to/raw-output \
  --expected-fixture-file-sha256 FIXTURE_SHA256 \
  --expected-output-sha256 OUTPUT_SHA256 --receipt evidence/repro-numpy-unique.json
```

The separate modern profile can be opened from Windows PowerShell using its existing launcher (or the equivalent launcher path in a portable copy):

```powershell
& '\\wsl.localhost\Ubuntu-24.04\home\jslycord\projects\gem5-salam-26\workbench\workbench.ps1' -Action configurator
```

This launches the modern Ubuntu 24.04 workspace. The preserved legacy shortcut remains unchanged. The recorded automated GUI acceptance is rendered offscreen; this command is a launch route, not evidence of a completed manual desktop review.

For forced-pass controls, use the actual schema's `inject_mismatch=true` and `force_guest_pass=true`, seed 31 and the recorded full output shape. An expected nonzero workbench result is only acceptable with normal native exit, complete output and exactly the intended numerical disagreement. Preserve the unmodified fixture/source, binary and raw-output identities.

Raw run directories, binaries and bulk build output remain local ignored evidence. The companion `GEM5_26_EVIDENCE_INDEX.json` records primary paths and SHA-256 identities; `GEM5_26_EVIDENCE_INDEX.md` provides readable scope labels. Public source and reproduction commands can be committed separately from bulky local artifacts. `GEM5_26_KNOWN_GAPS.md` records the remaining work and exclusions. The final six-case primary aggregate is SHA-256 `e80d0e58af89ef95e2fa57149c9ae8ac724adb546519de8d92f4fb4494248c45`. This local source-validation snapshot predates branch publication. Current repository delivery and hosted CI status are tracked separately in the PR checks and local delivery record; they are not implied by the completed scoped qualification.
