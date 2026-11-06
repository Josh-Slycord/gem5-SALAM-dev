# First implementation slice after the Track A audit

This is the prioritized implementation handoff, not completed functionality.
The completed source audit is indexed in README.md and its machine records.

## A1: A normalized model with faithful compatibility

Create a side-effect-free parser with source locations, explicit/default
origins and a versioned normalized representation. Start with the qualified
GEMM topology and hardware profile. It must not import a legacy generator
that overwrites tracked source while importing a module.

Use the pinned PR #2429 parser/factory as a structural reference. Reconcile
our audit records field by field; copying its FU capacity or pipeline
semantics would change the experiment. Preserve our typed-wrapper adapter
until a generic-Params engine migration is independently qualified.

Deliverables:
- Normalized GEMM model and a consumer-status report for each requested field.
- Legacy-to-normalized adapter plus explicit path, address, IRQ and port rules.
- Duplicate, unknown, wrong-device, malformed, unsupported-cap and unsafe-path
  diagnostics that cite the original YAML file/line.
- Deterministic serialized model and dependency hashes usable by the build
  receipt and by the later header/offline consumers.

Acceptance evidence:
1. Load the pinned qualified GEMM config without changing any source or binary.
2. Compare normalized explicit/default fields to the current staged builder;
   explain every difference rather than blessing a serialized golden file.
3. Demonstrate that each deliberately unsupported request fails before a run.
4. Preserve instruction runtime_cycles=0 and neutral instruction-cap=0 while
   preserving finite FU capacity. Test all three separately.

## A2: A direct GEMM factory, alongside the retained builder

Instantiate the model directly in an isolated engine/build directory, with
no new writes into the qualified source or runtime. Keep the old path
available. Declare exactly which SALAM/gem5 objects, address ranges,
interfaces, queues and memory edges are created.

First compare structure and effective Params. Then run real GEMM using
independent numerical output validation, including a known corruption
control. A simulation exit or a green GUI result alone is insufficient.

Required differential matrix:

| Dimension | Minimum comparisons |
| --- | --- |
| Builder | retained generated Python vs new direct factory |
| Clock | 10 ns and 3 ns, effective native domain checked |
| FU capacity | unlimited 0 and at least one finite bottleneck |
| Latency | default and changed logical instruction runtime_cycles |
| Launch lifecycle | two invocations, distinct known inputs |
| Failure controls | nonzero instruction cap, malformed IR, corrupted output |
| Evidence | source/binary/config receipts; complete run IDs and oracle results |

Check effective configuration and bounded FU event traces alongside
numerical results. Preserve grant/release balance, reset/dump consistency,
cycle/tick reconciliation and per-launch finalization behavior. Do not use
one timing total alone as proof a setting reached the scheduler.

After this matrix passes, extend through the actual Workbench GUI to FFT
and stencil; compare requested, normalized and effective settings and run
their existing independent numerical checks. GUI run history must point
to the exact receipt and oracle evidence.

## A3: Native SCons generation and a smaller upstream candidate

Move profile generation to declared build-tree targets, opt-in with SALAM.
Record input, generator and output identities, including the current
codegen patches, and test rebuilding after one relevant YAML change.
Irrelevant input must not force source mutation.

Prove a default no-SALAM build succeeds without LLVM installed or selected.
Separately prove the supported SALAM build/toolchain. Validate explicit
LLVM major selection; discovery candidates are not a support matrix.

Only after A1/A2 qualification should common FU/instruction Params replace
the current named-wrapper ABI. Port the qualified scheduling/stats/clock
behavior deliberately. Do not merge the full historical repository into
upstream develop: select an auditable core, factory, build and test slice.

## Work kept separate

Josh assigned Gemini B1 and B3. Consume its bounded-write and provenance
results as reviewed changes, retaining source attribution and tests.
Licensing questions remain open until obligations are established; this
audit is not a legal conclusion. Full memory backpressure/bypass/drain,
RegisterBank port cardinality, graph lifetime and whole-engine sanitizer
qualification remain separate test work. No finding here grants those
capabilities merely because Params exist.

The original integration tag, protected runtime, main branch and official
repositories are outside the write scope of these slices.
