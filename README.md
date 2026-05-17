
# Distro Hunter

Distro Hunter is a Windows-friendly Python tool that:

- crawls official distro pages with pattern-based plugins
- picks the best current ISO candidate with simple heuristics
- downloads with `aria2c` when available, auto-discovering it from config, `PATH`, or `tools/aria2` (auto-downloads a portable copy if none is found), and falls back to Python when needed
- detects a Ventoy USB and copies updated images to it
- can generate new plugins from repeated link patterns on a page
- writes run logs and mirror failure logs for scheduled-task troubleshooting

It is designed to run cleanly from Windows Task Scheduler through the included [Update-Ventoy.ps1](./Update-Ventoy.ps1).

## What Is Included

- Built-in plugins for Arch Linux, AlmaLinux, Alpine, ChimeraOS, Debian Netinst plus Debian Live variants, Fedora Workstation plus KDE/Xfce/Cinnamon/Budgie/LXQt/MATE-Compiz/i3/Sway spins and selected ARM64 builds, FydeOS PC Intel Modern/Slim plus AMD Graphics images, Garuda flavor images, Linux Mint Cinnamon/MATE/Xfce plus Mint Edge, LMDE Cinnamon, Kali Installer plus Netinst and Weekly Installer, Manjaro GNOME/KDE/XFCE, NixOS Graphical/Minimal, Nobara variants, openSUSE MicroOS plus Tumbleweed GNOME/KDE/XFCE/DVD/NET/Rescue, Pop!_OS generic/NVIDIA plus ARM64 variants, Rocky Linux Minimal/Boot/DVD, SteamOS Recovery, SystemRescue, Ubuntu Desktop LTS plus latest and flavors, Ubuntu Server LTS plus latest, and Zorin OS Core/Education/Lite
- External `user_plugins` support so you can add distros without editing the core package
- A `generate-plugin` command that writes a new plugin from a page pattern
- Ventoy detection based on volume label and marker folders
- A running backlog in [MISSING_DISTROS.md](./MISSING_DISTROS.md) for distros and builds that still need work

## Quick Start

1. Install Python 3.12 or newer.
2. Run the setup bootstrap once:

---
```powershell
.\Setup-DistroHunter.ps1
```
---

3. Optional but recommended: leave `download.aria2_path` pointed at `tools/aria2/aria2c.exe`. The first run will auto-download a portable `aria2c` to that path if none is found on the system. The PowerShell scripts also attempt the same download during setup.
4. Edit [config.example.json](./config.example.json) for your download folder, Ventoy label, enabled plugins, and copied image extensions. The default list is intentionally large now, so trim it if you do not want a giant pull set.
5. Ventoy sync now defaults to `ISO/Linux/<distro>/<type>` where it can infer the source plugin, with a `manual` fallback folder plus optional `ventoy.manual_sources` rules for files you drop into the download library yourself.
6. Run:

---
```powershell
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json backup
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json list-plugins
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json report --format json
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json doctor
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json sync
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json discover
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json run --dry-run
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json run
.\.venv\Scripts\python.exe -m distro_hunter --config .\config.example.json tui
```
---

Or use PowerShell directly:

---
```go

```
---

---
```powershell
.\Update-Ventoy.ps1
```
---

`Setup-DistroHunter.ps1` creates `.venv` when needed and installs anything missing from [requirements.txt](./requirements.txt). `Update-Ventoy.ps1` now runs the same bootstrap automatically at startup, so scheduled tasks keep using the repo-local environment instead of whichever `python` happens to be first on `PATH`.

## Task Scheduler

Create a scheduled task that runs:

- Program: `powershell.exe`
- Arguments: `-ExecutionPolicy Bypass -File "J:\SCRIPTS\DISTRO-HUNTER\Update-Ventoy.ps1" -ConfigPath "J:\SCRIPTS\DISTRO-HUNTER\config.example.json"`
- Start in: `J:\SCRIPTS\DISTRO-HUNTER`

Useful triggers:

- daily or weekly
- on workstation unlock
- at logon

## Plugin Model

Each plugin is a single Python file with:

---
```python
from distro_hunter.models import Candidate

NAME = "My Distro"

def discover(context) -> list[Candidate]:
    return [
        Candidate(url="https://example.org/releases/latest.iso", priority=5)
    ]
```
---

Drop custom plugins into `user_plugins`.

## Self-Generating Plugins

Generate a starter plugin from a page pattern:

