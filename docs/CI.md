# CI validation and its limits

The `Workbench source validation` workflow validates the maintained research workbench against repository
source. It runs on GitHub's Ubuntu runner inside a pinned Ubuntu 20.04 container.
The job installs Python 3.8 dependencies into that **ephemeral container's system
interpreter**, which is the interpreter used by the workbench's subprocesses. It
does not install software on a contributor's machine.

## What the workflow checks

- It checks out the triggering revision with read-only repository permission and
  without persisted Git credentials. The checkout and artifact actions use full
  commit pins; the Ubuntu container uses a digest pin.
- It creates an ignored `workbench/workspace.json` that selects the checkout as a
  **source-only fixture**. It requires the simulator binary and toolchain receipt
  to be absent. The fixture is never presented as a runnable engine.
- It parses maintained Python, curated JSON, and experiment YAML; then runs the
  workbench's fast, config, and GUI unit tiers. Every selected test must pass,
  with no skip, failure, duplicate selection, or unassigned test file.
- It generates GEMM hardware source in `$RUNNER_TEMP`, outside the checkout. A
  witness checks all 129 generated outputs against their saved hashes and the
  checked-in source bytes. This is a generation and source-parity check; no
  simulator is compiled or run.
- It runs scoped pre-commit checks on maintained workbench code and documentation.
  Vendored GUI code, frozen regression overlays, archived patches, and historical
  gem5 files are outside that style scope. JSON/YAML/Python parsing failures are
  real failures. The workflow does not claim mypy type checking.
- It uploads the unit receipts and generation witness even when a later step
  fails. The artifact retains source-validation evidence, not simulator output.

The source-only fixture was tested locally at revision
`62536e9c98c3e8d2f0a1af8f8ca37847f233e78d`: fast 164, config 174, GUI 14,
and all 352 unit tests passed with no simulator binary or toolchain receipt. That
local result establishes feasibility for the recorded Ubuntu 20.04/Python 3.8/Qt
environment. The hosted workflow result is separate and must be read from its own
GitHub Actions run.

## What remains outside CI

The verified local FU capacity study, negative controls, and actual GUI-driven
simulations have their own saved receipts. This source-only job does not reproduce
them. A future simulator CI gate needs a fresh build with a bound toolchain and
source-input receipt, actual guest and simulator runs, numerical oracle checks,
and deliberately rejected wrong-output controls.

The old [CI workflow](ci/legacy-ci.yml) and
[pre-commit configuration](ci/legacy-precommit-config.yaml) are retained exactly
as historical before-images. The former Python job invoked gem5's internal runner outside gem5 and ran zero workbench tests. Its warning-only type-check job swallowed failures. The whole-tree formatter mixed legacy, vendor and maintained source scopes. Local triage also
recorded 1,031 whole-tree style findings and 24 mypy findings; the maintained workbench Python has now been formatted with pinned Black/isort settings. Inherited gem5/vendor style debt and unresolved type-check findings remain outside this scoped gate. The separate scheduled `nightly.yml` full-build workflow
is unchanged and has not been validated under this contract.

To inspect a run, start with the three `workbench/evidence/ci/{fast,config,gui}.json`
unit receipts and `generation-witness.json` in the `workbench-source-validation`
artifact. Compare the hardware generator's `hardware-codegen.json` with the
checked-out revision; it records source and staged output hashes.
