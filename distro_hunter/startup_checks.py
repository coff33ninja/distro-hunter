from __future__ import annotations

import sys

from distro_hunter.config import Settings


def collect_startup_warnings(settings: Settings, *, plugin_count: int) -> list[str]:
    warnings: list[str] = []
    in_virtualenv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)

    if not in_virtualenv:
        warnings.append("Running outside a virtual environment; prefer .venv\\Scripts\\python.exe for scheduled and direct runs.")

    aria2_available = settings.download.aria2_path is not None and settings.download.aria2_path.exists()
    if settings.download.prefer_aria2 and not aria2_available:
        if settings.download.aria2_path is None:
            warnings.append(
                "prefer_aria2 is enabled but aria2c was not found and could not be auto-downloaded; "
                "downloads will fall back to Python. Run Setup-DistroHunter.ps1 or place aria2c under tools\\aria2."
            )
        else:
            warnings.append(
                f"prefer_aria2 is enabled but aria2_path was not found: {settings.download.aria2_path}. "
                "The app can also use aria2c from PATH or tools\\aria2 when available."
            )

    if settings.download.prefer_torrent and not aria2_available:
        warnings.append("prefer_torrent is enabled but aria2c is unavailable, so torrent and magnet downloads cannot be used.")

    if plugin_count <= 0:
        warnings.append("No plugins are currently loadable, so discover and run commands will have nothing to do.")

    if settings.ventoy.enabled and not settings.ventoy.volume_labels and not settings.ventoy.marker_paths:
        warnings.append("Ventoy detection is enabled but no volume labels or marker paths are configured.")

    return warnings
