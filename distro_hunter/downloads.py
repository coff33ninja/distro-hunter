from __future__ import annotations

import bz2
import subprocess
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

from distro_hunter.checksums import ExpectedChecksum, resolve_expected_checksum, verify_file_checksum
from distro_hunter.config import Settings
from distro_hunter.exceptions import (
    ChecksumMismatchError,
    ChecksumUnavailableError,
    DownloadAttemptError,
)
from distro_hunter.models import Candidate, ChecksumResult, DownloadResult, RemoteFileInfo
from distro_hunter.state import StateStore
from distro_hunter.utils import ensure_directory, extract_filename
from distro_hunter.web import WebClient


class DownloadManager:
    def __init__(self, settings: Settings, state: StateStore) -> None:
        self.settings = settings
        self.state = state
        self.web = WebClient(
            user_agent=settings.download.user_agent,
            timeout_seconds=settings.download.timeout_seconds,
            retry_attempts=settings.download.retry_attempts,
            retry_backoff_seconds=settings.download.retry_backoff_seconds,
            page_cache_dir=settings.download.page_cache_dir,
            page_cache_ttl_seconds=settings.download.page_cache_ttl_seconds,
        )
        ensure_directory(settings.download.download_dir)

    def _collision_safe_filename(self, plugin_slug: str, filename: str) -> str:
        return f"{plugin_slug}--{filename}"

    def _record_remote_identifier(self, record: dict | None) -> str | None:
        if not isinstance(record, dict):
            return None
        download = record.get("download", {})
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

    def _resolve_local_path(self, path_text: str | None) -> Path | None:
        if not path_text:
            return None
        path = Path(path_text)
        if path.is_absolute():
            return path.resolve()
        return (self.settings.download.download_dir / path).resolve()

    def _is_within_download_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.settings.download.download_dir.resolve())
            return True
        except ValueError:
            return False

    def _choose_destination(self, plugin_slug: str, filename: str, remote: RemoteFileInfo) -> Path:
        download_dir = self.settings.download.download_dir
        default_filename = Path(filename).name
        default_path = download_dir / default_filename
        if not self.settings.download.protect_filename_collisions:
            return default_path

        current_record = self.state.get_plugin_record(plugin_slug).get("download", {})
        current_path_text = current_record.get("path") if isinstance(current_record, dict) else None
        collision_filename = self._collision_safe_filename(plugin_slug, default_filename)

        if isinstance(current_path_text, str):
            current_name = Path(current_path_text).name
            if current_name in {default_filename, collision_filename}:
                return download_dir / current_path_text

        owner = self.state.find_download_owner(default_filename, excluding_plugin=plugin_slug)
        if owner is not None:
            _, owner_record = owner
            owner_remote = self._record_remote_identifier(owner_record)
            current_remote = remote.final_url or remote.url
            if not owner_remote or not current_remote or owner_remote != current_remote:
                return download_dir / collision_filename

        if default_path.exists() and isinstance(current_path_text, str) and current_path_text != default_filename:
            return download_dir / collision_filename
        return default_path

    def _apply_retention(self, plugin_slug: str, current_path: Path) -> list[Path]:
        keep_latest = max(0, int(self.settings.download.retention_keep_latest))
        if keep_latest <= 0:
            return []

        current_resolved = current_path.resolve()
        ordered: list[Path] = [current_resolved]
        seen: set[Path] = {current_resolved}
        for path_text in self.state.download_history_paths(plugin_slug):
            candidate = self._resolve_local_path(path_text)
            if candidate is None:
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            ordered.append(resolved)

        pruned: list[Path] = []
        for stale_path in ordered[keep_latest:]:
            if not stale_path.exists() or not stale_path.is_file():
                continue
            if not self._is_within_download_dir(stale_path):
                continue
            stale_path.unlink()
            pruned.append(stale_path)
        return pruned

    def _remote_info(self, candidate: Candidate) -> RemoteFileInfo:
        try:
            headers, final_url = self.web.inspect_remote_file(candidate.url)
        except Exception:
            filename = candidate.filename or extract_filename(candidate.url)
            return RemoteFileInfo(
                url=candidate.url,
                final_url=candidate.url,
                filename=filename,
            )

        filename = candidate.filename or extract_filename(final_url) or extract_filename(candidate.url)
        size_header = headers.get("Content-Length")
        return RemoteFileInfo(
            url=candidate.url,
            final_url=final_url,
            filename=filename,
            size=int(size_header) if size_header and size_header.isdigit() else None,
            etag=headers.get("ETag"),
            last_modified=headers.get("Last-Modified"),
        )

    def _resolve_expected_checksum(self, candidate: Candidate, remote: RemoteFileInfo) -> object | None:
        if not self.settings.download.verify_checksums:
            return None
        return resolve_expected_checksum(self.web, candidate, remote)

    def _verification_unavailable(self) -> ChecksumResult:
        return ChecksumResult(status="unavailable")

    def _verify_local_artifact(self, local_path: Path, expected_checksum: object | None) -> ChecksumResult:
        if not self.settings.download.verify_checksums:
            return self._verification_unavailable()
        if expected_checksum is None:
            if self.settings.download.require_checksums:
                raise ChecksumUnavailableError("checksum required but unavailable")
            return self._verification_unavailable()
        return verify_file_checksum(local_path, expected_checksum)

    def _cached_verified_checksum(
        self,
        plugin_slug: str,
        local_path: Path,
        expected_checksum: object | None,
    ) -> ChecksumResult | None:
        if not isinstance(expected_checksum, ExpectedChecksum):
            return None
        if not local_path.exists():
            return None

        record = self.state.get_plugin_record(plugin_slug).get("download", {})
        if not isinstance(record, dict):
            return None
        checksum = record.get("checksum", {})
        if not isinstance(checksum, dict):
            return None
        if checksum.get("status") != "verified":
            return None
        if checksum.get("algorithm") != expected_checksum.algorithm:
            return None
        expected_digest = expected_checksum.digest.lower()
        if checksum.get("expected") != expected_digest or checksum.get("actual") != expected_digest:
            return None
        if checksum.get("source") != expected_checksum.source:
            return None

        stat = local_path.stat()
        if checksum.get("file_size") != stat.st_size:
            return None
        if checksum.get("file_mtime_ns") != stat.st_mtime_ns:
            return None

        return ChecksumResult(
            status="verified",
            algorithm=expected_checksum.algorithm,
            expected=expected_digest,
            actual=expected_digest,
            source=expected_checksum.source,
        )

    def _should_download(
        self,
        plugin_slug: str,
        local_path: Path,
        remote: RemoteFileInfo,
        expected_checksum: object | None,
    ) -> tuple[bool, str | None, ChecksumResult | None]:
        if not local_path.exists():
            return True, None, None

        if remote.size is not None and local_path.stat().st_size != remote.size:
            return True, None, None

        record = self.state.get_plugin_record(plugin_slug).get("download", {})
        previous = record.get("remote", {})
        if remote.etag and previous.get("etag") and remote.etag != previous.get("etag"):
            return True, None, None
        if remote.last_modified and previous.get("last_modified") and remote.last_modified != previous.get("last_modified"):
            return True, None, None

        cached_checksum = self._cached_verified_checksum(plugin_slug, local_path, expected_checksum)
        if cached_checksum is not None:
            return False, "local file matches remote metadata", cached_checksum

        try:
            checksum = self._verify_local_artifact(local_path, expected_checksum)
        except ChecksumMismatchError:
            return True, None, None
        return False, "local file matches remote metadata", checksum

    def _download_with_aria2(self, candidate: Candidate, destination: Path, progress_callback=None) -> None:
        aria2_path = self.settings.download.aria2_path
        if aria2_path is None:
            raise RuntimeError("aria2_path is not configured")

        command = [
            str(aria2_path),
            f"--dir={destination.parent}",
            f"--out={destination.name}",
            f"--max-connection-per-server={self.settings.download.connections_per_server}",
            f"--split={self.settings.download.split}",
            "--continue=true",
            "--allow-overwrite=true",
            "--file-allocation=none",
            candidate.url,
        ]

        if self.settings.download.prefer_torrent:
            if candidate.magnet_url:
                command[-1] = candidate.magnet_url
                command.remove(f"--out={destination.name}")
            elif candidate.torrent_url:
                command[-1] = candidate.torrent_url
                command.remove(f"--out={destination.name}")

        if progress_callback:
            progress_callback(0, None, destination.name)
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "aria2 download failed")
        if progress_callback:
            progress_callback(1, 1, destination.name)

    def _download_builtin(self, url: str, destination: Path, progress_callback=None) -> None:
        temp_path = destination.with_suffix(destination.suffix + ".part")
        self.web.download(url, str(temp_path), progress_callback=progress_callback)
        temp_path.replace(destination)

    def _decompress_bz2(self, archive_path: Path, progress_callback=None) -> Path:
        output_path = archive_path.with_suffix("")
        archive_stat = archive_path.stat()
        if output_path.exists():
            output_stat = output_path.stat()
            if output_stat.st_size > 0 and int(output_stat.st_mtime) >= int(archive_stat.st_mtime):
                return output_path

        temp_path = output_path.parent / f"{output_path.name}.part"
        total = archive_stat.st_size
        try:
            with open(archive_path, "rb") as compressed_handle, bz2.BZ2File(compressed_handle, "rb") as archive, open(
                temp_path, "wb"
            ) as output_handle:
                while True:
                    chunk = archive.read(1024 * 1024)
                    if not chunk:
                        break
                    output_handle.write(chunk)
                    if progress_callback:
                        progress_callback(compressed_handle.tell(), total, output_path.name)
            temp_path.replace(output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return output_path

    def _extract_zip_disk_image(self, archive_path: Path, progress_callback=None) -> Path:
        archive_stat = archive_path.stat()
        with ZipFile(archive_path) as archive:
            image_members = [
                info
                for info in archive.infolist()
                if not info.is_dir() and Path(info.filename).suffix.lower() in {".img", ".bin"}
            ]
            if len(image_members) != 1:
                return archive_path

            member = image_members[0]
            member_name = Path(member.filename).name
            output_path = archive_path.with_suffix("")
            if output_path.suffix.lower() == ".bin":
                output_path = output_path.with_suffix(".img")
            elif output_path.name != member_name:
                output_path = archive_path.parent / member_name
                if output_path.suffix.lower() == ".bin":
                    output_path = output_path.with_suffix(".img")

            if output_path.exists():
                output_stat = output_path.stat()
                if output_stat.st_size > 0 and int(output_stat.st_mtime) >= int(archive_stat.st_mtime):
                    return output_path

            temp_path = output_path.parent / f"{output_path.name}.part"
            try:
                with archive.open(member, "r") as member_handle, open(temp_path, "wb") as output_handle:
                    extracted = 0
                    total = member.file_size
                    while True:
                        chunk = member_handle.read(1024 * 1024)
                        if not chunk:
                            break
                        output_handle.write(chunk)
                        extracted += len(chunk)
                        if progress_callback:
                            progress_callback(extracted, total, output_path.name)
                temp_path.replace(output_path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            return output_path

    def _finalize_local_artifact(self, local_path: Path, progress_callback=None) -> Path:
        if self.settings.download.decompress_bz2 and local_path.name.lower().endswith(".bz2") and local_path.exists():
            return self._decompress_bz2(local_path, progress_callback=progress_callback)
        if local_path.name.lower().endswith(".zip") and local_path.exists():
            return self._extract_zip_disk_image(local_path, progress_callback=progress_callback)
        return local_path

    def process(self, plugin_slug: str, candidate: Candidate, *, dry_run: bool = False, progress_callback=None) -> DownloadResult:
        remote = self._remote_info(candidate)
        filename = remote.filename or candidate.filename or f"{plugin_slug}.iso"
        local_path = self._choose_destination(plugin_slug, filename, remote)
        expected_checksum = self._resolve_expected_checksum(candidate, remote)

        should_download, skipped_reason, checksum_result = self._should_download(plugin_slug, local_path, remote, expected_checksum)
        selected = replace(candidate, filename=local_path.name)
        if not should_download:
            final_path = self._finalize_local_artifact(local_path, progress_callback=progress_callback)
            pruned_paths = self._apply_retention(plugin_slug, final_path) if final_path.exists() else []
            if progress_callback and final_path == local_path:
                progress_callback(1, 1, final_path.name)
            return DownloadResult(
                plugin_slug=plugin_slug,
                candidate=selected,
                path=final_path,
                downloaded=False,
                skipped_reason=skipped_reason,
                remote=remote,
                checksum=checksum_result,
                pruned_paths=pruned_paths,
            )

        if dry_run:
            if progress_callback:
                progress_callback(1, 1, local_path.name)
            return DownloadResult(
                plugin_slug=plugin_slug,
                candidate=selected,
                path=local_path,
                downloaded=False,
                skipped_reason="dry run",
                remote=remote,
                checksum=checksum_result,
            )

        try:
            if (
                self.settings.download.prefer_aria2
                and self.settings.download.aria2_path
                and self.settings.download.aria2_path.exists()
            ):
                self._download_with_aria2(selected, local_path, progress_callback=progress_callback)
            else:
                self._download_builtin(
                    selected.url,
                    local_path,
                    progress_callback=(
                        (lambda downloaded, total: progress_callback(downloaded, total, filename))
                        if progress_callback
                        else None
                    ),
                )

            checksum_result = self._verify_local_artifact(local_path, expected_checksum)
            final_path = self._finalize_local_artifact(local_path, progress_callback=progress_callback)
        except Exception as exc:
            if local_path.exists():
                local_path.unlink()
            raise DownloadAttemptError(str(exc), candidate=selected, remote=remote) from exc

        pruned_paths = self._apply_retention(plugin_slug, final_path) if final_path.exists() else []
        return DownloadResult(
            plugin_slug=plugin_slug,
            candidate=selected,
            path=final_path,
            downloaded=True,
            remote=remote,
            checksum=checksum_result,
            pruned_paths=pruned_paths,
        )