---
```powershell
python -m distro_hunter --config .\config.example.json generate-plugin `
  --name "Linux Mint" `
  --page-url "https://mirrors.edge.kernel.org/linuxmint/stable/"
```
---

Then review the generated file in `user_plugins` and tighten the filters if needed.

## Notes

- `prefer_torrent` only applies when a plugin exposes a magnet or torrent link and `aria2c` is configured.
- If `download.aria2_path` is missing or stale, Distro Hunter looks for `aria2c` on `PATH`, under `tools/aria2`, and in common Windows install locations. As a last resort it auto-downloads a portable copy from GitHub to `tools/aria2/aria2c.exe` so no manual installation is needed.
- `doctor` runs discovery plus a remote file probe for each selected plugin and reports `ok`, `no candidates`, `changed page shape`, or `download head failed`, now with per-plugin timing plus last-known-good and failure-count context in the output. It exits non-zero if any plugin is unhealthy.
- `sync` copies the current local library to Ventoy using the existing route map and manual fallback behavior without running discovery or downloads first.
- `report` exports the current persisted selection, download, remote, and health snapshot as JSON or CSV for scripts and scheduled-task review.
- `report` now also includes plugin metadata fields such as family, architecture, edition type, source kind, and the inferred Ventoy subfolder so routing decisions are visible in exports.
- `plugins.profiles` lets you expand named groups such as `desktop`, `server`, `arm`, `gaming`, and `minimal` instead of hand-managing every builtin slug in the main list.
- `plugins.overrides` lets you filter or boost candidates per plugin with `disabled_hosts`, `include`, `exclude`, `forced_urls`, and `priority_boost` without editing plugin files.
- `generate-plugin` now supports `--preview`, `--validate`, `--review`, and `--with-test` so you can inspect the inferred pattern, confirm the generated plugin still returns candidates, review tightening suggestions before enabling it, and optionally write a starter test file.
- `doctor`, `discover`, `run`, `sync`, and `tui` now use a single-run lockfile in your state directory so overlapping scheduled runs fail fast instead of racing on logs, state, or downloads.
- Page fetches, remote file probes, and built-in downloads now retry automatically with backoff using `download.retry_attempts` and `download.retry_backoff_seconds`.
- Built-in downloads now keep partial `.part` files and resume them with HTTP `Range` requests after transient timeouts instead of restarting from zero every time.
- Discovery page fetches now persist a disk cache between runs using `download.page_cache_dir` and `download.page_cache_ttl_seconds`, so repeated scheduled runs can reuse fresh page bodies without re-fetching every source immediately.
- Discovery now runs multiple plugins in parallel using `download.discovery_workers`, and shared page-cache writes use atomic file replacement so plugin families that hit the same upstream page do not corrupt cache entries.
- Downloaded artifacts now verify checksums when a source page or standard sidecar file exposes one, and checksum mismatches fail the download before the file can be synced to Ventoy. You can tighten that with `download.require_checksums`.
- Repeated runs now reuse a previously verified checksum when the local file, expected digest, and file timestamp all still match, so unchanged multi-GB images are not re-hashed from scratch every time.
- Repeated download failures now create per-host mirror backoff entries in state, and later runs automatically push those mirrors behind healthier fallback candidates using `download.mirror_backoff_base_seconds` and `download.mirror_backoff_cap_seconds`.
- Downloads now protect against silent filename collisions by automatically switching to a stable plugin-prefixed local filename when another plugin already owns the generic name.
- Optional retention cleanup can keep only the latest `N` local files per plugin using `download.retention_keep_latest`, and prunes only files recorded in that plugin's own history under the configured download directory.
- `logging.jsonl_log_file` adds newline-delimited JSON records alongside the human log, which is useful for scheduler parsing or later automation.
- Direct CLI and TUI launches now emit startup warnings when they detect risky setup issues such as running outside a virtualenv, missing `aria2c`, torrent preference without `aria2`, empty plugin loads, or unusable Ventoy detection settings.
- `Setup-DistroHunter.ps1` and `Update-Ventoy.ps1` try to reuse an existing `aria2c` first and otherwise cache a portable Windows build under `tools/aria2`. The Python runtime auto-downloads to the same location if neither the scripts nor a manual install have placed one there.
- Plugin state now tracks persistent health metadata including last status, last success or failure timestamps, consecutive failure count, and the last seen error.
- Discovery now writes explicit version-delta log lines such as `old -> new` when a plugin’s selected release changes.
- The state file now keeps a capped per-plugin history of selection, download, and health changes so version churn is visible over time without letting the state file grow without bound.
- The state file also keeps mirror-host memory so flaky download sources can cool off between scheduled runs instead of being retried first every time.
- Ventoy sync is non-destructive by default. Set `"prune_removed": true` only if you want the tool to remove stale image files from the Ventoy target folder.
- SteamOS recovery downloads now decompress automatically from `.img.bz2` to `.img` after download, and Ventoy sync copies the decompressed `.img`.
- FydeOS PC downloads now extract a single raw disk image from the official `.bin.zip` archive and rename it to `.img` so it can be routed with the normal Ventoy copy rules.
- The default Ventoy copy filter now includes `.iso` and `.img`, and the default destination tree is `ISO/Linux`.
- Relative paths in the JSON config are resolved from the config file location.
- The state file now stores download paths relative to your configured download directory and migrates older absolute-path records on load.
- Persisted download state now reflects whether the artifact is actually present in the local library, so reports stay aligned with what is in `downloads/` after revalidation-only runs.
- Scheduled runs now append to `logs/distro_hunter.log` and failed mirror attempts are also copied to `logs/mirror_failures.log`.
- `backup` creates a timestamped source zip in `backups/`, excluding downloaded payloads and cache folders.
- `run` and `tui` now sync completed artifacts to Ventoy as they become available, so a later slow mirror or timeout does not block already-finished images from being copied.
- `tui` opens an interactive selector with a plugin filter box, persistent selection across filter changes, progress bars for discovery and downloads, and cooperative cancel support for long runs. Press `/` to jump to the filter box, `Esc` to clear it, and `c` to request cancellation.

