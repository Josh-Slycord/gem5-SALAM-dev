# SPDX-License-Identifier: BSD-3-Clause
# Native commands are mocked; no image or distribution is created.
param([string]$ArtifactRoot, [string]$PackageRoot = $PSScriptRoot)
$ErrorActionPreference='Stop'

$sourceRoot=Split-Path -Parent $packageRoot
if (-not $ArtifactRoot) {
    $ArtifactRoot=Join-Path ([IO.Path]::GetTempPath()) (
        'salam-packaging-contracts-' + [Guid]::NewGuid().ToString('N'))
}
$validationRoot=[IO.Path]::GetFullPath($ArtifactRoot)
[IO.Directory]::CreateDirectory($validationRoot) | Out-Null
foreach ($name in @('build_gem5_wsl.ps1','launch_workbench.ps1')) {
    $parseTokens=$null
    $parseErrors=$null
    [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $packageRoot $name),[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
}
$launchScript=[scriptblock]::Create((Get-Content -LiteralPath (Join-Path $packageRoot 'launch_workbench.ps1') -Raw))
$buildScript=[scriptblock]::Create((Get-Content -LiteralPath (Join-Path $packageRoot 'build_gem5_wsl.ps1') -Raw))
$checks=[Collections.Generic.List[object]]::new()
function Assert-Reject([scriptblock]$Action,[string]$Expected,[string]$Name) {
    try { & $Action; throw "Expected rejection missing: $Name" }
    catch {
        if($_.Exception.Message -notmatch $Expected) { throw }
        $checks.Add(@{name=$Name;state='passed';message=$_.Exception.Message})
    }
}
function wsl.exe {
    $script:launchArgs=@($args)
    $script:launchCode=($input | Out-String)
    $global:LASTEXITCODE=0
}
& $launchScript -Distribution 'test-only' -WorkbenchRoot '/path with spaces/workbench' -Inspect -Benchmark 'benchmarks/sys_validation/fft'
if($launchArgs -notcontains '/path with spaces/workbench' -or
   $launchArgs -notcontains '--inspect' -or
   $launchArgs -notcontains 'benchmarks/sys_validation/fft' -or
   $launchCode -notmatch 'os.execv') {
    throw 'Launcher argument contract failed'
}
$checks.Add(@{name='launcher argument/profile contract';state='passed'})
function wsl.exe { $global:LASTEXITCODE=7 }
Assert-Reject { & $launchScript -Inspect } 'exit code 7' 'launcher propagates native failure'
Assert-Reject {
    & $buildScript -SourceRoot $sourceRoot -ArtifactRoot (Join-Path $packageRoot 'forbidden-output')
} 'outside the source checkout' 'reject output inside source'
function git {
    $global:LASTEXITCODE=0
    if($args -contains 'rev-parse') {
        '91fcf24bc60cda21a4d5fb6a480a60a5060d58fe'
    }
}
function docker {
    $global:LASTEXITCODE=0
    if($args -contains 'inspect') {
        '{"Id":"sha256:mock","Config":{"Labels":{"org.opencontainers.image.revision":"wrong-source"}}}'
    } else { throw 'Unexpected Docker command in source-rejection test' }
}
Assert-Reject {
    & $buildScript -SourceRoot $sourceRoot -ArtifactRoot (Join-Path $validationRoot 'wrong-image-source') -SkipBuild
} 'Image source identity differs' 'reject image source mismatch'
function git { $global:LASTEXITCODE=13 }
Assert-Reject {
    & $buildScript -SourceRoot $sourceRoot -ArtifactRoot (Join-Path $validationRoot 'failed-git') -SkipBuild -SkipExport
} 'git failed with exit code 13' 'packager propagates native failure'
$record=@{
    schema_version=1
    kind='packaging_mocked_contract_validation'
    state='passed'
    checks=@($checks)
    docker_build_performed=$false
    wsl_import_performed=$false
    execution='parsed scriptblocks; native commands mocked; no execution-policy change'
    captured_at_utc=[DateTime]::UtcNow.ToString('o')
}
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $validationRoot 'mocked-contracts.json') -Encoding UTF8
$record | ConvertTo-Json -Depth 6
