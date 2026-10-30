# Configurable benchmarks with independent output checks

This milestone expands the checked configuration pipeline across integer GEMM,
double-precision FFT and a three-dimensional integer stencil. The original
reference workloads remain separate, preserved experiments.

## Accepted backend study, 2026-10-30

The rebuilt isolated engine completed 12 positive simulations and correctly
rejected three corrupted-output controls despite a guest success marker. All
six setting comparisons passed. Seeds 1 and 2 produced distinct numeric inputs;
each setting pair retained identical complete output hashes.

| Workload | Changed effective cycle-count field | Accelerator ticks, latency 1 | Accelerator ticks, latency 4 | Outputs checked per run |
| --- | --- | ---: | ---: | ---: |
| GEMM | `mul` | 2,700,000 | 2,730,000 | 64 int32 values |
| FFT | `fmul` | 778,400,000 | 860,340,000 | 1,024 complex values |
| stencil3d | `add` | 472,100,000 | 493,090,000 | 16,384 int32 values |

These accelerator intervals matched for both input seeds at each setting.
They are simulated invocation measurements, not whole-guest time or physical
hardware performance. Every positive run passed complete independent FU replay.
The first stencil invocation replayed 434,124 events plus its separate top-level
invocation; they are not summed as independent accelerator work.

Local raw evidence is retained under
`evidence/configurable-breadth-20261030T083948-bb1763e3/`, including `study.json`,
every specification, source snapshot, build-input witness, run contract, actual
output file, effective configuration and direct SALAM traces. The isolated
build is bound by `evidence/breadth-engine-build-20261030-v2/build/build.json`.
Raw runs, binaries and machine bindings are ignored by Git. Original engines,
recovered sources and earlier rejected or interrupted attempts remain intact.

The production desktop window also completed a real generated-input GEMM run
(seed 17), with edited memory/FU settings, a 1,048,576-event trace-budget
override, 405 effective-setting checks, complete scheduling replay, and all 64
outputs checked independently. The Run button, background completion gate,
results reader, topology renderer and saved screenshots were exercised without
mocking a simulator result. This was Qt offscreen acceptance, not a manual
Windows interaction test. Its local receipt is
`evidence/desktop-workbench-acceptance-20261030T090848-b5a1535e/acceptance.json`.
The GUI suites also check preset round trips and rejection of changed selectors
or nominal success receipts without current evidence. GUI-driven hardware
profile rebuilds for FFT/stencil are not established by the backend matrix.

Final automated validation passed 541 checks (250 fast, 239 configuration,
52 GUI), with zero skips, failures or unassigned test modules. The native C++
scheduler test also compiled and passed with warnings treated as errors; it
tests the small/default/expanded trace bounds and balanced ownership counters.
Local receipts are under `evidence/checks/20261030T090815-fast-a3fa96ef66`,
`evidence/checks/20261030T090823-config-2bf8e4bfd2`,
`evidence/checks/20261030T090828-gui-e3c80368c7`, and
`evidence/breadth-native-scheduler-validation-20261030-v1`.

## Contract

| Workload | Supported shape | Independent host reference |
| --- | --- | --- |
| GEMM | 8 x 8 int32 matrices | Ordinary complete matrix product; 64 outputs |
| FFT | 1,024 complex binary64 samples | Direct discrete Fourier transform, reordered for the recovered kernel; 1,024 complex outputs |
| stencil3d | 16 x 32 x 32 int32 grid | Coordinate-based seven-point stencil with explicit preserved boundaries; 16,384 outputs |

Select **Generated input / independent full-output check** in the configuration
editor and choose a deterministic seed. Zero and boundary input options are
also available. Presets retain the selected input. Original source input keeps
the original guest-checker contract; it does not acquire an independent oracle
by being displayed beside these options.

The simulator acceptance above covers the two seeded input cases. Zero and
boundary options additionally have host oracle and transport tests; that is not
a claim that every option/profile/topology combination has been simulated.

The backend regenerates the complete input fixture from the saved selector,
stores its SHA-256, stages a fresh guest and accelerator IR, and compares every
emitted result with the host reference. Integer checks are exact. FFT checks
require finite values and use `abs(error) <= 1e-6 + 1e-9 * abs(expected)`.
Truncated, duplicated, unordered or incorrectly identified output is rejected.

