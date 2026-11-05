# SALAM functional-unit trace viewer

The standalone HTML viewer presents the direct SALAM scheduler event stream.
It is an inspection tool for modeled functional-unit leases. A successful
export establishes complete, internally consistent scheduling evidence for
that source file; it does not establish benchmark numerical correctness,
physical RTL timing accuracy, or calibrated power. Keep the Workbench's
independent numerical checks, effective-configuration witnesses and original
raw output alongside each view.

The Docker/WSL appliance has its own instructions in [docker/README.md](../../docker/README.md).
Build support and clean-host acceptance are separate from viewer acceptance.
The original PR's reported build timings, guest pass marker and 110 tests
are historical claims, not a new acceptance result for every benchmark.

## Export an existing trace

From the repository root:

```sh
python3 workbench/visualizer/export_salam_visualizer.py \
  /path/to/observability/fu-scheduling-accelerator.invocation-1.json \
  /path/to/viewer.html --max-spans 20000
```

The optional `--expected-sha256 HASH` binds the input to an existing Workbench
artifact record. The command returns nonzero on invalid input or a mismatched
hash and writes no new dashboard in those cases. It prints JSON containing
source path, bytes, SHA-256, full replay count, and preview coverage. The
library equivalent is:

```python
metadata = export_trace(
    trace_path, output_path, max_spans=20000,
    expected_sha256=recorded_artifact_hash,
)
```

`docker/export_salam_visualizer.py` is a compatibility entry point to the
same implementation. It deliberately contains no second renderer. The old
hardcoded personal WSL paths have been retired: callers must supply the
actual trace they intend to inspect. Output must be HTML and cannot replace
the source trace.

## Evidence contract

The input must be direct `salam_fu_scheduling` schema version 1, not a witness
summary. The exporter streams the JSON trace, replays every event, and requires:

- An explicitly untruncated trace and valid declared event budget.
- Unique declared FU IDs/names, unsigned counters and invocation bounds.
- Monotonic cycle/tick order and increasing, unique grant lease IDs.
- A first-to-last event tick span within the declared invocation elapsed ticks;
  absolute tick values may have a nonzero simulation origin.
- Identity-matched releases with no outstanding grants at completion.
- Capacity-respecting grants and denials only when a positive cap is full.
- Exact agreement of all per-unit and global counters with event replay.

Duplicate JSON keys, malformed objects and input changes during replay
are rejected. SHA-256 is computed from the same binary stream being decoded,
with incremental UTF-8 decoding. Stable file-descriptor identity, inode, change
time, size and modification time are checked; a same-size atomic replacement
with a restored modification time cannot substitute a second file for hashing. The input budget is 512 MiB and 4,194,304 events, matching the
maximum current scheduler trace budget. A decoded non-event JSON value is
limited to one MiB. These are refusal limits, not silent truncation.

This replay is an exporter safety check. The existing independent Workbench
FU replay and numerical checker remain separate acceptance gates.

## What the display means

Track IDs and names come from the validated trace. Floating-point, double
precision and unfamiliar future functional units remain visible. A limit of
zero means **unlimited**, preserving the current SALAM scheduling contract;
it does not infer static hardware instances.

Each lane depicts one non-overlapping lease interval `[grant, release)` in
modeled accelerator cycles. A release and regrant on the same boundary may
reuse a lane. A zero-duration lease is a marker, never a fabricated cycle.
All lane indices are distinct, including beyond eight simultaneous leases.
The full event-order peak can exceed the cycle-boundary occupancy: multiple
ordered grant/release events can occur within one displayed cycle.

Ticks are labeled as ticks. This FU schema does not itself declare the tick
frequency, so the viewer does not assume picoseconds or convert to seconds.
Tick and instruction/lease identities are preserved as strings where needed
to avoid JavaScript integer precision loss.

To keep large stencil outputs usable, full replay and rendering are separate.
By default, the first **20,000 completed spans** are retained for the browser;
`--max-spans` accepts 1 through 100,000. The header explicitly reports rendered
and total span counts. The occupancy curve and active-operation display cover
those preview spans only. The unit summary and event-order peak come from the
complete replay. A limited preview must never be described as the entire
execution timeline. Raw JSON remains the complete source of detail.

HTML data is JSON-escaped before embedding, and trace names are escaped before
insertion into rich markup. No network dependency or external script is
required by an exported dashboard.

## Checkpoint validation

The focused regression suite covers invalid/truncated input, counter and lease
tampering, floating-point and future FU IDs, twelve concurrent lanes,
release/regrant boundaries, zero-duration markers, bounded previews, chunked
input, source hashing, HTML injection and the Docker compatibility entry point:

```sh
cd workbench
python3 -m unittest discover -s tests -p test_execution_visualizer.py -v
```

Real preserved GEMM, FFT and stencil GUI traces are also replayed and exported
at the integration checkpoint. Their raw SHA-256 values and coverage metadata
are retained in the checkpoint evidence; export success is not represented as
a new simulator or numerical test run. The root checkpoint record carries the
combined source, GUI and numerical validation results.
