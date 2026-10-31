# gem5 26: open gaps and qualification limits

Source-validation snapshot, 31 October 2026 UTC. The configured GEMM/FFT/stencil qualification is complete for the tested scope. The limitations and unresolved failures below remain explicit.

## Qualification and delivery status at this snapshot

1. **Six actual configured GUI positives have passed:** GEMM17/23, FFT17/23 and stencil17/23 each reached complete host numerical outputs and trace checks. Independent GEMM/FFT pairs, stencil17 replay and the explicit stencil23 bounded-process composite passed; the six-case aggregate binds 34,944 complete outputs with zero mismatches and 12 complete FU invocations. Two failed monolithic stencil23 audit attempts remain failed, so no one-process full-audit success or clean stability result is claimed.
2. **Stencil recovery lineage remains explicit:** the original sequential eight-worker fresh GUI build failed before simulation. Production `-j1` recovery passed with unchanged sources and preserved failed receipts. The unchanged strict sealer passed all normal gates and atomically published the verified marker. Both later GUI cases verified and reused that serial-recovered profile; neither is a successful fresh GUI rebuild.
3. **GUI rebuild worker control:** the CLI exposes `--jobs 1`; the GUI currently uses the default eight workers without an equivalent exposed control. A successful serial recovery does not make the original failed GUI build pass.
4. **False-pass controls cover all three families:** real forced-guest-pass runs were rejected by both numerical readers after normal native exit; copied real outputs were separately rejected by exact Qt widgets and independent NumPy readers after one changed value, with all original evidence preserved. Copied-output controls are not simulator reruns.
5. **Repository delivery is separate:** this source-validation snapshot was captured before branch publication. The upgrade remains separate from working main. Current commit, branch push, PR and hosted CI state belong to the PR checks and local delivery record. Official repositories remain untouched.
6. **Unexplained verification rejections remain unresolved:** first recovery publication rejected the base source binding; independent round 1 later rejected its binary binding. The exact mismatched values at the rejection points were not captured. Later unmodified production checks and native/stable binary reads agreed; two independent 9,860-file source rounds and loaded-code checks matched. The subsequent unchanged strict sealer passed every gate before publication. Those later successes do not assign a cause or erase the earlier failures.
7. **Native stencil23 audit aborts remain unresolved:** two monolithic audits aborted with `free(): invalid pointer`. All original gates subsequently completed in fresh bounded ordinary processes with actual normal return 0, and an explicitly labelled composite passed. Preserve the failed attempts and the successful phase receipts; do not call a failed monolithic process passed or infer a cause. No allocator flags, forced exits or suppressed aborts were used.
8. **Bounded environment observations are inconclusive:** the scoped Windows WHEA and recent Ubuntu kernel-pattern queries reported no matching entries. The first kernel query's unsupported flag is retained as an error; its supported correction returned no entries. These results do not rule out faults or establish a hardware, OS, RAM, WSL, filesystem, cache, allocator or code explanation.

## Limits that remain after the tested milestone

- Selected classic ARM full-system/SALAM paths and tested fixed benchmark shapes only. No claim of complete LLVM 14 instruction/intrinsic coverage, other ISAs, Ruby, checkpoints, distributed simulation, KVM execution or arbitrary topology support.
- The LLVM preflight catches specific known unsupported floating-point forms. It is a partial guard, not a complete instruction-support validator.
- The existing bare-metal request witness is partial even though actual workload type and other setting witnesses are recorded. Do not promote it to fully verified without a dedicated mapping/test.
- Legacy manually assembled/reference configuration routes remain explicitly guarded or lack full numerical qualification. Historical templates are not active modern GUI acceptance evidence.
- Stencil scalar `Ports=1` matches the accepted baseline. Multiport register-bank hardware is outside this port's implemented scope.
- GCC internal compiler failures have an **unproven cause**. One exact unchanged target passed serial retry; a later eight-worker stencil failure recurred with builds sequential. There is insufficient evidence to attribute this to RAM, WSL, source correctness or a compiler defect.
- The inherited bare-metal `_exit` noreturn/fall-through warning is a latent issue outside the exercised normal main-to-m5_exit path. Do not silently claim it fixed.
- Installed HDF5/PNG/Capstone packages did not enable those native features in the selected actual build. x86 KVM flags do not prove ARM/WSL KVM support.
- Power/energy figures are uncalibrated model estimates. No silicon measurements, calibrated process-node scaling or performance-generalization claim is established.
- Whole-guest gem5 statistics and accelerator invocation metrics have different boundaries. The current jointly changed CPU/FU/latency experiments do not isolate a causal speedup from one knob.
- Qt offscreen product tests exercise the actual GUI backend and Run flow, but do not replace a human review of the Windows shortcut, display, interaction or accessibility.
- The initial source-override ABI diagnostic and original FFT timeout with known unsupported IR constructs present (exact hang point unestablished) are preserved failures; neither counts as ordinary embedded numerical acceptance or a successful forced-pass control.
- Native PyStats 18 and two standalone C++ executable tests have their stated narrow scope. They do not represent the complete upstream gem5 regression suite.

The final independent composite and aggregate have been reviewed and indexed. Keep the original failed records and unresolved observations available; broader stability and coverage remain open. The Ubuntu 20.04 user-session startup warning is observed but not repaired or attributed by this port.

## CI follow-up: remaining scope and integrity uncertainty

The historical six-case simulation evidence remains bound to the original e587/900309 snapshot. A test-only source-identity transition and CI-profile correction were independently checked; all other identity inputs, four compiled-source inventories, private workspace and 159 historical artifacts remained unchanged at capture. Fresh 661-test outer coverage and a separate current-identity 64-output GEMM smoke passed; this does not rerun the historical six cases or establish broader stability.

Two additional native base hash reads differed from later matching native reads and retained copies. A subsequent completed byte comparison matched a retained copy without restoration or binary writes. The inconsistent observations and their unknown cause remain open. Do not describe them as established persistent on-disk modification/corruption or assign a host, RAM, filesystem or cache cause. The original compiler failures, transient binding failures and two native audit aborts remain preserved. Hosted results at the fixed follow-up head are separate from the completed local checks.
