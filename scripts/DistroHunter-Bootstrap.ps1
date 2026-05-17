function Get-DistroHunterBootstrapPython {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($versionArg in @("-3.12", "-3")) {
            & $pyLauncher.Source $versionArg -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{
                    Command = $pyLauncher.Source
                    Args    = @($versionArg)
                }
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{
                Command = $python.Source
                Args    = @()
            }
        }
    }

    throw "Python 3.12 or newer was not found. Install Python first, then rerun setup."
}

function Test-DistroHunterRequirementsInstalled {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [string]$RequirementsPath
    )

    if (-not (Test-Path -LiteralPath $RequirementsPath)) {
        return $true
    }

    $checkScript = @'
import importlib.metadata
import re
import sys
from pathlib import Path

requirements_path = Path(sys.argv[1])
missing = []

for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        continue

    match = re.match(r"([A-Za-z0-9_.-]+)", line)
    if not match:
        continue

    package_name = match.group(1)
    try:
        importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        missing.append(package_name)

if missing:
    print("\n".join(missing))
    raise SystemExit(1)
'@

    $output = $checkScript | & $PythonPath - $RequirementsPath 2>&1
    if ($LASTEXITCODE -eq 0) {
        return $true
    }

    if ($output) {
        Write-Host "Missing Python packages: $($output -join ', ')"
    }
    return $false
}

function Install-DistroHunterRequirements {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [string]$RequirementsPath
    )

    if (-not (Test-Path -LiteralPath $RequirementsPath)) {
        return
    }

    Write-Host "Installing Python packages from requirements.txt..."
    & $PythonPath -m pip install --disable-pip-version-check -r $RequirementsPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed for $RequirementsPath"
    }
}

function Resolve-DistroHunterAria2Path {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $repoLocal = Join-Path $RepoRoot "tools\aria2\aria2c.exe"
    $candidates = @($repoLocal, "C:\Tools\aria2\aria2c.exe")

    $command = Get-Command aria2c -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    foreach ($envVar in @("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")) {
        $base = [Environment]::GetEnvironmentVariable($envVar)
        if (-not $base) {
            continue
        }
        switch ($envVar) {
            "LOCALAPPDATA" {
                $candidates += Join-Path $base "Programs\aria2\aria2c.exe"
            }
            default {
                $candidates += Join-Path $base "aria2\aria2c.exe"
            }
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Install-DistroHunterAria2 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $existing = Resolve-DistroHunterAria2Path -RepoRoot $RepoRoot
    if ($existing) {
        return $existing
    }

    $installRoot = Join-Path $RepoRoot "tools\aria2"
    $tempZip = Join-Path ([IO.Path]::GetTempPath()) ("aria2-{0}.zip" -f ([guid]::NewGuid().ToString("N")))
    $extractRoot = Join-Path ([IO.Path]::GetTempPath()) ("aria2-{0}" -f ([guid]::NewGuid().ToString("N")))
    $releaseApi = "https://api.github.com/repos/aria2/aria2/releases/latest"
    $headers = @{
        "User-Agent" = "DistroHunter-Bootstrap"
        "Accept"     = "application/vnd.github+json"
    }

    try {
        Write-Host "aria2c was not found; downloading a portable copy..."
        $release = Invoke-RestMethod -Headers $headers -Uri $releaseApi -ErrorAction Stop
        $asset = $release.assets | Where-Object {
            $_.browser_download_url -match 'win-64bit-build1\.zip$'
        } | Select-Object -First 1

        if (-not $asset) {
            throw "No Windows 64-bit aria2 release asset was found."
        }

        New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
        Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $tempZip -ErrorAction Stop
        Expand-Archive -LiteralPath $tempZip -DestinationPath $extractRoot -Force

        $packageRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
        if (-not $packageRoot) {
            throw "The aria2 archive did not contain an extracted package directory."
        }

        Copy-Item -Path (Join-Path $packageRoot.FullName "*") -Destination $installRoot -Recurse -Force
        $installed = Join-Path $installRoot "aria2c.exe"
        if (-not (Test-Path -LiteralPath $installed)) {
            throw "aria2c.exe was not found after extraction."
        }
        return $installed
    }
    finally {
        if (Test-Path -LiteralPath $tempZip) {
            Remove-Item -LiteralPath $tempZip -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $extractRoot) {
            Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Ensure-DistroHunterEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [switch]$ForceInstall
    )

    $venvRoot = Join-Path $RepoRoot ".venv"
    $venvPython = Join-Path $venvRoot "Scripts\python.exe"
    $requirementsPath = Join-Path $RepoRoot "requirements.txt"
    $stampPath = Join-Path $venvRoot ".requirements.sha256"
    $venvCreated = $false

    if (-not (Test-Path -LiteralPath $venvPython)) {
        $bootstrap = Get-DistroHunterBootstrapPython
        Write-Host "Creating virtual environment at $venvRoot..."
        & $bootstrap.Command @($bootstrap.Args + @("-m", "venv", $venvRoot))
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the virtual environment at $venvRoot"
        }
        $venvCreated = $true
    }

    $requirementsHash = $null
    $installedHash = ""
    if (Test-Path -LiteralPath $requirementsPath) {
        $requirementsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $requirementsPath).Hash
        if (Test-Path -LiteralPath $stampPath) {
            $installedHash = (Get-Content -LiteralPath $stampPath -Raw).Trim()
        }
    }

    $needsInstall = $ForceInstall.IsPresent -or $venvCreated
    if (-not $needsInstall) {
        if ($requirementsHash -and $requirementsHash -ne $installedHash) {
            $needsInstall = $true
        }
        elseif (-not (Test-DistroHunterRequirementsInstalled -PythonPath $venvPython -RequirementsPath $requirementsPath)) {
            $needsInstall = $true
        }
    }

    if ($needsInstall) {
        Install-DistroHunterRequirements -PythonPath $venvPython -RequirementsPath $requirementsPath
        if ($requirementsHash) {
            Set-Content -LiteralPath $stampPath -Value $requirementsHash -Encoding ASCII
        }
    }

    $aria2Path = Resolve-DistroHunterAria2Path -RepoRoot $RepoRoot
    if (-not $aria2Path -and ($ForceInstall.IsPresent -or $venvCreated)) {
        try {
            $aria2Path = Install-DistroHunterAria2 -RepoRoot $RepoRoot
        }
        catch {
            Write-Warning "aria2c is unavailable and automatic download failed: $($_.Exception.Message)"
        }
    }
    if ($aria2Path) {
        Write-Host "aria2c ready at $aria2Path"
    }

    return $venvPython
}
