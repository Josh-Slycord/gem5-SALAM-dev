# gem5 26 Workbench checkpoint - 5 November 2026

Tag: **gem5-26-checkpoint-20261105** on the separate gem5 26 upgrade branch.
This integrates and repairs [PR #3](https://github.com/Josh-Slycord/gem5-SALAM-dev/pull/3)
while preserving its original commit/authorship and the working main version.
It is a tooling checkpoint, not a claim of upstream readiness or physical accuracy.

## What works at this checkpoint

- Results exports a selected hash-verified functional-unit trace in a worker.
  Full event replay and exact parsed-byte hashing precede HTML generation.
  Floating-point/custom units and more than eight lanes remain visible.
- Truncated, inconsistent, unmatched, duration-invalid and changed-source
  traces fail. Large HTML exports explicitly label their bounded preview.
- The explicit-request GEMM command uses the same staged generation/build/run
  and independent results gate as the GUI. Export success is not numerical success.
- Existing-engine bootstrap preserves and verifies the modern toolchain.
- Windows packaging controls cover arguments, failures and source identity.
  The appliance recipe records exact committed sources and refuses replacement.

## Qualification

705 local tests pass: 352 fast, 289 configuration and 64 GUI.
Independent discovery matches exactly; there are zero skips or duplicate tests.
The exporter has 30 dedicated positive/negative tests. Regeneration produced
129 files matching the checked-in generated sources.

Hosted source CI passed all three jobs at the recorded code commit:
[run 42061923990](https://github.com/Josh-Slycord/gem5-SALAM-dev/actions/runs/42061923990).
Source CI is separate from these local real-simulator cases.

Each fresh GUI case used seed 31, applied settings through the actual Run
button, completed independent output checks, and exercised the actual Results
timeline button/worker. A second standalone NumPy checker compared every output.

| Benchmark | Complete numerical outputs | FU events replayed for timeline | Spans rendered / total |
| --- | ---: | ---: | ---: |
| gemm | 64 | 41,264 | 2,176 / 2,176 |
| fft | 1,024 | 149,558 | 20,000 / 70,682 |
| stencil3d | 16,384 | 2,112,201 | 20,000 / 205,362 |

FFT and stencil use regenerated/rebuilt profiles; final checked-cache reuse is
explicit in their raw receipts. The earlier FFT acceptance attempt was retained
but excluded because source changed during its run. Final selected acceptances
require unchanged source. A separate configured GEMM CLI run also passed.

Two derived breadth controls retained the guest pass and refreshed transport
hashes after changing one numerical output. The production reader and actual
GUI rejected each for exactly one mismatch. Original accepted files stayed intact.
These controls are derived-data tests, not additional simulator runs.

## Disabled or retained deliberately

- **Disabled appliance workspace fabrication and readiness claim:** those steps
  supplied no genuine build/generation receipts or installed GUI adapter.
- **Disabled ad-hoc benchmark compilation/direct-generator shortcut:** it
  bypassed supported generator repairs, ARM SDK selection and output checking.
  The root GEMM helper now requires an explicit generated-input request.
- **Deduplicated exporter:** the Docker path delegates to one maintained implementation.
- **Retained legacy power/cycle-tracking SimObject scaffolds:** this checkpoint
  documents their inactive/incomplete paths rather than removing public object
  shapes or implying they produce native metrics. Existing invocation/FU JSON
  remains the implemented observability route.

## Limits and next milestone

The Docker image has not been built/imported/qualified on a clean host.
Windows-to-WSL inspection passed; GUI captures are Qt offscreen, and the external
browser opener was suppressed during automated button acceptance. Local HTML
browser rendering was blocked by URL policy; static JavaScript syntax passed.
Power/area parameters remain uncalibrated model inputs.

[UPSTREAM_READINESS.md](UPSTREAM_READINESS.md) maps 20 concern areas to the actual
review of gem5 PR #2429, retaining 132 thread statuses. Resolved upstream threads
are not proof that this fork has equivalent fixes. Next work begins with targeted
engine correctness/support-boundary tests, followed by native statistics/ROI,
ports/clocks/lifecycle, configuration components and optional research integrations.
No next milestone or official upstream submission was started here.

Historical GCC failures, inconsistent native binary hash observations and
monolithic audit aborts remain recorded in [known gaps](GEM5_26_KNOWN_GAPS.md).

## Reproduction and provenance

See [execution visualizer](EXECUTION_VISUALIZER.md), [appliance recipe](../../docker/README.md)
and the [machine-readable checkpoint](CHECKPOINT_2026-11-05.json).
The JSON records selected local receipt paths, hashes and the exact tooling
identity. Raw runs, simulator binaries, variants, bindings and generated HTML
remain local/ignored. Official repositories and main were untouched.
