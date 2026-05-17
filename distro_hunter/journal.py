from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from distro_hunter.config import LoggingSettings
from distro_hunter.utils import ensure_directory


class RunJournal:
    def __init__(self, settings: LoggingSettings) -> None:
        self.settings = settings

    def _timestamp(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _append_text(self, path: Path | None, timestamp: str, level: str, message: str) -> None:
        if path is None:
            return
        ensure_directory(path.parent)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} [{level}] {message}\n")

    def _append_jsonl(self, timestamp: str, level: str, message: str, **fields: object) -> None:
        path = self.settings.jsonl_log_file
        if path is None:
            return
        ensure_directory(path.parent)
        payload = {"timestamp": timestamp, "level": level, "message": message, **fields}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _append(self, level: str, message: str, **fields: object) -> None:
        timestamp = self._timestamp()
        self._append_text(self.settings.run_log_file, timestamp, level, message)
        self._append_jsonl(timestamp, level, message, **fields)

    def info(self, message: str) -> None:
        self._append("INFO", message)

    def warning(self, message: str) -> None:
        self._append("WARN", message)

    def error(self, message: str) -> None:
        self._append("ERROR", message)

    def mirror_failure(self, plugin_slug: str, url: str, error: str) -> None:
        message = f"{plugin_slug}: {url} -> {error}"
        timestamp = self._timestamp()
        self._append_text(self.settings.run_log_file, timestamp, "WARN", message)
        self._append_text(self.settings.mirror_failures_file, timestamp, "WARN", message)
        self._append_jsonl(
            timestamp,
            "WARN",
            message,
            event="mirror_failure",
            plugin_slug=plugin_slug,
            url=url,
            error=error,
        )
