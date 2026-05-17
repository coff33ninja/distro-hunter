from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Candidate:
    url: str
    filename: str | None = None
    version: str | None = None
    arch: str | None = None
    source_page: str | None = None
    torrent_url: str | None = None
    magnet_url: str | None = None
    notes: str | None = None
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RemoteFileInfo:
    url: str
    final_url: str
    filename: str | None = None
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass(slots=True)
class ChecksumResult:
    status: str
    algorithm: str | None = None
    expected: str | None = None
    actual: str | None = None
    source: str | None = None


@dataclass(slots=True)
class DownloadResult:
    plugin_slug: str
    candidate: Candidate
    path: Path | None
    downloaded: bool
    skipped_reason: str | None = None
    remote: RemoteFileInfo | None = None
    checksum: ChecksumResult | None = None
    pruned_paths: list[Path] = field(default_factory=list)


VALID_STATUS_UP_TO_DATE = "up_to_date"
VALID_STATUS_OUTDATED = "outdated"
VALID_STATUS_FILE_MISSING = "file_missing"
VALID_STATUS_NO_RECORD = "no_download_record"
VALID_STATUS_ERROR = "error"


@dataclass(slots=True)
class ValidateResult:
    plugin_slug: str
    plugin_name: str
    status: str
    downloaded_filename: str | None = None
    discovered_filename: str | None = None
    downloaded_url: str | None = None
    discovered_url: str | None = None
    downloaded_version: str | None = None
    discovered_version: str | None = None
    downloaded_at: str | None = None
    file_exists: bool = False
    error: str | None = None
