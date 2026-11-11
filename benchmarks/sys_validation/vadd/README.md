# Tiny VADD diagnostic

This new workload computes `c[i] = a[i] + b[i]` for signed 32-bit integers.
The historical `benchmarks/legacy/vadd*` sources are unchanged. This workload
has its own `vadd` IR entry point and full-output verification contract.

The default length is 8; supported lengths are 1 through 256. The fixture,
shared `VADD_LENGTH` define, host ELF, accelerator IR and DMA byte count must
agree. Inputs and sums must fit signed int32; overflow is rejected, not wrapped.
Each scratchpad has 1024 bytes of physical capacity by default, even when the
selected vector uses fewer bytes. A smaller configured memory must still fit
all selected elements. The study keeps the standard 4 GB simulated ARM
memory map for the linked bare-metal image; the vectors themselves stay tiny.
Three argument slots and the flag use 25 logical bytes;
the existing allocator reserves a 64-byte aligned top-level register window.

Use the Workbench pipeline to stage inputs and serializer headers before
building. Keep the GUI host and simulation engine in separate directories, as
in the installed Workbench layout: GUI staging must be outside engine sources. In the configured benchmark editor select `sys_validation/vadd`,
then choose length, dataset, seed or custom JSON arrays `a` and `b`. The
supported datasets are baseline, seeded, zeros, boundary and custom. The GUI
also selects file/UART output and optional human-readable input/result values.

Correctness checking is mandatory. The default file output keeps all observed
words in `simulator/salam-results.txt`. Explicit UART mode sends the same
complete protocol to `simulator/system.terminal`; it does not fall back from
failed file output. Verbose printing happens after the measurement dump.
The CPU stages inputs and a sentinel; it never computes expected values into
the observed output buffer. Every output word is checked outside the simulator.

From this repository's `workbench` directory, with its configured toolchain:

```sh
python -B scripts/run_vadd_diagnostic.py \
  --engine /absolute/path/to/engine \
  --build-receipt /absolute/path/to/configured-build/build.json \
  --output /absolute/path/to/new-study --simulate --include-max
```

Without `--simulate` the command only prepares/compiles workloads; that is not
a passing simulation. Output directories must be new. Existing failed runs are
retained. The study covers independent seeds, single/odd lengths, zeros, custom
signed edge values, explicit UART, and deliberately corrupted outputs. Its
forced guest-pass control succeeds only when independent checks reject the
wrong observed value despite the guest success marker.

Pre-launch witnesses inspect all three real compiler macro dumps, IR data
flow and loop bounds, DMA length writes, memory capacity and artifact hashes.
Real-run witnesses separately require completed SALAM lifecycle, actual add
activity, memory commits/bytes, and recorded binary/configuration identities.
NumPy verification uses saved input arrays and observed bits; it imports no
Workbench checker and does not trust a guest success string. Numerical success,
execution evidence and source-only tests are distinct results.

## Provenance

The DMA/SPM topology and ARM bare-metal scaffolding are adapted from
`benchmarks/sys_validation/gemm` at fork commit
`33d30bf6ef361b33a5bce8f06543e0acc10a0e5d`. Existing notices in the copied
boot/link/Makefile scaffolding are retained. Hardware-profile YAML was copied
from that same GEMM source; these coefficients are reused references, not new
measurements. The addition kernel, diagnostic fixture contract, bounds and
output controls were added for this diagnostic. Configuration and compilation
modify only independently staged workspaces; qualified engines and official
repositories are not working directories for this benchmark.
