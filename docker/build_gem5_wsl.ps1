<#
.SYNOPSIS
    Builds the pre-compiled gem5-SALAM Docker image, exports its rootfs, and registers
    it as an independent native WSL2 distribution.

.PARAMETER ImageName
    Name of the Docker image to build. Default: 'gem5-salam-prebuilt'.

.PARAMETER DistroName
    Name of the registered WSL distro. Default: 'gem5-salam-prebuilt'.

.PARAMETER TarPath
    Path where the rootfs tarball will be exported. Default: 'D:\wsl_backups\gem5-salam-prebuilt.tar'.

.PARAMETER WslInstallDir
    Directory on host disk where the WSL2 ext4.vhdx will reside. Default: 'D:\wsl_instances\gem5-salam-prebuilt'.

.PARAMETER SkipBuild
    Skip running `docker build` if the image is already built locally.

.PARAMETER SkipExport
    Skip creating and exporting the container tarball if TarPath already exists.

.EXAMPLE
    .\build_gem5_wsl.ps1
    .\build_gem5_wsl.ps1 -DistroName "gem5-dev" -WslInstallDir "D:\wsl_instances\gem5-dev"
#>

[CmdletBinding()]
param (
    [string]$ImageName = "gem5-salam-prebuilt",
    [string]$DistroName = "gem5-salam-prebuilt",
    [string]$TarPath = "D:\wsl_backups\gem5-salam-prebuilt.tar",
    [string]$WslInstallDir = "D:\wsl_instances\gem5-salam-prebuilt",
    [switch]$SkipBuild,
    [switch]$SkipExport,
    [switch]$NoImport
)

$ErrorActionPreference = "Stop"
$swTotal = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " gem5-SALAM Pre-compiled Docker -> WSL2 Distro Generator" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 0. Check Docker CLI & Auto-discover PATH if needed
Write-Host "`n[1/4] Checking Docker availability..." -ForegroundColor Yellow

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $knownDockerPaths = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin",
        "$env:ProgramFiles\Docker\Docker\resources\bin",
        "C:\Program Files\Docker\Docker\resources\bin"
    )
    foreach ($cand in $knownDockerPaths) {
        if (Test-Path (Join-Path $cand "docker.exe")) {
            Write-Host "  -> Auto-detected Docker CLI in $cand (adding to session PATH)" -ForegroundColor DarkGray
            $env:PATH = "$cand;$env:PATH"
            break
        }
    }
}

try {
    $dockerVer = docker version --format '{{.Server.Version}}' 2>$null
    if (-not $dockerVer) {
        Write-Error "Docker is not running or not accessible. Please ensure Docker Desktop is started."
    }
    Write-Host "  -> Docker Engine connected (v$dockerVer)" -ForegroundColor Green
} catch {
    Write-Error "Failed to execute 'docker version': $_"
}

# 1. Build Docker Image
$DockerDir = $PSScriptRoot
if (-not $SkipBuild) {
    Write-Host "`n[2/4] Building Docker image '$ImageName' from $DockerDir..." -ForegroundColor Yellow
    Write-Host "  -> Note: Pre-compiling gem5.opt can take 15-30 minutes depending on CPU." -ForegroundColor DarkGray
    $swBuild = [System.Diagnostics.Stopwatch]::StartNew()

    docker build -t $ImageName -f (Join-Path $DockerDir "Dockerfile") $DockerDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed with exit code $LASTEXITCODE."
    }
    $swBuild.Stop()
    Write-Host "  -> Docker image built in $($swBuild.Elapsed.ToString('hh\:mm\:ss'))" -ForegroundColor Green
} else {
    Write-Host "`n[2/4] Skipping Docker build (-SkipBuild specified)." -ForegroundColor DarkGray
}

# 2. Export Container Filesystem to Tarball
$tarDir = Split-Path -Parent $TarPath
if (-not (Test-Path $tarDir)) {
    New-Item -ItemType Directory -Path $tarDir -Force | Out-Null
}

if (-not $SkipExport) {
    Write-Host "`n[3/4] Exporting rootfs tarball to $TarPath..." -ForegroundColor Yellow
    $swExport = [System.Diagnostics.Stopwatch]::StartNew()

    Write-Host "  -> Creating temporary export container..." -ForegroundColor DarkGray
    $containerId = (docker create $ImageName).Trim()
    if (-not $containerId) {
        Write-Error "Failed to create temporary Docker container for export."
    }

    try {
        Write-Host "  -> Exporting filesystem..." -ForegroundColor DarkGray
        docker export $containerId -o $TarPath
        if ($LASTEXITCODE -ne 0) {
            Write-Error "docker export failed with exit code $LASTEXITCODE."
        }
    } finally {
        docker rm -f $containerId | Out-Null
    }

    $tarItem = Get-Item $TarPath
    $tarMB = [math]::Round($tarItem.Length / 1MB, 2)
    $swExport.Stop()
    Write-Host "  -> Exported $tarMB MB in $($swExport.Elapsed.ToString('hh\:mm\:ss'))" -ForegroundColor Green
} else {
    Write-Host "`n[3/4] Skipping export (-SkipExport specified). Using existing $TarPath." -ForegroundColor DarkGray
}

# 3. Register WSL Distro
if (-not $NoImport) {
    Write-Host "`n[4/4] Registering WSL2 distribution '$DistroName'..." -ForegroundColor Yellow

    if (-not (Test-Path $WslInstallDir)) {
        New-Item -ItemType Directory -Path $WslInstallDir -Force | Out-Null
    }

    # Check if a distro with this name already exists
    $existing = wsl -l -q 2>$null
    if ($existing -match [regex]::Escape($DistroName)) {
        Write-Warning "A WSL distribution named '$DistroName' is already registered."
        $confirm = Read-Host "Unregister/replace '$DistroName'? This will delete its current disk image (y/N)"
        if ($confirm -match '^[Yy]') {
            Write-Host "  -> Unregistering existing distro..." -ForegroundColor DarkGray
            wsl --unregister $DistroName
        } else {
            Write-Host "  -> Aborting import to protect existing distro." -ForegroundColor Yellow
            return
        }
    }

    $swImport = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host "  -> Importing into $WslInstallDir..." -ForegroundColor DarkGray
    wsl --import $DistroName $WslInstallDir $TarPath --version 2
    if ($LASTEXITCODE -ne 0) {
        Write-Error "wsl --import failed with exit code $LASTEXITCODE."
    }
    $swImport.Stop()
    Write-Host "  -> Registered WSL distro in $($swImport.Elapsed.ToString('hh\:mm\:ss'))" -ForegroundColor Green

    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host " SETUP COMPLETE!" -ForegroundColor Green
    Write-Host " Total time: $($swTotal.Elapsed.ToString('hh\:mm\:ss'))" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "`nTo enter your pre-configured gem5-SALAM environment:" -ForegroundColor Cyan
    Write-Host "  wsl -d $DistroName" -ForegroundColor Yellow
    Write-Host "`nTo verify the pre-compiled simulator inside WSL:" -ForegroundColor Cyan
    Write-Host "  ./build/ARM/gem5.opt --version" -ForegroundColor Yellow
} else {
    Write-Host "`n[4/4] Skipping WSL import (-NoImport specified)." -ForegroundColor DarkGray
}
