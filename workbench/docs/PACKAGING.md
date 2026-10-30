# Packaging the SALAM Research Workbench

Status: packaging recommendations, 2026-10-29. No installer, container, WSL export, or VM was built for this note. The verified simulator environment is Ubuntu 20.04 under WSL 2 with LLVM/Clang 12, Python 3.8, GCC 9, and ARM GCC 9. A current upstream gem5 container or a newer Linux base has not been shown to build this SALAM fork.

## Recommended sequence

| Stage | User experience | What it packages | Next proof required |
|---|---|---|---|
| 1. Windows shortcut to the existing WSLg GUI | Open the configuration editor from Windows | A launcher for the current WSL installation | Launch, edit, rebuild, run, close, and reopen on a second desktop session |
| 2. Pinned Docker build and run image | Repeat headless builds and simulations on another WSL 2 host | Toolchain, source revision, dependencies, and scripts | Fresh image build and the existing independent numeric and trace checks |
| 3. Clean, exportable WSL appliance | Import a ready Linux environment on another Windows machine | An installed Linux distribution and simulator | Import into a new distro name, run the checks, and verify external data mounts |
| 4. Native Windows PySide front end | Windows executable for the editor, Linux backend for simulation | GUI and a versioned request protocol | End-to-end cross-process tests and a real Windows package |
| 5. Full VM if a separate kernel or non-WSL host is needed | Portable machine image | Guest OS and simulator | Reproduce the same run and compare evidence |

The first stage reuses the tested path. The later stages solve different portability problems and should be accepted separately.

## 1. Convenient Windows launch now

The current PowerShell entry point is workbench.ps1 -Action configurator. It reads a local workspace.json, starts Python 3.8 in the selected WSL distribution, and loads the existing Qt editor. A Windows shortcut can point to:

~~~text
powershell.exe -NoProfile -File "<checkout>\workbench.ps1" -Action configurator
~~~

For a checkout on a WSL UNC share, Windows may classify the unsigned PowerShell script as remote and refuse it. An alternative shortcut target is `wsl.exe`, with arguments `-d <distribution> --cd <Linux-checkout>/workbench --exec /usr/bin/python3.8 -B -m salam_workbench.configurator_app`. This uses the same GUI without changing machine-wide execution policy. The process-only PowerShell launch was separately checked on the development host.

Set the shortcut working directory to the checkout. The script resolves its manifest from its own directory, so it does not depend on the shell starting there. Keep workspace.json as a local machine setting; put a documented example and validation command in the source package. A separate shortcut can use -Action configurator -Inspect for an offscreen readiness check.

WSLg supports Linux GUI windows integrated with the Windows desktop on WSL 2. Microsoft documents Windows 11 and Windows 10 build 19044 or later as supported hosts. This route still needs the Linux simulator and current distribution installed; a shortcut is convenience, not an installer. [Microsoft: Linux GUI apps in WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)

For build-heavy source, prefer the Linux filesystem inside the distribution; Microsoft documents better Linux command-line performance there than under /mnt/c or another Windows mount. Keep durable evidence in a deliberate external directory with a manifest and backup policy. The existing D: workbench layout is a working local arrangement; relocation is a separate migration, not part of a shortcut. [Microsoft: WSL file systems](https://learn.microsoft.com/en-us/windows/wsl/filesystems)

Current checked runs establish that edited GUI requests can generate a configuration, rebuild an isolated variant when required, and run a simulation. They do not by themselves prove that an unsaved form can be reopened after the app closes. Add explicit Save project, Open project, and Recent runs actions using versioned request JSON plus evidence paths, then test a close/reopen round trip. Keep source YAML and prior receipts immutable; a new edit creates a new request and run record.

## 2. Pinned Docker for reproducible builds and runs

Create a Dockerfile from the validated Ubuntu 20.04 toolchain, not from a current gem5 image by name. Pin the base image digest, apt repository snapshot or package versions, Python wheels, generator inputs, source commit, and simulator build receipt. Build the image from source in CI and publish its content digest. The first container acceptance test should regenerate the required C++ and SimObjects, build the simulator and guest, run GEMM plus a negative output control, and independently replay direct SALAM scheduling traces. Until that passes, Docker is a proposed reproduction route.

Use Docker Desktop with its WSL 2 backend on Windows. Docker documents integration with a selected WSL distribution, so the GUI can remain in WSLg while a container handles headless build and simulation. GUI display forwarding from a container needs its own tested setup; it is not assumed here. [Docker: WSL 2 backend](https://docs.docker.com/desktop/features/wsl/)

An image is the packaged software and filesystem layers. A container is an instance with its own writable layer. Put run inputs, completed outputs, receipts, and profiles on explicit persistent mounts rather than relying on that writable layer. Docker volumes persist across container removal and are a strong choice for Linux-side data; bind mounts are suitable when the host must directly browse and back up the files. Test the chosen mount layout with a recreated container, including ownership and path mapping. [Docker: storage](https://docs.docker.com/engine/storage/), [Docker: volumes and bind mounts](https://docs.docker.com/engine/storage/volumes/)

Persisted files are different from an in-flight process. A Docker image, volume, or WSL export does not capture the accelerator simulation currently executing in RAM. Docker has a separate experimental checkpoint/restore facility with stated limitations; it is not part of this workbench acceptance contract. If resumable long runs become necessary, add and test an explicit gem5 checkpoint workflow with source, binary, input, and restored-result identity checks. Until then, interrupted runs should be recorded as incomplete and rerun from their saved inputs. [Docker: checkpoint limitations](https://docs.docker.com/reference/cli/docker/checkpoint/)

## 3. Exportable WSL appliance before a full VM

Build a clean, named WSL distribution from the pinned source and toolchain, validate it, then export it as tar or VHDX. Microsoft documents wsl --export and wsl --import for this purpose. A WSL export captures the distribution filesystem; Windows-mounted evidence directories must be transferred and verified separately. Do not export the everyday development distribution as a public appliance because it can include unrelated files and machine-specific state. [Microsoft: WSL export and import](https://learn.microsoft.com/en-us/windows/wsl/basic-commands), [Microsoft: custom distributions](https://learn.microsoft.com/en-us/windows/wsl/use-custom-distro)

A usable appliance would ship an import guide, source revision, package manifest, local configuration template, smoke-test command, and a checksum for the export. Verify on a second machine or a fresh imported distro before calling it portable. A full VM adds size and maintenance and is useful later only if WSL 2 cannot satisfy a concrete host or kernel requirement.

## 4. Native Windows PySide front end later

The editor can eventually be packaged for Windows while the simulator stays in WSL. Preserve the current versioned configuration request, asynchronous execution, and durable receipt as the boundary between front end and backend. Replace direct imports from the Linux engine with a small WSL command or local service adapter, then test source selection, cancellation, errors, progress, and reopening saved sessions.

Qt provides pyside6-deploy for standalone or single-file Windows executables. That tool packages the PySide app, not the Linux simulator or WSL distribution. The Windows GUI package and backend appliance therefore need separate version and compatibility checks. [Qt for Python: pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)

## Release acceptance checklist

- Clean checkout and pinned dependency manifest build the same required simulator inputs.
- Numerical oracle, intentional wrong-output control, GUI apply/rebuild/run, and direct SALAM trace replay pass in the packaged environment.
- Closing and reopening the GUI restores a saved project and locates prior receipts; unsaved edits are clearly marked.
- Recreating a container or reimporting a clean WSL distro preserves external evidence files and can rerun a recorded request.
- Source package excludes raw run output, build binaries, local workspace.json, and private recovery material. The public result summary states measured values and the evidence scope without embedding raw local traces.