## Manual Sources

- Bazzite is intentionally documented as a manual source instead of an auto-plugin target.
- Official page: https://bazzite.gg/#image-picker
- Reason: the official download flow is an interactive image picker that asks for hardware, desktop, and install-style choices before presenting the final artifact, so there is no single stable "best ISO" URL for the tool to discover safely.
- Recommended workflow: use the official Bazzite picker to choose the exact build you want, download it manually, then place the resulting image in your configured download folder so Distro Hunter can still copy it to Ventoy on the next sync.
- If you want those files routed somewhere better than the generic `manual` bucket, add a `ventoy.manual_sources` rule such as `{"pattern": "bazzite-*.iso", "family": "bazzite", "edition_type": "desktop"}`.

## Sample Sources

The built-in plugins currently target these official pages:

- https://archlinux.org/download/
- https://repo.almalinux.org/almalinux/10/live/x86_64/
- https://www.alpinelinux.org/downloads/
- https://chimeraos.org/download
- https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/
- https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/
- https://cdimage.ubuntu.com/edubuntu/releases/24.04/release/
- https://endeavouros.com/latest-release/
- https://fedoraproject.org/en/workstation/download/
- https://fedoraproject.org/en/kde/download/
- https://fedoraproject.org/en/spins/
- https://fydeos.io/download/pc/intel-iris/
- https://fydeos.io/download/pc/intel-slim/
- https://fydeos.io/download/pc/apu/
- https://forum.garudalinux.org/c/announcements/iso-releases/
- https://www.kali.org/get-kali/
- https://linuxmint.com/download.php
- https://system76.com/pop/download/
- https://cdimage.ubuntu.com/kubuntu/releases/24.04/release/
- https://cdimage.ubuntu.com/lubuntu/releases/24.04/release/
- https://manjaro.org/products/download/x86
- https://nixos.org/download/
- https://nobaraproject.org/download-nobara/
- https://download.opensuse.org/tumbleweed/iso/
- https://download.rockylinux.org/pub/rocky/9/isos/x86_64/
- https://store.steampowered.com/steamos/download?ver=custom
- https://www.system-rescue.org/Download/
- https://cdimage.ubuntu.com/ubuntu-budgie/releases/24.04/release/
- https://cdimage.ubuntu.com/ubuntucinnamon/releases/24.04/release/
- https://ubuntu.com/download/desktop
- https://ubuntu.com/download/server
- https://cdimage.ubuntu.com/ubuntu-mate/releases/24.04/release/
- https://cdimage.ubuntu.com/ubuntustudio/releases/24.04/release/
- https://cdimage.ubuntu.com/xubuntu/releases/24.04/release/
- https://zorin.com/os/download/
- https://help.zorin.com/docs/getting-started/getting-zorin-os-lite/
