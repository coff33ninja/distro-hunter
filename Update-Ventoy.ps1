param(
    [string]$ConfigPath,
    [ValidateSet("Linux", "Windows", "All")][string]$Target = "Linux",
    [string]$Plugin,
    [switch]$DryRun,
    [switch]$SkipSync,
    [switch]$ForceInstall
)

$bootstrapScript = Join-Path $PSScriptRoot "scripts\DistroHunter-Bootstrap.ps1"
. $bootstrapScript

$python = Ensure-DistroHunterEnvironment -RepoRoot $PSScriptRoot -ForceInstall:$ForceInstall

# Linux -> ISO/Linux/<family>/<edition>, Windows -> ISO/Windows/<product>/<release> on the same Ventoy drive.
$configs = if ($ConfigPath) {
    @($ConfigPath)
} else {
    $linux = Join-Path $PSScriptRoot "config.example.json"
    $windows = Join-Path $PSScriptRoot "config.windows.json"
    switch ($Target) {
        "Linux"   { @($linux) }
        "Windows" { @($windows) }
        "All"     { @($linux, $windows) }
    }
}

Push-Location $PSScriptRoot
try {
    $exitCode = 0
    foreach ($config in $configs) {
        $runArgs = @("-m", "distro_hunter", "--config", $config, "run")
        if ($DryRun) { $runArgs += "--dry-run" }
        if ($SkipSync) { $runArgs += "--skip-sync" }
        if ($Plugin) { $runArgs += @("--plugin", $Plugin) }
        & $python @runArgs
        if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }
    }
    exit $exitCode
}
finally {
    Pop-Location
}
