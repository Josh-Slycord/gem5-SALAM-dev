# Native GEMM configuration and direct factory

Status: first native configuration slice, qualified on 2026-11-05
America/New_York. Protected source, checkpoint, runtime and official
repositories are outside this change.

## Implementation and contracts

The side-effect-free normalizer reads topology/hardware YAML and the current
typed SimObject declarations using AST, without importing m5 or executing a
generator. Its deterministic model records source file/line, key paths,
explicit/default/derived origins, resolved addresses, requested hardware
overrides and dependency hashes. ConfigurationError preserves the authored
location and a diagnostic code.

The factory creates clusters, noncoherent DMA, accelerators, scratchpads and
port connections from this model. It retains the typed C++ FU/instruction
interfaces and HWAccConfig consumers. Logical runtime_cycles reaches
CycleCounts; FU limits reach the existing pooled scheduler. Native clock
translation remains at Simulation.run's final override boundary.

The supported entry is native_factory.makeHWAcc. Each launch freshly
normalizes source inputs. Saved JSON is evidence, not a serialized executable
configuration; construction helpers are private.

This slice admits one cluster, NonCoherent DMA, CommInterface accelerators
and SPM, with LocalBus-only PIO. Unsupported ConfigPath, stream/cache/bank
devices, named PIO networks, unknown/duplicate keys, unsafe paths, opcode
remapping, nonzero instruction caps and unsupported special-op timing/FU
requests receive explicit pre-instantiation errors. SPM vector connections
retain their requested cardinality.

FU limit zero means unlimited. Instruction-cap zero is neutral and does not
bypass a finite FU cap. Characterization period is separate from actual
runtime clock. PPA coefficients remain uncalibrated metadata.

## Select the native builder

Native selection is available through the configuration JSON/CLI:

~~~json
{
  "schema_version": 1,
  "name": "native_gemm_seed47",
  "benchmark": "benchmarks/sys_validation/gemm",
  "builder": "native",
  "base_address": "0x10020000",
  "benchmark_input": {"dataset": "seeded", "seed": 47},
  "correctness": {"expected_passed_markers": 1}
}
~~~

A runnable example is
[experiments/native_gemm/seed47.json](../experiments/native_gemm/seed47.json).
From workbench/, with its workspace/toolchain binding configured:

~~~sh
python -m salam_workbench.configurator run --engine /path/to/independent-engine --build-receipt /path/to/verified-build.json --spec experiments/native_gemm/seed47.json --evidence-dir /path/to/new-native-run
~~~

Omitting builder selects the retained generated route. The host stages the
normalizer and passes --salam-builder=native, --salam-config and
--salam-base-address. Arbitrary system options cannot override these managed
fields.

Native preparation now generates headers and the full-system wrapper from
the normalized model, with layout checks across compilation and a verified
runtime snapshot binding. See [normalized generation](NATIVE_GENERATION.md)
for the newer nine-case qualification. The first factory-only study below
remains preserved as its earlier checkpoint.

The pure model is usable independently:

~~~python
from salam_workbench.native_config import normalize_configuration

model = normalize_configuration(
    "/path/to/engine/benchmarks/sys_validation/gemm/config.yml",
    "/path/to/engine",
)
document = model.to_dict()
canonical_json = model.to_json()
semantic_sha256 = model.sha256
~~~

IR files must exist inside the engine root. Their bytes are fingerprinted;
LLVM syntax/semantic acceptance remains the C++ loader's responsibility.

## Reproduce and independently check

From the repository root:

~~~sh
python workbench/scripts/run_native_gemm.py --engine /path/to/independent-engine --build-receipt /path/to/verified-build.json --output /path/to/new-study --simulate
~~~

Without --simulate only a plan is saved. --case PERIOD_NS FU_LIMIT MUL_CYCLES
selects a debugging subset. Default qualification covers eight combinations:
period 10/3 ns, capacity 0/1 and multiply latency 1/16 cycles. Every process runs
two distinct fixtures (seeds 11/29) with native statistics reset/dump around
each launch.

Within each retained/direct pair, binary, ELF, IR and workspace are identical.
Checks cover all effective config.ini fields/peers, all 128 output values per
process against independent NumPy int64 GEMM with exact int32 bits, native
clocks/reset windows, memory/commit metrics, elapsed ticks/compute passes
and complete FU admission/release event replay. Only children ordering and
content-identical input paths may normalize. Guest/run pass flags are ignored.

Three actual controls are required: corrupt second-launch output while the
guest prints Check Passed, a nonzero instruction-cap rejection, and malformed
IR rejected by the C++ module reader.

Saved pairs can be checked independently:

~~~sh
python workbench/scripts/verify_native_gemm.py --retained-run /path/to/generated-run --direct-run /path/to/native-run --fixture /path/to/fixture-1.json --fixture /path/to/fixture-2.json --expected-period-ns 10 --expected-mul-limit 1 --expected-mul-cycles 16 --receipt /path/to/new-comparison.json
~~~

## Factory-only qualification (2026-11-05)

All eight pairs passed: 16 positive simulator processes, 32 launches and 2,048
observed values checked. Each setting repeats the two input fixtures; these
are not 2,048 distinct inputs. Effective settings, numerical results, selected
native metrics and event replay matched between builders. All three actual
negative controls passed their expected rejection checks.

A separate ordinary native JSON/CLI run with seed 47 passed its 64-value
oracle. All 805 source tests passed: 352 fast, 389 config and 64 headless GUI.
Strict discovery equals the union of selected tests, with no duplicate or
missing IDs, skips, failures or errors.

The simulator binary was copied byte-for-byte from the qualified runtime.
Source/build/Kconfig/toolchain identities were verified. Simulator C++
sources and typed interfaces were unchanged; no new simulator build is claimed.

First-invocation witnesses, identical on both builders:

| Clock ns | FU capacity | Mul cycles | Peak occupancy | Denied attempts | Compute passes |
| --- | --- | --- | --- | --- | --- |
| 10 | unlimited | 1 | 8 | 0 | 337 |
| 10 | unlimited | 16 | 8 | 0 | 1055 |
| 10 | 1 | 1 | 1 | 100184 | 839 |
| 10 | 1 | 16 | 1 | 100184 | 8207 |
| 3 | unlimited | 1 | 8 | 0 | 337 |
| 3 | unlimited | 16 | 8 | 0 | 1055 |
| 3 | 1 | 1 | 1 | 100184 | 839 |
| 3 | 1 | 16 | 1 | 100184 | 8207 |

Each launch grants/releases 512 multiplier leases and ends with zero
occupancy. Denials are retry attempts, not stall-cycle counts. Capacity
changes observed peak overlap from 8 to 1. Changing latency 1 to 16 changes
compute passes from 337 to 1,055 at unlimited capacity.

The [machine-readable summary](NATIVE_GEMM_QUALIFICATION.json) links raw
evidence and frozen source. Full results remain outside Git:

- /home/jslycord/projects/salam-track-a-native-20261105
- D:/kb_local_chatGPT/salam/track-a-implementation-20261105

Earlier development/smoke attempts remain preserved and are excluded from
the final positive-case counts.

## Remaining scope

Generic Params, native SCons profile generation, a stdlib board, normalized
offline consumers, additional device/topology types and a GUI builder
selector remain subsequent slices. This qualification does not establish
calibrated PPA, whole-engine leak freedom, forced backpressure or drain coverage.
