param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "config.example.json"),
    [switch]$DryRun,
    [switch]$SkipSync,
    [switch]$ForceInstall
)

$bootstrapScript = Join-Path $PSScriptRoot "scripts\DistroHunter-Bootstrap.ps1"
. $bootstrapScript

$python = Ensure-DistroHunterEnvironment -RepoRoot $PSScriptRoot -ForceInstall:$ForceInstall
$args = @("-m", "distro_hunter", "--config", $ConfigPath, "run")

if ($DryRun) {
    $args += "--dry-run"
}

if ($SkipSync) {
    $args += "--skip-sync"
}

Push-Location $PSScriptRoot
try {
    & $python @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
