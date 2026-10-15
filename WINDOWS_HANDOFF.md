# Windows ISO hunter — handoff

Windows variant of Distro Hunter. Reuses the existing engine (discover → download → Ventoy sync) with a separate catalog and profile.

## What exists
- `distro_hunter/plugins/windows_common.py` — `CATALOG` (single source of truth, Windows 1.x through 11 26H2, Windows Server 2000 through 2025). Pulls file lists from archive.org `/metadata/<item>`; candidates carry archive.org's SHA-1.
- `distro_hunter/plugins/windows_*.py` — generated stubs. Don't hand-edit.
- `scripts/gen_windows_plugins.py` — regenerates stubs and rewrites `plugins.builtin` in `config.windows.json` from `CATALOG`.
- `config.windows.json` — separate state (`state_windows/`), downloads (`downloads_windows/`), logs, `ISO/Windows` Ventoy dir, `.iso` and `.img` sync, `.7z` image extraction enabled, `prune_removed: false`.
- `distro_hunter/checksums.py` — added `sha1` to `ALGORITHM_LENGTHS` (direct-digest path only).
- `tests/test_windows_plugins.py`.

## Commands (from `H:\DATA\DISTRO`)
```powershell
.\.venv\Scripts\python.exe -m distro_hunter --config config.windows.json discover        # find only, no download
.\.venv\Scripts\python.exe -m distro_hunter --config config.windows.json run --dry-run
.\.venv\Scripts\python.exe -m distro_hunter --config config.windows.json run --plugin windows_11_24h2_x64
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
`--config` goes before the subcommand. `--plugin` takes one slug. Never run `run` unfiltered: the full set is hundreds of GB.

## Layout
Downloads land in `downloads_windows/`; sync moves images into `ISO/Windows/<product>/official/<arch>/` (Server uses `ISO/Windows/Windows Server/<release>/official/<arch>`). Sync also reconciles state-tracked images left in the sibling `downloads/` folder, but does not sweep unrelated files there. State paths follow successfully moved images. If a Ventoy target already exists, sync deletes the local source only after byte-for-byte verification; differing files or verification errors are retained and logged. If an image is locked, sync logs the failure and continues with other files; rerunning sync reconciles completed moves and retries the remaining images. Linux stays in `ISO/Linux/<family>/<edition>`; both coexist, and pruning is scoped to each root.
- Folder comes from `VENTOY_SUBDIR` in each plugin stub, computed by `ventoy_subdir()` in `windows_common.py`. For example: `Windows 11/official/x64`, `Windows 10/official/x86`, `Windows Server/2022/official/x64`. Architectures of a release are separated in the canonical library layout.
- Change the layout in `ventoy_subdir()`, then run `scripts\gen_windows_plugins.py` (stubs are generated, don't hand-edit).
- `.\Update-Ventoy.ps1 -Target Windows|Linux|All [-Plugin slug] [-DryRun]`; or `--config config.windows.json sync` to sync what's already downloaded.
- Tests: `tests/test_windows_sync.py` (layout + Windows/Linux side by side on one fake drive).

## Catalog behavior and limitations
- Windows 11 26H2 has Archive.org entries for x64 and ARM64. Rolling UUP Dump entries discover the newest matching build per release and architecture, including future Windows 11 releases; these are informational build links, not direct ISO downloads. A listed build is not a claim of general availability.
- Batch specs keep related disk images together: DOS 6.0 floppy disks, Windows 1.x–3.x floppy sets, NT 4.0 Enterprise, and Server 2003 R2. `.7z` legacy archives are extracted only for contained `.iso`/`.img` files; unsafe archive paths are rejected. The Windows profile syncs extracted `.img` files to Ventoy.
- During Ventoy sync, local `.7z` archives are extracted and their image files are routed alongside the archive's product. The archive is deleted only after every extracted image is present and verified at its Ventoy destination; extraction, sync, verification, or destination conflicts leave the archive available for retry.
- Pre-95 versions may be available as `.7z` archives from `vintage-versions-of-windows-1980s-1990s`; archive availability and member naming can change, so use `discover` before downloading.
- The 25H2 x64 Archive.org entry is a Media Creation Tool build (consumer editions only), not a VLSC/MSDN image.
- English only. Other languages exist in Archive.org items; add entries to `CATALOG` if wanted.
- Everything comes from third-party archive.org uploads; the sha1 only proves the file matches what the uploader published.
