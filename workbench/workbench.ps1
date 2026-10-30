param(
    [ValidateSet("reproduce", "compare", "viewer", "test", "validate", "doctor", "checks", "regression", "models", "configure", "configurator")]
    [string]$Action = "reproduce",
    [switch]$BuildEngine,
    [switch]$Inspect,
    [switch]$AllowSimulation,
    [ValidateSet("gemm", "parameter")][string]$View = "gemm",
    [ValidateSet("fast", "config", "gui", "collector", "gemm")][string]$Tier = "fast",
    [ValidateRange(1,86400)][int]$TimeoutSeconds = 900,
    [ValidateRange(1,32)][int]$Jobs = 8,
    [ValidateSet("bfs", "nw", "fft", "stencil3d")][string[]]$Workloads = @("bfs", "nw"),
    [ValidateRange(1,2)][int]$Repeats = 2,
    [ValidateSet("prepare", "run", "inventory", "hardware", "install", "build")][string]$ConfigureMode = "prepare",
    [string]$Configuration = "experiments/configurator/gemm_baseline.json",
    [string]$ConfiguredEngine,
    [string]$BuildReceipt,
    [string]$EvidenceDirectory,
    [string]$GenerationReceipt,
    [string]$PreviousOverlay,
    [string]$HardwareBenchmark = "gemm",
    [string]$HardwareModel = "40nm_model",
    [string]$HardwarePeriod = "5ns",
    [string]$HardwareProfile = "default_profile"
)
$ErrorActionPreference = "Stop"
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot "workspace.json") -Raw | ConvertFrom-Json
$distribution = $manifest.engine.distribution
$enginePath = $manifest.engine.path
if ($distribution -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid WSL distribution in workspace.json" }
function ConvertTo-WorkbenchWslPath([string]$TaskPath) {
    if ($TaskPath.StartsWith("/")) { return $TaskPath }
    if ($TaskPath -match '^\\\\(?:wsl\$|wsl\.localhost)\\([^\\]+)\\(.+)$') {
        if ($Matches[1] -ine $distribution) {
            throw "WSL share distribution does not match workspace.json"
        }
        return "/" + $Matches[2].Replace("\","/")
    }
    if ($TaskPath -match '^[A-Za-z]:[\\/]') {
        return "/mnt/" + $TaskPath.Substring(0,1).ToLowerInvariant() + $TaskPath.Substring(2).Replace("\","/")
    }
    return $projectPath + "/" + $TaskPath.Replace("\","/")
}
$projectPath = ConvertTo-WorkbenchWslPath $PSScriptRoot
$commandArgs = @("-d", $distribution, "--cd", $projectPath, "--exec", "/usr/bin/python3.8", "-B")
switch ($Action) {
    "configurator" {
        $commandArgs += @("-m", "salam_workbench.configurator_app")
        if ($Inspect) { $commandArgs += "--inspect" }
    }
    "configure" {
        $configurationEngine = $enginePath
        if ($manifest.configuration_engine -and $ConfigureMode -in @("prepare", "run")) {
            $configurationEngine = $manifest.configuration_engine.path
            if (-not $BuildReceipt -and -not $ConfiguredEngine) { $BuildReceipt = $manifest.configuration_engine.build_receipt }
        }
        if ($ConfigureMode -in @("build", "install") -and -not $ConfiguredEngine) {
            throw "Select an independent source copy with -ConfiguredEngine for build/install."
        }
        if ($ConfiguredEngine) { $configurationEngine = ConvertTo-WorkbenchWslPath $ConfiguredEngine }
        $commandArgs += @("-m", "salam_workbench.configurator", $ConfigureMode, "--engine", $configurationEngine, "--jobs", "$Jobs")
        if ($ConfigureMode -in @("prepare", "run")) { $commandArgs += @("--spec", (ConvertTo-WorkbenchWslPath $Configuration)) }
        if ($EvidenceDirectory) { $commandArgs += @("--evidence-dir", (ConvertTo-WorkbenchWslPath $EvidenceDirectory)) }
        if ($BuildReceipt) { $commandArgs += @("--build-receipt", (ConvertTo-WorkbenchWslPath $BuildReceipt)) }
        if ($GenerationReceipt) { $commandArgs += @("--generation", (ConvertTo-WorkbenchWslPath $GenerationReceipt)) }
        if ($PreviousOverlay) { $commandArgs += @("--previous-overlay", (ConvertTo-WorkbenchWslPath $PreviousOverlay)) }
        if ($ConfigureMode -eq "hardware") {
            $commandArgs += @("--benchmark-name", $HardwareBenchmark, "--model", $HardwareModel, "--period", $HardwarePeriod, "--profile", $HardwareProfile)
        }
    }
    "test" { $commandArgs += @("-m", "unittest", "discover", "-s", "tests", "-v") }
    "validate" {
        $commandArgs += @("-m", "salam_workbench.config", "$enginePath/benchmarks/sys_validation/gemm/config.yml", "--engine-root", $enginePath)
    }
    "doctor" { $commandArgs += @("-m", "salam_workbench.doctor", "--engine", $enginePath) }
    "checks" {
        $commandArgs += @("-m", "salam_workbench.checks", "--tier", $Tier, "--engine", $enginePath, "--jobs", "$Jobs", "--timeout", "$TimeoutSeconds")
        if ($AllowSimulation) { $commandArgs += "--allow-simulation" }
        if ($BuildEngine) { $commandArgs += "--build-engine" }
    }
    "regression" { $commandArgs += @("-m", "salam_workbench.regression", "--engine", $enginePath, "--repeats", "$Repeats", "--workloads") + $Workloads }
    "models" { $commandArgs += @("-m", "salam_workbench.model_data", "--engine-root", $enginePath) }
    "viewer" {
        if ($View -eq "parameter") {
            $sessionPath = $manifest.latest_parameter_session
            $savedSession = Get-Content -LiteralPath (Join-Path $PSScriptRoot ($sessionPath + "/session.json")) -Raw | ConvertFrom-Json
            $runPaths = @($savedSession.runs[0].directory, $savedSession.runs[1].directory)
        } else {
            $sessionPath = $manifest.latest_gemm_session
            $savedSession = Get-Content -LiteralPath (Join-Path $PSScriptRoot ($sessionPath + "/session.json")) -Raw | ConvertFrom-Json
            $runPaths = @($savedSession.baseline_runs[0].directory, $savedSession.baseline_runs[1].directory)
        }
        $comparisonPath = $projectPath + "/" + $sessionPath + "/report/comparison.json"
        $commandArgs += @("-m", "salam_workbench.offline_viewer", $runPaths[0], $runPaths[1], $comparisonPath)
        if ($Inspect) { $commandArgs += "--inspect" }
    }
    "compare" { $commandArgs += @("-m", "salam_workbench.variant", "--engine", $enginePath) }
    "reproduce" {
        $commandArgs += @("-m", "salam_workbench.gemm", "reproduce", "--engine", $enginePath, "--jobs", "$Jobs")
        if ($BuildEngine) { $commandArgs += "--build-engine" }
    }
}
& wsl.exe @commandArgs
exit $LASTEXITCODE
