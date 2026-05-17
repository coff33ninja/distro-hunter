from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from distro_hunter.utils import ensure_directory


EXCLUDED_PARTS = {"backups", "downloads", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc"}


def should_include(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def create_source_backup(root_dir: Path, backup_dir: Path | None = None) -> Path:
    backup_root = ensure_directory(backup_dir or (root_dir / "backups"))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / f"distro-hunter-src-{timestamp}.zip"

    with ZipFile(backup_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(root_dir.rglob("*")):
            if path.is_dir() or not should_include(path.relative_to(root_dir)):
                continue
            archive.write(path, arcname=path.relative_to(root_dir))
    return backup_path
