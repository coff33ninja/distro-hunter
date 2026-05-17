from __future__ import annotations

import os
import re
from pathlib import Path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "plugin"


def deduplicate(items: list[str]) -> list[str]:
    """Remove duplicate strings while preserving order.
    
    Args:
        items: List of strings that may contain duplicates
        
    Returns:
        List with duplicates removed, order preserved
    """
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def extract_filename(url: str) -> str | None:
    """Extract filename from URL path.
    
    .. deprecated:: Use :func:`distro_hunter.url_utils.extract_filename` instead.
    
    Args:
        url: The URL to extract filename from
        
    Returns:
        The filename (HTML-unescaped) or None if path is empty
    """
    from distro_hunter.url_utils import extract_filename as url_extract_filename
    return url_extract_filename(url)


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def human_size(value: int | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
