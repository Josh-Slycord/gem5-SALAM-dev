# CI validation and its limits

The `Workbench source validation` workflow checks the maintained research
workbench against repository source. On the gem5 26 upgrade branch it contains
two source-validation jobs. Neither job builds or runs gem5, and neither creates
a simulator build receipt or a runnable engine binding.

## The two environments

| Job | Environment | Selection |
|---|---|---|
| `source-only` | Digest-pinned Ubuntu 20.04, Python 3.8 and the legacy dependency lock | Explicit recorded legacy command profile. Existing source-validation commands are retained. |
| `source-only-gem5-26` | Digest-pinned Ubuntu 24.04, isolated Python 3.12 venv and `.github/requirements-ci-gem5-26.txt` | Legacy-default command contracts are tested under Python 3.12. A separate generation step then selects the modern profile with explicit CI-local tool paths. |

The legacy profile used by unit fixtures is
`ubuntu20-llvm12-python38-armgcc9`. This preserves assertions about legacy
defaults without pretending that Python 3.8 tools are installed or simulations
are executed in the modern container. The subsequent modern generation fixture
selects `gem5-26-retained-salam`, its Python 3.12 venv, LLVM 14 paths and modern
build flags. The generator's recorded command must use that selected Python.

The workflow runs for pull requests targeting `main`, pushes to `main`,
`codex/ci-workbench-*` and `codex/gem5-26-*`, and manual dispatch. Dependencies
are installed only on ephemeral GitHub runners. The modern job records the
actual interpreter, OS, compiler, LLVM version, dependency input hashes and
installed Python package versions.

## What the workflow checks

- Checkout and artifact actions use full commit pins. Base containers use digest
  pins. Repository permission is `contents: read`; checkout credentials are not
  persisted. Source validation has no build cache shared with untrusted runs.
- An ignored `workbench/workspace.json` selects the checkout as a source-only
  fixture. A simulator binary and toolchain build receipt must be absent.
- Maintained Python, curated JSON and experiment YAML are parsed. The fast,
  config and offscreen GUI unit tiers must all pass without skips, failures,
  duplicate selection or unassigned tests. Their exact union is compared with
  independent unittest discovery, so newly added tests cannot silently escape
  the tier catalog.
- GEMM hardware generation runs in `$RUNNER_TEMP`, outside the checkout. All
  129 output hashes must match both the staged files and checked-in source.
  This establishes source generation and parity, not simulator execution.
- Scoped pre-commit checks cover maintained workbench code and documentation.
  Historical gem5/vendor style and archived workflow payloads remain outside
  that scope. The modern job additionally rejects tracked source changes and
  whitespace errors after validation.
- Receipts, generator logs and the generation witness are uploaded even if a
  later step fails. They are source-validation artifacts, not simulation output.

The Ubuntu 20.04 job uploads `workbench-source-validation`; the modern job
uploads `workbench-source-validation-gem5-26`. Start with
`workbench/evidence/ci/{fast,config,gui}.json`, `test-inventory.json`, and
`generation/generation-witness.json`. The modern artifact also contains
`environment.json`, `python-freeze.txt` and `toolchain-selection.json`.

The prior source-only fixture result at
`62536e9c98c3e8d2f0a1af8f8ca37847f233e78d` was fast 164, config 174 and GUI 14:
352 unit tests with no simulator binary or toolchain receipt. That is historical
Ubuntu 20.04/Python 3.8/Qt evidence. It does not establish the upgraded tree's
current test count or its hosted workflow outcome. Read each new Actions run's
own receipts for those results.

## Fork boundaries and historical workflows

The imported official gem5 workflows retain their source but every imported job
requires `github.repository == 'gem5/gem5'`. In this fork their schedulers,
publishing, issue/discussion responders, labelers and agentic maintenance jobs
therefore cannot execute. Source validation checks this boundary. Keep the
guards when updating upstream or regenerating agentic lock workflows.

The old scheduled nightly workflow is archived byte for byte at
[legacy-nightly-gem5-21.yml](../workbench/docs/ci/legacy-nightly-gem5-21.yml) on
the upgrade branch. It is outside `.github/workflows` and does not schedule
runs. It used generic unbound builds and benchmark pass strings; it did not
establish the upgraded SALAM engine's correctness. The preserved working
version on the old main branch remains separate.

The former [CI workflow](ci/legacy-ci.yml) and
[pre-commit configuration](ci/legacy-precommit-config.yaml) remain exact
historical before-images. That former Python job invoked gem5's internal
runner outside gem5 and ran zero workbench tests; its type-check job swallowed
failures. Historical triage recorded 1,031 whole-tree style findings and 24
mypy findings. The current scoped source gate does not claim to resolve
inherited whole-tree style debt or perform mypy checking.

## Real simulator acceptance is separate

Local acceptance needs a fresh SALAM-enabled simulator build whose receipt
binds the actual binary, compiler/LLVM toolchain and complete source inputs.
It then needs real GEMM, FFT and stencil simulations, independent full-output
numerical oracles, deliberately rejected wrong-output controls, and replayed
FU scheduling evidence. GUI regeneration/rebuild and effective configuration
witnesses must demonstrate that requested settings reach those simulations.

Standalone C++ scheduling/collector tests verify synthetic component behavior;
source capability markers declare hash-matched implementation support. Neither
is a replacement for compiled runtime evidence. A successful source-only CI
run must never be reported as a successful gem5 simulation or port validation.
