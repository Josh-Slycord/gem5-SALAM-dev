# Normalized GEMM header and wrapper generation

Qualified on 2026-11-06 America/New_York, after the native factory checkpoint
35e5459bb2. The native preparation path now derives address headers and its
full-system wrapper from normalized configuration. It does not invoke
SALAM-Configurator/systembuilder.py or produce a legacy topology module.

## One source-bound contract across phases

1. Preparation normalization explicitly permits not-yet-built IR. Such inputs
   are recorded as unbuilt without invented hashes. Header addresses, typed
   defaults, hardware settings, paths and source identities are validated.
2. The header renderer consumes that model, preserving custom text outside a
   single generated region. Macro names/values retain the existing ABI.
   Ambiguous regions and macro collisions fail instead of losing custom data.
3. Real guest and IR compilers consume the generated headers. Compiler
   preprocessor witnesses check the actual address values used by each source.
4. Strict normalization after compilation includes IR bytes. Its layout hash
   must equal the preparation hash; only build-derived IR content/size/state
   are excluded from the layout projection.
5. The wrapper renderer consumes the final model and the maintained board
   template as text. It preserves inherited license/board setup, removes
   generated-topology dispatch, fixes native-only selection and binds config,
   base, semantic model SHA and layout SHA. Conflicting CLI overrides fail.
6. Before constructing objects, the factory freshly normalizes sources and
   compares them with that binding. A saved model is evidence, never an
   independently trusted executable input.

The layout identity is tied to its workspace and source files. Moving inputs
or changing configuration/defaults requires regeneration. This is distinct
from the simulator's compiled-source identity.

Generation checks also pin frontend code, the selected template, runtime
request and copied adapters across preparation. Prepared wrapper bytes must
equal the normalized rendering plus the known runtime hook. Captured factory
receipts must contain all canonical source roles and the same normalized model.

The independent legacy structural/effective contract remains a verification
witness. It does not produce the native header or wrapper.

## Interfaces and selection

The normalizer retains strict runtime behavior by default:

~~~python
layout = normalize_configuration(config_path, engine_root, require_ir=False)
prepared_layout_sha = layout.layout_sha256
final = normalize_configuration(config_path, engine_root)
assert final.layout_sha256 == prepared_layout_sha
~~~

The current pure consumers are:

- native_codegen.render_headers(model, existing_headers=...) and
  header_symbols(model).
- native_wrapper.render_wrapper(final_model, template_text, model_path=...).
- native_generation preparation/finalization and artifact checks, used by
  the ordinary configurator pipeline when the JSON specification sets
  builder to native.

The existing [seed47 example](../experiments/native_gemm/seed47.json) uses
this path. Current C++ interfaces, zero-limit scheduling semantics and the
final native clock-binding boundary are retained.

## Reproduce the comparison

From the repository root, with the selected workspace/toolchain binding:

~~~sh
python workbench/scripts/run_native_generation.py --engine /path/to/independent-engine --build-receipt /path/to/verified-build.json --output /path/to/new-study --simulate
~~~

Without --simulate only a plan is saved. A debugging subset is available as
--case 10 0 1 --skip-negatives, or --relocation-only.

Retained and normalized preparation run in separate workspaces. Each builds
its own headers, guest and IR. Validation compares complete header macro maps,
actual compiler-visible addresses, byte-identical LLVM IR, and the ARM ELF
entry/machine/flags plus every loadable segment's address, size, permissions,
alignment and bytes. Debug information can differ because workspace paths
differ; full ELF file hashes are therefore recorded separately.

After load-image equivalence is established, both simulator processes execute
the native-built canonical guest ELF. This keeps the numerical comparison
strict while proving that the newly generated headers reached a real build.
Both paths run two different input fixtures, seeds 11 and 29.

## Results

All nine paired cases passed: 18 positive simulator processes, 36 launches and
2,304 observed output values checked independently with NumPy. The same two
fixtures repeat across settings; these are not 2,304 distinct input vectors.
Effective configuration, output bits, native clock/reset metrics and complete
FU event replay matched between paths.

The study covers the eight combinations of 10/3 ns, multiplier capacity
unlimited/1 and multiply latency 1/16 cycles, plus a relocated base of
0x10024000 at 3 ns/capacity1/latency16. In the relocation case, TOP becomes
0x10024040 and all nine address macros match the retained build and the actual
compiler inputs. The relocated simulation remains numerically correct.

All four compiler/runtime failure controls behaved as required:

- An intentionally wrong TOP macro is observed by the actual compiler and
  rejected by the model-address witness.
- A corrupt second-launch output is rejected independently despite green
  guest/runner pass labels.
- A modified saved model is refused before construction.
- A conflicting wrapper base override is refused before system construction.

The ordinary native JSON pipeline also passed its 64-value seed47 check while
the copied legacy system-builder file was unavailable. The builder was absent
from the staged workspace, never invoked, and restored unchanged afterward.
The captured factory model/binding matched preparation.

All 906 source tests passed: 352 fast, 490 configuration and 64 headless GUI.
Strict discovery exactly matches selected test IDs, with no skips, missing
tests or duplicates. Commit hooks and source-identity guards are additional
checks; the real simulation results remain separate evidence.

The simulator binary was reused byte-for-byte after source, toolchain and
Kconfig verification. Simulator C++ sources were unchanged and no simulator
rebuild is claimed.

The [machine-readable qualification](NATIVE_GENERATION_QUALIFICATION.json)
links the study, input/load-image proofs, failure controls, exact test
inventory and frozen implementation. Full raw evidence is kept outside Git:

- /home/jslycord/projects/salam-track-a-generation-20261106
- D:/kb_local_chatGPT/salam/track-a-generation-20261106

## Scope and next integration

This remains the qualified GEMM/NonCoherent-DMA/SPM/LocalBus slice. Generic
Params, native SCons profile generation, other topology/memory classes,
a stdlib board and native GUI selection require subsequent work. PPA remains
uncalibrated metadata.

Track B has not been merged here. The next integration input is a frozen
handoff with exact branch/base/head IDs, changed files, commands and raw test
receipts, unresolved issues and overlaps. Review it against this checkpoint
before merging into the active Track A branch. Qualified checkpoints and
official repositories remain outside the write scope.
