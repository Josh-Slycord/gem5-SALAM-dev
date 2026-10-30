# Scalar functional-unit scheduling

Validated on the recovered 8 × 8 integer GEMM with two fresh simulations per setting, plus a separate intentionally wrong-output simulation. These are accelerator invocation measurements from direct SALAM output.

| Integer multiplier capacity | Accelerator cycles, both repeats | Dynamic multiplies | Denied issue attempts per run | Peak occupancy |
| --- | ---: | ---: | ---: | ---: |
| 0, unlimited | 1,054 | 512 | 0 | 8 |
| 1 | 8,206 | 512 | 100,184 | 1 |
| 2 | 4,126 | 512 | 36,912 | 2 |
| Unlimited; unused divider capped at 1 | 1,054 | 512 | 0 | 8 |

Every positive run passed the guest's independent CPU reference, released all 512 multiplier leases, and ended with zero outstanding occupancy. The unused divider received no grants. Multiplier latency was 16 accelerator cycles in all cases. Denials count repeated admission attempts while resources are occupied; they are not stall cycles.

## What is enforced

`FunctionalUnitBase.limit` now controls a shared admission pool across active functions. Zero means unlimited. A supported scalar compute instruction receives a unique lease when issued and holds it until completion. A denied instruction remains queued and retries. Both zero-latency and queued completion release their lease exactly once. The existing FU occupancy counters follow the same events.

The implementation is nonpipelined occupancy from issue to completion. Positive limits on memory/control/unsupported paths are refused. Nonzero per-instruction `functional_unit_limit` is also refused. Pipelined initiation intervals, memory-port scheduling, and per-instruction limits remain separate work.

Each accelerator invocation writes `observability/fu-scheduling-<SimObject>.invocation-<n>.json`, alongside the SALAM lifecycle file. The file records configured capacity, attempts, grants, denials, releases, peak/final occupancy, and bounded grant/deny/release events with unique lease IDs. A truncated trace is insufficient for a passing replay witness.

## Independent checks

The verifier reloads raw run receipts and snapshots instead of trusting a report's pass label. It independently replays leases, enforces capacity, recomputes counters, checks tick/cycle consistency and 16-cycle multiply lease durations, and binds scheduling events to the lifecycle output and effective `config.ini`.

Across controlled cases it requires distinct raw runs, the same simulator build and source identity, equivalent effective settings except the designated capacities and staging paths, the same benchmark C/LLVM IR and checker, and matching executable ARM `PT_LOAD` bytes and execution metadata. A raw ELF hash may vary because of nonloaded metadata; executable load-image comparison includes entry point, segment addresses, flags and zero-filled memory sizes.

The negative control compiles a separate ELF with `WORKBENCH_INJECT_MISMATCH`, flips output element zero after computing the reference, and reaches normal `m5_exit`. It reports `Check Failed`; the runner records failure. The verifier binds the macro, changed load image, source and engine to the positive control. A successful process exit alone therefore cannot produce a passing numerical check.

A first diagnostic run exceeded the original 65,536-event trace budget. Replay rejected it despite a passing numeric checker. The simulator was rebuilt with a 262,144-event bound, and the complete matrix was rerun. Historical failed evidence stays failed.

## GUI acceptance

An actual Qt form edited multiplier capacity to one and used its production QProcess path to apply settings and run gem5. That run reproduced 8,206 accelerator cycles, 512 grants/releases, 100,184 denied attempts and peak occupancy one. The GUI displayed counters only after the effective-configuration and direct-event checks passed. Separate revalidation passed 399 effective-configuration checks and replayed both accelerator invocations. This was an automated offscreen Qt acceptance run; a manual Windows desktop session has not been claimed.

## Reproduce and inspect

After binding a verified external engine with the [existing-engine bootstrap](../README.md), run:

```bash
python3.8 -B scripts/run_fu_study.py \
  --engine /absolute/path/to/verified-engine \
  --build-receipt /absolute/path/to/build.json \
  --evidence-dir "$PWD/evidence/my-fu-study" \
  --allow-simulation
```

The command creates eight positive simulations and a wrong-output control. Use a new evidence directory each time. The four controlled requests are in [`experiments/fu_scheduling`](../experiments/fu_scheduling/); replay logic is in [`fu_experiments.py`](../salam_workbench/fu_experiments.py). Raw results and binary/build artifacts stay local and ignored. This repository publishes the source, requests, verifier and authored findings.

The accepted study's simulator SHA-256 was `fb2e355723dc0572e342d50fbd8c5711f51fd7c7d287fb4c5b755b5621f2ade8`; compiled source identity was `3f99894985051727fef026ffc3a2cfed2e47ddd08e359e3e5294142e71ffc66f`. These identify the measured build, not a downloadable prebuilt release or a fresh-machine installation guarantee.

The timings establish this scalar scheduling behavior on one workload. They do not establish physical hardware speed, energy, power, area, transistor counts, all-benchmark correctness, or memory/control scheduling. gem5 `stats.txt` still provides whole-system context; whole-guest totals must retain that scope.

## Fork-layout publication acceptance

The controlled eight-positive-run matrix and separate wrong-output run were reproduced from the fork's `workbench/` source layout. A subsequent actual offscreen Qt capacity-one run and independent GUI revalidation passed 399 effective-setting checks and both direct accelerator traces. The final source-bound unit tiers passed 352 tests with no skips or unassigned modules. The binary matched both the guarded Python checksum and an independent native `sha256sum`.

Migration rehearsal exposed a missing build-source sidecar. The bootstrap now verifies and copies it, and the study refuses missing build provenance before simulation. Earlier incomplete/rejected attempts remain separate local records. Intermittent WSL systemd startup timeouts and one transient checksum discrepancy remain documented environment observations with an unresolved initiating cause; they were not relabeled as passing runs. No WSL service settings were changed.

Local acceptance identifiers: `publication-validation-20261029-v2`, `fork-fu-study-20261029-v3`, `fork-gui-fu-capacity-20261029-v2`. Raw artifacts are deliberately excluded from Git.
