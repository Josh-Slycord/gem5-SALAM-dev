# SimObject lifecycle validation: 7 November 2026

The isolated `codex/simobject-lifecycle-20261107` branch adds real drain,
callback-order and retry-statistics fixes on qualified source
`1f4e6225dc04d305bdf2a2be424fab029d471d4e`. The qualified checkpoint is
preserved. This is a fork validation record, not an upstream submission.

## Verified outcomes

| Gate | Result |
| --- | --- |
| Real lifecycle/protocol suite | 15 successful simulations and 5 intentional rejections, each with its specific cause |
| Independent accelerator restart | Two invocations per actor; A restarts while B is active, then B restarts while A is active; all four fresh outputs checked |
| Preserved pre-fix binary | Four targeted failures reproduced; already-healthy RegisterBank response-retry case passes |
| Ordinary product build | Successful configured build without SALAM tester SimObjects; actual SimObject inventory checked |
| GEMM retained/native generation | Nine paired configurations, 18 successful simulator processes, two distinct guest launches per process |
| GEMM rejection controls | Four controls: compiler-visible wrong header, false guest pass, model tampering and CLI base override |
| Sanitized helper binary | 30 production-helper GTests; ASan, UBSan and checked STL |
| Source-only test tiers | 953 independently discovered tests; fast: 386; config: 503; gui: 64; zero failures, errors or skips |
| FU capability | Current LLVM consumer hashes; successful configured-build binding; fail-closed guard retained |
| Protected inputs | Three source checkouts clean at their original heads; protected main/branch/tag unchanged; two preserved binary hashes and 72 package members plus manifest verified |

The core lifetime outputs are A1 `23`, B1
`32640`, A2 `130833`, B2 `120`.
The host computes them independently using Python sums. Previous and current
captured graph handles expire separately; B2 finishes while A2 is still active.
Native invocation counters are two per actor, with four fresh write responses.
Output bytes are removed before each launch so a stale result cannot qualify.

The GEMM study independently generates both layouts, compares complete
compiler-visible address macros, IR and ARM ELF load images, then compares
full effective configurations, complete numerical outputs, native reset
windows, timing and FU grant/release replays. Its finite-capacity cases
require actual denials and bounded occupancy, and its unlimited cases
require no denials. The false-pass control deliberately leaves the guest and
runner green while independent numerical comparison rejects the output.

## Executable identities

- Tested opt-in lifecycle binary: `5cba63c51258ec719c256868c2b90b28f369fde0fb7af8120d04cb680dfa06b3`.
- Preserved pre-fix control binary: `03b9af4546188dcd76dd04007526b0af024b424cbf309dc7625e602541400a3e`.
- Ordinary product binary: `41a3717a4b8f71dd7004d1693aa27909b8ff1c41c54f9301481bcaf764923cfe`.
- Ordinary product compiled-source fingerprint:
  `306ee4d0f85734d91be1af1d71b144a9f869dfd1e5843ac5b065abee37a7dfa3`.

The exact C++ and embedded SimObject inputs of the opt-in build still match
its build snapshot after the external source-capability metadata refresh.
Both final lifecycle matrices hash their source inputs and actual binaries
before and after execution. Each process has its own PID, command, return
code, raw stdout/stderr, configuration witness and result receipt.

## Reproduce and inspect

Use Python 3.12 and the selected modern gem5 26 / LLVM 14 workbench profile.
The [lifecycle suite documentation](SIMOBJECT_PROTOCOL_TESTS.md) gives the
opt-in build command, normal suite and pre-fix reproduction mode. After the
normal build is selected in an initialized modern workbench:

```sh
PYTHONPATH=workbench python -m salam_workbench.configurator build \
  --engine "$PWD" --evidence-dir workbench/evidence/lifecycle-product-build
python workbench/scripts/run_native_generation.py \
  --engine "$PWD" \
  --build-receipt workbench/evidence/lifecycle-product-build/build.json \
  --output ../salam-lifecycle-evidence/gemm-generation --simulate
python workbench/scripts/verify_native_helpers.py \
  --output workbench/evidence/lifecycle-helpers --generated-headers build/ARM
```

All evidence directories must be new. GEMM staging must be outside the source
checkout. Raw outputs remain in ignored or separate local
storage, rather than Git. In this validation checkout they are:

- `workbench/evidence/lifecycle-final-v2/matrix.json`.
- `workbench/evidence/lifecycle-baseline-final-v2/matrix.json`.
- `workbench/evidence/production-build-v2/build.json` and `source-inputs.json`.
- `/home/jslycord/projects/salam-lifecycle-validation-20261107/gemm-generation-v2/study.json` and its
  per-case numerical/configuration/FU/generation comparisons.
- `workbench/evidence/lifecycle-native-helpers-v2/validation.json`.
- `workbench/evidence/lifecycle-source-fixture-v4/workbench/evidence/ci/`.

The Windows task record is
`D:/kb_local_chatGPT/salam/simobject-lifecycle-20261107/VALIDATION_SUMMARY.json`.
It preserves these identities, protection checks, independent discovery
counts and the observed restart results. Earlier unsuccessful attempts are
retained separately; they are not counted as qualifying runs.

## Remaining scope

Drain quiescence is not checkpoint serialization/restore qualification.
Automatic full-simulator TestLib/CI registration remains follow-up work.
Captured per-instance graph destruction is not whole-engine sanitizer or
leak-freedom proof. DMA, stream and SPM-specific protocols remain open for
real end-to-end validation. The 64 GUI cases are source/offscreen tests;
this patch does not claim a new FFT/stencil GUI rebuild qualification.
Physical PPA calibration, licensing and other historical upstream gates
remain as recorded in the [readiness register](UPSTREAM_READINESS.md).