The shapes are deliberately fixed. This does not establish arbitrary matrix
dimensions, FFT sizes, stencil dimensions, memory topologies or calibrated
physical-hardware performance.

## Guest output and staged repairs

The guest writes its actual post-accelerator buffers into one complete hex
protocol block at `simulator/salam-results.txt`. The engine's existing ARM
semihosting SYS_GEM5 bridge calls gem5's writefile implementation. The runtime
explicitly instantiates `ArmSemihosting`; the effective configuration witnesses
both the object and its system binding. The run contract requires the output
file and records its hash. The results reader replays the numerical check from
the file, rather than trusting a saved success field.

The ARM32 entry uses `svc #0x5d57`, operation `0x100`, and five 64-bit argument
slots `{0x4f00, buffer, length, 0, filename}`. A DSB and compiler memory barrier
precede the call; the guest requires the exact returned length. This avoids the
older direct ARM32 m5_write_file register ABI's insufficient argument capacity.
The file is an explicit benchmark output, not an accelerator performance trace.

Two defects exposed by real runs are repaired only in staged guest sources:

* `_write_r` now writes exactly its length-delimited byte count. The recovered
  implementation used a NUL-terminated printer and leaked stale buffer tails.
* ARM32 `m5_exit` clears both words of its 64-bit delay argument and declares
  register/memory clobbers. Previously a nonzero high word could delay exit
  after output printing.

The stencil IR Makefile receives an explicit ARM target. A staged, source-bound
RegisterBank adapter makes explicit port requests visible to the contract. The
compiled component has a scalar private response port: more than one private
connection is rejected before generation. This study explicitly requests one
port, recording that the recovered YAML requested two while the older generator
silently created one. Multiport implementation requires separate C++ response,
queue and retry handling plus a rebuild. Exact recorded peers, including
requestor port indices, are checked. Unsupported scratchpad-only controls on
RegisterBank still reject.
Accelerator C kernels and the original external engines remain unchanged.

Every repair records source, template and generated-output hashes. Earlier
failed, slow or interrupted attempts are retained as diagnostic evidence.

## Reproduce the explicit study

From the fork's `workbench` directory in the configured WSL environment:

```bash
python3.8 -B scripts/verify_configurable_breadth.py \
  --engine /absolute/path/to/verified/configuration-engine \
  --build-receipt evidence/path/to/build.json \
  --workloads gemm,fft,stencil3d --seeds 1,2 --simulate
```

Without `--simulate`, the helper records a plan only. The default simulated
study requests 12 positive experiments (three workloads, two seeds, two
instruction-latency settings) and three deliberately corrupted-output controls.
Each control requires the guest to print success while the independent host
checker rejects the numerical mismatch. Control options are explicit in backend
receipts and are unavailable through ordinary GUI input controls.

Each setting pair requires identical numeric inputs and output hashes, witnessed
instruction latency, complete direct SALAM evidence and an observed increase in
the accelerator interval. Inputs across seeds must actually differ; changing a
seed label alone is insufficient. The study retains the preexisting unwitnessed
bare-metal option explicitly; any additional unknown system option fails the
study's acceptance contract.

Whole-guest `stats.txt` values may include guest preparation, checking and output
work. An explicit dump occurs before output serialization, but the general
report reader can select the final exit dump. Timing comparisons therefore use
the separately identified direct SALAM invocation interval.

## Remaining breadth

The full-size stencil exceeded the earlier 262,144-event trace bound. The
rebuilt engine exposes `LLVMInterface.fu_trace_event_limit`: default 262,144,
range 1 through 4,194,304. This study explicitly requests 1,048,576 for stencil.
The GUI has an optional **Override scheduling trace event budget** control, and
presets retain it. The constructor validates the bound; invocation resets keep
the chosen value; direct FU JSON records it. The host checks that the recorded
budget matches `config.ini` and replays every event. This affects retained
diagnostics, not FU admission, timing, resource counts or numerical execution.
Truncated traces continue to fail. The GUI bounds direct JSON reads to 64 MiB;
a larger requested maximum does not remove that reader bound.

This is the first bounded expansion. Arbitrary dimensions, complete topology
families, multi-accelerator workflows, pipelined resource policies and a clean
installation remain separate work.
