<#
.SYNOPSIS
Launch an already bound SALAM Workbench through WSLg.
.DESCRIPTION
Uses the interpreter declared by workspace.json. This script does not create
receipts, install packages, import distributions, or change an existing engine.
#>
[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$Distribution = "gem5-salam-prebuilt",
    [ValidatePattern('^/[^\r\n]*$')]
    [string]$WorkbenchRoot = "/home/salam/workbench",
    [switch]$Inspect,
    [string]$Benchmark
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL is not available."
}
# Static Python on stdin: paths and benchmark names are argv, not shell code.
$launcher = @'
import os
import sys
from pathlib import Path

root = Path.cwd().resolve(strict=True)
manifest = root / "workspace.json"
if not manifest.is_file():
    raise SystemExit(
        "Workbench is not bound: supply verified runtime receipts using "
        "salam_workbench.bootstrap_existing; see workbench/README.md."
    )
sys.path.insert(0, str(root))
from salam_workbench.toolchain_profile import load_toolchain
profile = load_toolchain(root)
python = Path(profile["python"])
if not python.is_file():
    raise SystemExit("Selected profile Python is missing: " + str(python))
# Preserve a venv executable symlink; resolving it would bypass pyvenv.cfg.
os.environ["SALAM_WORKBENCH_ROOT"] = str(root)
os.environ["PYTHONPATH"] = str(root)
os.environ["PYTHONNOUSERSITE"] = "1"
os.execv(str(python), [
    str(python), "-B", "-m", "salam_workbench.configurator_app", *sys.argv[1:]
])
'@
$applicationArguments = @()
if ($Inspect) { $applicationArguments += "--inspect" }
if ($Benchmark) { $applicationArguments += @("--benchmark", $Benchmark) }
$launcher | & wsl.exe --distribution $Distribution --cd $WorkbenchRoot --exec /usr/bin/python3 - @applicationArguments
if ($LASTEXITCODE -ne 0) {
    throw "Workbench launch failed with WSL exit code $LASTEXITCODE."
}
