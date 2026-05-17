from __future__ import annotations

import ctypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from distro_hunter.config import VentoySettings
from distro_hunter.plugin_metadata import PluginMetadata, infer_plugin_metadata, metadata_subdir
from distro_hunter.utils import ensure_directory


DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3


@dataclass(slots=True)
class DriveInfo:
    root: Path
    label: str
    drive_type: int
    score: int


def _iter_windows_roots() -> list[Path]:
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    roots: list[Path] = []
    for index in range(26):
        if bitmask & (1 << index):
            roots.append(Path(f"{chr(65 + index)}:/"))
    return roots


def _label_for_root(root: Path) -> str:
    volume_name = ctypes.create_unicode_buffer(261)
    file_system_name = ctypes.create_unicode_buffer(261)
    ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(str(root)),
        volume_name,
        len(volume_name),
        None,
        None,
        None,
        file_system_name,
        len(file_system_name),
    )
    return volume_name.value


def _drive_type(root: Path) -> int:
    return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(str(root)))


def detect_ventoy_drive(settings: VentoySettings) -> DriveInfo | None:
    candidates: list[DriveInfo] = []
    labels = {label.casefold() for label in settings.volume_labels}
    for root in _iter_windows_roots():
        drive_type = _drive_type(root)
        if drive_type not in {DRIVE_REMOVABLE, DRIVE_FIXED}:
            continue

        label = _label_for_root(root)
        score = 0
        if label and label.casefold() in labels:
            score += 50
        for marker in settings.marker_paths:
            if (root / marker).exists():
                score += 25
        if drive_type == DRIVE_REMOVABLE:
            score += 5
        if score:
            candidates.append(DriveInfo(root=root, label=label, drive_type=drive_type, score=score))

    if not candidates:
        return None
    return sorted(candidates, key=lambda entry: entry.score, reverse=True)[0]


def infer_plugin_subdir(plugin_slug: str, metadata: PluginMetadata | None = None) -> Path:
    return metadata_subdir(metadata or infer_plugin_metadata(plugin_slug))


def _target_for_source(
    source: Path,
    destination_root: Path,
    settings: VentoySettings,
    route_map: dict[Path, Path] | None,
) -> Path:
    if not settings.organize_by_plugin:
        return destination_root / source.name

    planned_subdir = None
    if route_map:
        try:
            planned_subdir = route_map.get(source.resolve())
        except OSError:
            planned_subdir = route_map.get(source)

    relative_subdir = planned_subdir or Path(settings.manual_subdir)
    return destination_root / relative_subdir / source.name


def _should_copy_source(source: Path, target: Path) -> bool:
    if not target.exists():
        return True
    target_stat = target.stat()
    source_stat = source.stat()
    return (
        target_stat.st_size != source_stat.st_size
        or int(target_stat.st_mtime) < int(source_stat.st_mtime)
    )


def sync_paths_to_ventoy(
    sources: Iterable[Path],
    drive: DriveInfo,
    settings: VentoySettings,
    *,
    route_map: dict[Path, Path] | None = None,
) -> list[Path]:
    copied: list[Path] = []
    destination = drive.root / settings.destination_subdir if settings.destination_subdir else drive.root
    ensure_directory(destination)

    allowed_extensions = tuple(entry.lower() for entry in settings.copy_extensions)
    seen_sources: set[Path] = set()
    ordered_sources: list[Path] = []
    for source in sources:
        try:
            resolved = source.resolve()
        except OSError:
            resolved = source
        if resolved in seen_sources:
            continue
        seen_sources.add(resolved)
        ordered_sources.append(resolved)

    for source in sorted(ordered_sources):
        if not source.is_file() or not source.name.lower().endswith(allowed_extensions):
            continue
        target = _target_for_source(source, destination, settings, route_map)
        ensure_directory(target.parent)
        if _should_copy_source(source, target):
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def sync_directory_to_ventoy(
    source_dir: Path,
    drive: DriveInfo,
    settings: VentoySettings,
    *,
    route_map: dict[Path, Path] | None = None,
) -> list[Path]:
    destination = drive.root / settings.destination_subdir if settings.destination_subdir else drive.root
    ensure_directory(destination)

    wanted_files: set[Path] = set()
    allowed_extensions = tuple(entry.lower() for entry in settings.copy_extensions)
    sources: list[Path] = []
    for source in sorted(source_dir.iterdir()):
        if not source.is_file() or not source.name.lower().endswith(allowed_extensions):
            continue
        sources.append(source)
        target = _target_for_source(source, destination, settings, route_map)
        wanted_files.add(target)
    copied = sync_paths_to_ventoy(sources, drive, settings, route_map=route_map)

    if settings.prune_removed:
        for existing in destination.rglob("*"):
            if existing.is_file() and existing.name.lower().endswith(allowed_extensions) and existing not in wanted_files:
                existing.unlink()
        for existing in sorted(destination.rglob("*"), key=lambda entry: len(entry.parts), reverse=True):
            if existing.is_dir():
                try:
                    existing.rmdir()
                except OSError:
                    pass
    return copied
