param(
    [switch]$ForceInstall
)

$bootstrapScript = Join-Path $PSScriptRoot "scripts\DistroHunter-Bootstrap.ps1"
. $bootstrapScript

Push-Location $PSScriptRoot
try {
    $python = Ensure-DistroHunterEnvironment -RepoRoot $PSScriptRoot -ForceInstall:$ForceInstall
    Write-Host "Environment ready."
    Write-Host "Python: $python"
    Write-Host "Run with: $python -m distro_hunter --config .\config.example.json run --dry-run"
}
finally {
    Pop-Location
}
