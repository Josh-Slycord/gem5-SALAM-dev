# Experimental Docker-to-WSL2 appliance

This recipe packages a specific committed SALAM source tree and builds its
simulator. **A clean-host Docker build, WSL import, GUI launch and independent
numerical acceptance have not yet been established for this recipe.** The
existing validated installations remain the supported local environments.
This checkpoint fixes source identity and launch contracts; it does not certify
an appliance release.

## What changed from the initial PR

- The image uses one exact `git archive` snapshot, including its Workbench and
  visualizer. It no longer clones an older commit and silently patches scripts.
- Build jobs, base image, source revision, artifact directory, distribution name
  and installation directory are explicit parameters.
- Every native command failure stops the PowerShell workflow.
- No existing distribution is unregistered, replaced or modified. Existing
  exports are never overwritten. The stopped export container is retained.
- The image records package versions, simulator SHA-256 and build information.
  The host manifest records the source commit/archive hash, image identity and
  rootfs hash. This is provenance, **not bit-for-bit reproducibility**: the
  default base tag, Ubuntu apt repositories and transitive Python dependencies
  are mutable. A digest-pinned base and controlled dependency mirror/lock are
  additional release requirements.
- The hand-written workspace and ad-hoc GEMM compilation are disabled in the
  Dockerfile with comments explaining why. They bypassed verified receipts,
  GUI adapter installation and the supported generation/ARM SDK flow.

## Build and export

Requirements: Docker with a working Linux engine, Git, PowerShell and enough
space on the chosen artifact disk. Use a clean committed source tree. The
context archive, image build and exported filesystem can be large; no timing
or disk-size guarantee is made.

Run from a Windows clone or WSL UNC checkout, supplying your own destination:

```powershell
.\docker\build_gem5_wsl.ps1 -SourceRoot "D:\your-source-checkout" -ArtifactRoot "E:\salam-appliances\checkpoint-1" -Commit HEAD -Jobs 2
```

Only committed tracked files are archived. The Dockerfile is read from that
same commit. The packager rejects gitlinks because a plain archive does not include their
submodule contents. This repository currently vendors SALAM's LLVMRead files;
check future submodule additions before packaging.

For stronger environment identification, pass an independently checked base
digest instead of the mutable default `ubuntu:22.04`:

```powershell
# Supply a real digest from the intended platform; this is a placeholder.
# -BaseImage "ubuntu@sha256:<verified-linux-amd64-digest>"
```

This example is intentionally commented out: no image digest was verified by
this checkpoint. The default is a build convenience, not a frozen release.

## Optional new WSL installation

Import is opt-in and requires a new destination. It never unregisters anything:

```powershell
.\docker\build_gem5_wsl.ps1 -SourceRoot "D:\your-source-checkout" -ArtifactRoot "E:\salam-appliances\checkpoint-1" -Commit HEAD -SkipBuild -SkipExport -Import -DistroName "gem5-salam-checkpoint-1" -WslInstallDir "E:\wsl-instances\gem5-salam-checkpoint-1"
```

The default Linux account is `salam`. Simulator sources/binary are under
`/opt/salam/engine`, package/build records under `/opt/salam/provenance`, and
a separate Workbench copy under `/home/salam/workbench`. No passwordless sudo
rule or systemd startup dependency is installed. WSLg support depends on the
host's WSL installation.

Docker environment variables are not carried into a `docker export` rootfs
as WSL process defaults. The launch script selects paths explicitly.

## Bind and launch the GUI

The copied Workbench intentionally has **no fabricated `workspace.json`**.
Use the supported [existing-installation bootstrap](../workbench/README.md#bind-an-existing-installation)
with actual build/generation receipts and install its checked GUI adapter.
Producing and validating those receipts inside this new appliance is an open
clean-environment acceptance task. Do not copy receipt identities from another
binary or source tree.

After binding:

```powershell
.\docker\launch_workbench.ps1 -Distribution "gem5-salam-checkpoint-1" -WorkbenchRoot "/home/salam/workbench" -Inspect
.\docker\launch_workbench.ps1 -Distribution "gem5-salam-checkpoint-1" -WorkbenchRoot "/home/salam/workbench"
```

The launcher reads the selected Python interpreter from the real workspace
profile, propagates failures and accepts an optional `-Benchmark`. Missing
bindings fail clearly; this launcher never starts a simulator by itself.

## Release acceptance still required

1. Build/export on a clean host; retain source, dependency and image manifests.
2. Import into a new WSL name and disk path; verify the simulator hash.
3. Produce genuine generation/build receipts, install GUI hook and bootstrap.
4. Launch/inspect the actual GUI, apply settings and exercise regeneration/build.
5. Run GEMM, FFT and stencil with independent numerical and FU replay checks,
   including deliberate wrong-output and truncated-trace controls.
6. Validate WSLg visibly and record license/redistribution obligations before
   distributing an appliance. A successful simulator build is only one gate.

Unsigned scripts on a WSL UNC share may be blocked by the host execution
policy. Use a local reviewed script copy or the direct WSL invocation described
in the Workbench README; no machine-wide policy change is required. Select the
actual profile Python and bound Workbench directory for that invocation.
