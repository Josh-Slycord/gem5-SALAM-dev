<#
.SYNOPSIS
Build an experimental SALAM snapshot and optionally import a new WSL2 instance.
Existing distributions and export artifacts are never replaced.
.DESCRIPTION
Simulator build success is not configured-workbench or numerical acceptance.
All source archives, rootfs exports and manifests live in ArtifactRoot outside
the source checkout. Requires a clean committed source tree.
#>
[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidateNotNullOrEmpty()]
    [string]$Commit = "HEAD",
    [ValidateNotNullOrEmpty()]
    [string]$ImageName = "gem5-salam-checkpoint",
    [ValidateNotNullOrEmpty()]
    [string]$BaseImage = "ubuntu:22.04",
    [ValidateRange(1, 32)]
    [int]$Jobs = 2,
    [Parameter(Mandatory = $true)]
    [string]$ArtifactRoot,
    [string]$DistroName = "gem5-salam-prebuilt",
    [string]$WslInstallDir,
    [switch]$Import,
    [switch]$SkipBuild,
    [switch]$SkipExport
)
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE."
    }
}
function Read-Checked {
    param([string]$Program, [string[]]$Arguments)
    $value = & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE."
    }
    return $value
}
function Test-InSource {
    param([string]$Candidate, [string]$Source)
    $prefix = $Source.TrimEnd([char[]]"\/") +
        [IO.Path]::DirectorySeparatorChar
    return $Candidate.Equals($Source, [StringComparison]::OrdinalIgnoreCase) -or
        $Candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

$source = (Resolve-Path -LiteralPath $SourceRoot).ProviderPath
$artifacts = [IO.Path]::GetFullPath($ArtifactRoot)
if (Test-InSource $artifacts $source) {
    throw "ArtifactRoot must be outside the source checkout."
}
if ($Import -and -not $WslInstallDir) {
    throw "-Import requires an explicit -WslInstallDir on the intended disk."
}
if ($Import) {
    $install = [IO.Path]::GetFullPath($WslInstallDir)
    if ((Test-InSource $install $source) -or
        (Test-InSource $install $artifacts) -or
        (Test-Path -LiteralPath $install)) {
        throw "Choose a new WslInstallDir outside source and artifact paths."
    }
    $existing = Read-Checked "wsl.exe" @("--list", "--quiet")
    $names = @($existing | ForEach-Object { ($_ -replace "\0", "").Trim() })
    if ($names -contains $DistroName) {
        throw "Distribution already exists; choose a new name. No replacement."
    }
}
$gitPrefix = @("--no-optional-locks", "-c", "core.fsmonitor=false", "-C", $source)
$sha = ((Read-Checked "git" ($gitPrefix + @(
    "rev-parse", "--verify", "$Commit^{commit}"
))) -join "").Trim()
if ($sha -notmatch '^[0-9a-f]{40}$') { throw "Expected a full source commit." }
$tree = Read-Checked "git" ($gitPrefix + @("ls-tree", "-r", $sha))
if (@($tree | Where-Object { $_ -match '^160000 ' }).Count) {
    throw "Selected source has gitlinks; archive packaging needs their contents."
}
if ($Commit -eq "HEAD") {
    $dirty = Read-Checked "git" ($gitPrefix + @(
        "status", "--porcelain", "--untracked-files=normal"
    ))
    if ($dirty) { throw "Commit the reviewed changes before packaging HEAD." }
}
[IO.Directory]::CreateDirectory($artifacts) | Out-Null
$context = Join-Path $artifacts "context"
$tarPath = Join-Path $artifacts "rootfs.tar"
$manifestPath = Join-Path $artifacts "appliance.json"
if (-not $SkipBuild) {
    if (Test-Path -LiteralPath $context) {
        throw "Build context exists; use a new ArtifactRoot."
    }
    [IO.Directory]::CreateDirectory($context) | Out-Null
    $sourceTar = Join-Path $context "source.tar"
    Invoke-Checked "git" ($gitPrefix + @(
        "archive", "--format=tar", "--output=$sourceTar", $sha
    ))
    # Dockerfile and source.tar must come from the same selected commit.
    $recipe = Read-Checked "git" ($gitPrefix + @(
        "show", "${sha}:docker/Dockerfile"
    ))
    [IO.File]::WriteAllText(
        (Join-Path $context "Dockerfile"),
        ($recipe -join "`n") + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    $archiveHash = (Get-FileHash -LiteralPath $sourceTar -Algorithm SHA256).Hash
    Invoke-Checked "docker" @("version", "--format", "{{.Server.Version}}")
    Invoke-Checked "docker" @(
        "build", "--tag", $ImageName,
        "--build-arg", "BASE_IMAGE=$BaseImage",
        "--build-arg", "SALAM_COMMIT=$sha",
        "--build-arg", "SOURCE_ARCHIVE_SHA256=$($archiveHash.ToLowerInvariant())",
        "--build-arg", "BUILD_JOBS=$Jobs", $context
    )
}
if (-not $SkipExport) {
    if ((Test-Path -LiteralPath $tarPath) -or
        (Test-Path -LiteralPath "$tarPath.partial") -or
        (Test-Path -LiteralPath $manifestPath)) {
        throw "Export already exists; choose a new ArtifactRoot."
    }
    $image = (Read-Checked "docker" @("image", "inspect", $ImageName) |
        Out-String | ConvertFrom-Json)[0]
    if ($image.Config.Labels.'org.opencontainers.image.revision' -ne $sha) {
        throw "Image source identity differs from the selected commit."
    }
    if ($image.Config.Labels.'org.salam.source-archive.sha256' -notmatch
        '^[0-9a-f]{64}$') {
        throw "Image has no valid source archive SHA-256 label."
    }
    $container = ((Read-Checked "docker" @("create", $image.Id)) -join "").Trim()
    if ($container -notmatch '^[0-9a-f]{12,64}$') {
        throw "Docker returned an unexpected export container ID."
    }
    # Preserve this task-created stopped container for audit; no forced removal.
    Invoke-Checked "docker" @("export", $container, "--output", "$tarPath.partial")
    Move-Item -LiteralPath "$tarPath.partial" -Destination $tarPath
    $record = [ordered]@{
        schema_version = 1
        state = "experimental_unvalidated_appliance"
        source_commit = $sha
        source_archive_sha256 =
            $image.Config.Labels.'org.salam.source-archive.sha256'
        image_id = $image.Id
        image_repo_digests = @($image.RepoDigests)
        base_image_requested = $BaseImage
        export_container = $container
        rootfs = $tarPath
        rootfs_sha256 = (Get-FileHash $tarPath -Algorithm SHA256).Hash.ToLowerInvariant()
        built_at_utc = [DateTime]::UtcNow.ToString("o")
        configured_gui_acceptance = "not_performed"
        independent_numerical_acceptance = "not_performed"
    }
    $record | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $manifestPath -Encoding UTF8
}
if ($Import) {
    if (-not (Test-Path -LiteralPath $tarPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Import requires an exported rootfs and appliance.json."
    }
    $record = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $actualHash = (Get-FileHash $tarPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($record.rootfs_sha256 -ne $actualHash -or $record.source_commit -ne $sha) {
        throw "Export hash/source identity check failed."
    }
    [IO.Directory]::CreateDirectory($install) | Out-Null
    Invoke-Checked "wsl.exe" @(
        "--import", $DistroName, $install, $tarPath, "--version", "2"
    )
    Write-Host "Imported $DistroName. GUI/numerical acceptance remain pending."
}
Write-Host "Artifacts: $artifacts"
Write-Host "Existing WSL installations and checkout bindings were not changed."
