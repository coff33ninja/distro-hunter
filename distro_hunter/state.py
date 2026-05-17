from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from distro_hunter.models import Candidate, DownloadResult
from distro_hunter.utils import ensure_directory

STATE_VERSION = 7
MAX_HISTORY_EVENTS = 50


class StateStore:
    def __init__(self, path: Path, download_dir: Path | None = None) -> None:
        self.path = path
        self.download_dir = download_dir.resolve() if download_dir else None
        self.data = {"state_version": STATE_VERSION, "plugins": {}, "mirrors": {}}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        if self._migrate():
            self.save()

    def save(self) -> None:
        ensure_directory(self.path.parent)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get_plugin_record(self, plugin_slug: str) -> dict:
        plugins = self.data.setdefault("plugins", {})
        return plugins.setdefault(plugin_slug, {})

    def _mirror_records(self) -> dict[str, dict]:
        mirrors = self.data.setdefault("mirrors", {})
        if not isinstance(mirrors, dict):
            mirrors = {}
            self.data["mirrors"] = mirrors
        return mirrors

    def mirror_host_for_url(self, url: str | None) -> str | None:
        if not url:
            return None
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        return host.lower() if host else None

    def _lookup_mirror_record(self, url: str | None) -> dict | None:
        host = self.mirror_host_for_url(url)
        if host is None:
            return None
        return self._mirror_records().get(host)

    def _get_or_create_mirror_record(self, url: str | None) -> tuple[str | None, dict | None]:
        host = self.mirror_host_for_url(url)
        if host is None:
            return None, None
        return host, self._mirror_records().setdefault(host, {})

    def _parse_timestamp(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _append_history_event(self, plugin_slug: str, *, event: str, payload: dict[str, object]) -> None:
        record = self.get_plugin_record(plugin_slug)
        history = record.setdefault("history", [])
        entry = {"event": event, **payload}
        if history:
            previous = dict(history[-1])
            previous.pop("recorded_at", None)
            if previous == entry:
                return

        history.append(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                **entry,
            }
        )
        if len(history) > MAX_HISTORY_EVENTS:
            del history[:-MAX_HISTORY_EVENTS]

    def remember_selection(self, plugin_slug: str, candidate: Candidate) -> None:
        record = self.get_plugin_record(plugin_slug)
        record["selection"] = {
            "url": candidate.url,
            "filename": candidate.filename,
            "version": candidate.version,
            "selected_at": datetime.now(UTC).isoformat(),
        }
        self._append_history_event(
            plugin_slug,
            event="selection",
            payload={
                "url": candidate.url,
                "filename": candidate.filename,
                "version": candidate.version,
            },
        )

    def remember_health(
        self,
        plugin_slug: str,
        *,
        status: str,
        healthy: bool,
        error: str | None = None,
    ) -> dict[str, object]:
        record = self.get_plugin_record(plugin_slug)
        health = record.setdefault("health", {})
        checked_at = datetime.now(UTC).isoformat()
        previous_failures = health.get("failure_count", 0)
        if not isinstance(previous_failures, int):
            previous_failures = 0

        health["healthy"] = healthy
        health["last_status"] = status
        health["last_checked_at"] = checked_at
        if healthy:
            health["last_success_at"] = checked_at
            health["failure_count"] = 0
            health["last_error"] = None
        else:
            health["last_failure_at"] = checked_at
            health["failure_count"] = previous_failures + 1
            health["last_error"] = error or status
        self._append_history_event(
            plugin_slug,
            event="health",
            payload={
                "healthy": healthy,
                "status": status,
                "error": health["last_error"],
            },
        )
        return dict(health)

    def _normalize_download_path(self, path_text: str | None, filename: str | None) -> str | None:
        if path_text:
            path = Path(path_text)
            if not path.is_absolute():
                return path.as_posix()
            if self.download_dir:
                try:
                    return path.resolve().relative_to(self.download_dir).as_posix()
                except (OSError, ValueError):
                    pass
            if filename:
                return Path(filename).name
            return path.name or None
        if filename:
            return Path(filename).name
        return None

    def _resolve_download_artifact_path(self, path_text: str | None, filename: str | None) -> Path | None:
        normalized = self._normalize_download_path(path_text, filename)
        if not normalized:
            return None

        path = Path(normalized)
        if path.is_absolute():
            try:
                return path.resolve()
            except OSError:
                return path

        if self.download_dir is not None:
            try:
                return (self.download_dir / path).resolve()
            except OSError:
                return self.download_dir / path
        return path

    def _download_artifact_exists(self, path_text: str | None, filename: str | None) -> bool:
        artifact_path = self._resolve_download_artifact_path(path_text, filename)
        if artifact_path is None:
            return False
        try:
            return artifact_path.exists() and artifact_path.is_file()
        except OSError:
            return False

    def _migrate(self) -> bool:
        changed = False
        if self.data.get("state_version") != STATE_VERSION:
            self.data["state_version"] = STATE_VERSION
            changed = True

        plugins = self.data.setdefault("plugins", {})
        if not isinstance(self.data.get("mirrors"), dict):
            self.data["mirrors"] = {}
            changed = True
        for record in plugins.values():
            download = record.get("download")
            if not isinstance(download, dict):
                continue
            normalized_path = self._normalize_download_path(download.get("path"), download.get("filename"))
            if download.get("path") != normalized_path:
                download["path"] = normalized_path
                changed = True
            if normalized_path:
                normalized_filename = Path(normalized_path).name
                if download.get("filename") != normalized_filename:
                    download["filename"] = normalized_filename
                    changed = True
            artifact_exists = self._download_artifact_exists(normalized_path, download.get("filename"))
            if download.get("downloaded") != artifact_exists:
                download["downloaded"] = artifact_exists
                changed = True
        return changed

    def mirror_backoff_until(self, url: str | None) -> datetime | None:
        record = self._lookup_mirror_record(url)
        if not record:
            return None
        backoff_until = self._parse_timestamp(record.get("backoff_until"))
        if backoff_until is None:
            return None
        now = datetime.now(UTC)
        if backoff_until <= now:
            return None
        return backoff_until

    def prioritize_mirror_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        def sort_key(item: tuple[int, Candidate]) -> tuple[int, float, int]:
            index, candidate = item
            backoff_until = self.mirror_backoff_until(candidate.url)
            return (
                1 if backoff_until else 0,
                backoff_until.timestamp() if backoff_until else 0,
                index,
            )

        return [candidate for _, candidate in sorted(enumerate(candidates), key=sort_key)]

    def remember_mirror_failure(
        self,
        url: str | None,
        *,
        error: str,
        backoff_base_seconds: int,
        backoff_cap_seconds: int,
    ) -> None:
        _, record = self._get_or_create_mirror_record(url)
        if record is None or url is None:
            return
        now = datetime.now(UTC)
        previous_failures = record.get("failure_count", 0)
        if not isinstance(previous_failures, int):
            previous_failures = 0
        failure_count = previous_failures + 1
        base_seconds = max(0, int(backoff_base_seconds))
        cap_seconds = max(base_seconds, int(backoff_cap_seconds))
        delay_seconds = 0
        if base_seconds > 0:
            delay_seconds = min(base_seconds * (2 ** (failure_count - 1)), cap_seconds)
        record["last_url"] = url
        record["failure_count"] = failure_count
        record["last_failure_at"] = now.isoformat()
        record["last_error"] = error
        record["backoff_until"] = (now + timedelta(seconds=delay_seconds)).isoformat() if delay_seconds > 0 else None

    def remember_mirror_success(self, url: str | None) -> None:
        _, record = self._get_or_create_mirror_record(url)
        if record is None or url is None:
            return
        record["last_url"] = url
        record["last_success_at"] = datetime.now(UTC).isoformat()
        record["failure_count"] = 0
        record["last_error"] = None
        record["backoff_until"] = None

    def current_download_remote(self, plugin_slug: str) -> str | None:
        download = self.get_plugin_record(plugin_slug).get("download", {})
        if not isinstance(download, dict):
            return None
        remote = download.get("remote", {})
        if not isinstance(remote, dict):
            return None
        final_url = remote.get("final_url")
        if isinstance(final_url, str) and final_url:
            return final_url
        url = remote.get("url")
        if isinstance(url, str) and url:
            return url
        return None

    def find_download_owner(self, path_text: str, *, excluding_plugin: str | None = None) -> tuple[str, dict] | None:
        target = self._normalize_download_path(path_text, Path(path_text).name)
        if not target:
            return None
        for plugin_slug, record in self.data.setdefault("plugins", {}).items():
            if excluding_plugin and plugin_slug == excluding_plugin:
                continue
            download = record.get("download", {})
            if not isinstance(download, dict):
                continue
            current = self._normalize_download_path(download.get("path"), download.get("filename"))
            if current == target:
                return plugin_slug, record
        return None

    def download_history_paths(self, plugin_slug: str) -> list[str]:
        record = self.get_plugin_record(plugin_slug)
        paths: list[str] = []
        seen: set[str] = set()

        current = record.get("download", {})
        if isinstance(current, dict):
            current_path = self._normalize_download_path(current.get("path"), current.get("filename"))
            if current_path and current_path not in seen:
                seen.add(current_path)
                paths.append(current_path)

        history = record.get("history", [])
        if not isinstance(history, list):
            return paths

        for entry in reversed(history):
            if not isinstance(entry, dict) or entry.get("event") != "download":
                continue
            path_text = self._normalize_download_path(entry.get("path"), entry.get("filename"))
            if not path_text or path_text in seen:
                continue
            seen.add(path_text)
            paths.append(path_text)
        return paths

    def remember_download(self, result: DownloadResult) -> None:
        record = self.get_plugin_record(result.plugin_slug)
        filename = result.path.name if result.path else result.candidate.filename
        normalized_path = self._normalize_download_path(str(result.path) if result.path else None, filename)
        local_available = self._download_artifact_exists(normalized_path, filename)
        checksum_file_path = self._resolve_download_artifact_path(result.candidate.filename, result.candidate.filename)
        checksum_file_size = None
        checksum_file_mtime_ns = None
        if result.checksum and result.checksum.status == "verified" and checksum_file_path and checksum_file_path.exists():
            checksum_stat = checksum_file_path.stat()
            checksum_file_size = checksum_stat.st_size
            checksum_file_mtime_ns = checksum_stat.st_mtime_ns
        record["download"] = {
            "path": normalized_path,
            "filename": filename,
            "downloaded": local_available,
            "skipped_reason": result.skipped_reason,
            "updated_at": datetime.now(UTC).isoformat(),
            "remote": {
                "url": result.remote.url if result.remote else result.candidate.url,
                "final_url": result.remote.final_url if result.remote else result.candidate.url,
                "filename": result.remote.filename if result.remote else result.candidate.filename,
                "size": result.remote.size if result.remote else None,
                "etag": result.remote.etag if result.remote else None,
                "last_modified": result.remote.last_modified if result.remote else None,
            },
            "checksum": {
                "status": result.checksum.status if result.checksum else None,
                "algorithm": result.checksum.algorithm if result.checksum else None,
                "expected": result.checksum.expected if result.checksum else None,
                "actual": result.checksum.actual if result.checksum else None,
                "source": result.checksum.source if result.checksum else None,
                "file_size": checksum_file_size,
                "file_mtime_ns": checksum_file_mtime_ns,
            },
        }
        self._append_history_event(
            result.plugin_slug,
            event="download",
            payload={
                "path": record["download"]["path"],
                "filename": filename,
                "downloaded": local_available,
                "skipped_reason": result.skipped_reason,
                "checksum_status": result.checksum.status if result.checksum else None,
            },
        )
