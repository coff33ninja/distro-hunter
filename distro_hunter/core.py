from __future__ import annotations

from fnmatch import fnmatch
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from distro_hunter.config import PluginOverrideSettings, Settings
from distro_hunter.downloads import DownloadAttemptError, DownloadManager
from distro_hunter.journal import RunJournal
from distro_hunter.models import (
    VALID_STATUS_ERROR,
    VALID_STATUS_FILE_MISSING,
    VALID_STATUS_NO_RECORD,
    VALID_STATUS_OUTDATED,
    VALID_STATUS_UP_TO_DATE,
    Candidate,
    DownloadResult,
    RemoteFileInfo,
    ValidateResult,
)
from distro_hunter.plugin_metadata import infer_plugin_metadata, metadata_from_fields, metadata_subdir
from distro_hunter.plugin_loader import DiscoveryContext, PluginSpec, load_plugins
from distro_hunter.scoring import choose_best, rank_candidates, score_candidate
from distro_hunter.startup_checks import collect_startup_warnings
from distro_hunter.state import StateStore
from distro_hunter.utils import extract_filename
from distro_hunter.ventoy import detect_ventoy_drive, infer_plugin_subdir, sync_directory_to_ventoy, sync_paths_to_ventoy

DOCTOR_OK = "ok"
DOCTOR_NO_CANDIDATES = "no candidates"
DOCTOR_CHANGED_PAGE_SHAPE = "changed page shape"
DOCTOR_DOWNLOAD_HEAD_FAILED = "download head failed"


@dataclass(slots=True)
class DiscoverySelection:
    plugin: PluginSpec
    ranked: list[Candidate]
    selected: Candidate | None
    error: str | None = None


@dataclass(slots=True)
class DoctorResult:
    plugin: PluginSpec
    status: str
    selected: Candidate | None = None
    remote: RemoteFileInfo | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    health: dict[str, object] | None = None

    @property
    def healthy(self) -> bool:
        return self.status == DOCTOR_OK


class DistroHunter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = StateStore(settings.state_file, download_dir=settings.download.download_dir)
        self.context = DiscoveryContext(settings)
        self.plugins = load_plugins(settings)
        self.plugin_map = {plugin.slug: plugin for plugin in self.plugins}
        self.downloads = DownloadManager(settings, self.state)
        self.journal = RunJournal(settings.logging)

    def list_plugins(self) -> list[PluginSpec]:
        return self.plugins

    def startup_warnings(self) -> list[str]:
        return collect_startup_warnings(self.settings, plugin_count=len(self.plugins))

    def get_plugin(self, plugin: PluginSpec | str) -> PluginSpec:
        if isinstance(plugin, PluginSpec):
            return plugin
        return self.plugin_map[plugin]

    def _selection_delta_message(self, plugin_slug: str, selected: Candidate) -> str | None:
        previous = self.state.get_plugin_record(plugin_slug).get("selection", {})
        previous_version = previous.get("version")
        if previous_version and selected.version and previous_version != selected.version:
            return f"{plugin_slug}: version changed {previous_version} -> {selected.version}"

        previous_filename = previous.get("filename")
        if previous_filename and selected.filename and previous_filename != selected.filename:
            return f"{plugin_slug}: candidate changed {previous_filename} -> {selected.filename}"

        previous_url = previous.get("url")
        if previous_url and previous_url != selected.url:
            return f"{plugin_slug}: source changed {previous_url} -> {selected.url}"
        return None

    def _apply_plugin_overrides(self, plugin_slug: str, candidates: list[Candidate]) -> list[Candidate]:
        settings = getattr(self, "settings", None)
        plugins_settings = getattr(settings, "plugins", None)
        overrides = getattr(plugins_settings, "overrides", None)
        if not isinstance(overrides, dict):
            return candidates
        override = overrides.get(plugin_slug)
        if override is None:
            return candidates

        adjusted: list[Candidate] = []
        seen_urls: set[str] = set()
        for url in override.forced_urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            adjusted.append(
                Candidate(
                    url=url,
                    filename=extract_filename(url),
                    source_page="config override",
                    priority=1000 + override.priority_boost,
                )
            )

        for candidate in candidates:
            if not self._candidate_allowed(candidate, override):
                continue
            adjusted_candidate = candidate
            if override.priority_boost:
                adjusted_candidate = replace(candidate, priority=candidate.priority + override.priority_boost)
            if adjusted_candidate.url in seen_urls:
                continue
            seen_urls.add(adjusted_candidate.url)
            adjusted.append(adjusted_candidate)
        return adjusted

    def _candidate_allowed(self, candidate: Candidate, override: PluginOverrideSettings) -> bool:
        lowered = candidate.url.lower()
        host = urlparse(candidate.url).hostname
        if host and host.lower() in override.disabled_hosts:
            return False
        if override.include and not all(term in lowered for term in override.include):
            return False
        if any(term in lowered for term in override.exclude):
            return False
        return True

    def _discover_plugin(self, plugin_spec: PluginSpec, context: DiscoveryContext) -> DiscoverySelection:
        try:
            candidates = self._apply_plugin_overrides(plugin_spec.slug, plugin_spec.discover(context))
            ranked = rank_candidates(candidates)
            selected = choose_best(candidates)
            return DiscoverySelection(plugin=plugin_spec, ranked=ranked, selected=selected)
        except Exception as exc:
            return DiscoverySelection(
                plugin=plugin_spec,
                ranked=[],
                selected=None,
                error=str(exc),
            )

    def _discover_with_fresh_context(self, plugin_spec: PluginSpec) -> DiscoverySelection:
        return self._discover_plugin(plugin_spec, DiscoveryContext(self.settings))

    def _persist_discovery(self, discovery: DiscoverySelection) -> None:
        plugin_slug = discovery.plugin.slug
        if discovery.error:
            self.journal.error(f"{plugin_slug}: discovery failed: {discovery.error}")
            self.state.remember_health(
                plugin_slug,
                status=DOCTOR_CHANGED_PAGE_SHAPE,
                healthy=False,
                error=discovery.error,
            )
            return

        if discovery.selected is None:
            self.state.remember_health(
                plugin_slug,
                status=DOCTOR_NO_CANDIDATES,
                healthy=False,
                error=DOCTOR_NO_CANDIDATES,
            )
            return

        delta_message = self._selection_delta_message(plugin_slug, discovery.selected)
        self.state.remember_selection(plugin_slug, discovery.selected)
        self.state.remember_health(plugin_slug, status=DOCTOR_OK, healthy=True)
        if delta_message:
            self.journal.info(delta_message)

    def discover_one(self, plugin: PluginSpec | str) -> DiscoverySelection:
        plugin_spec = self.get_plugin(plugin)
        context = getattr(self, "context", None)
        if context is None:
            context = DiscoveryContext(self.settings)
        discovery = self._discover_plugin(plugin_spec, context)
        self._persist_discovery(discovery)
        self.state.save()
        return discovery

    def download_one(
        self,
        discovery: DiscoverySelection,
        *,
        dry_run: bool = False,
        progress_callback=None,
    ) -> DownloadResult:
        if discovery.selected is None:
            result = DownloadResult(
                plugin_slug=discovery.plugin.slug,
                candidate=Candidate(url="", filename=None),
                path=None,
                downloaded=False,
                skipped_reason="no candidate selected",
            )
            self.state.remember_download(result)
            self.state.save()
            return result

        tried_urls: set[str] = set()
        last_error: str | None = None
        result: DownloadResult | None = None
        ordered_candidates = self.state.prioritize_mirror_candidates(discovery.ranked or [discovery.selected])
        preferred_due_to_backoff = (
            discovery.selected is not None
            and ordered_candidates
            and ordered_candidates[0].url != discovery.selected.url
        )

        for candidate in ordered_candidates:
            if candidate.url in tried_urls:
                continue
            tried_urls.add(candidate.url)
            try:
                result = self.downloads.process(
                    discovery.plugin.slug,
                    candidate,
                    dry_run=dry_run,
                    progress_callback=progress_callback,
                )
                self.state.remember_mirror_success(result.remote.final_url if result.remote else candidate.url)
                if candidate.url != discovery.selected.url:
                    if preferred_due_to_backoff and candidate.url == ordered_candidates[0].url:
                        self.journal.info(
                            f"{discovery.plugin.slug}: preferred remembered healthy mirror {candidate.url}"
                        )
                    else:
                        self.journal.info(
                            f"{discovery.plugin.slug}: recovered using fallback candidate {candidate.url}"
                        )
                break
            except Exception as exc:
                last_error = str(exc)
                failure_url = candidate.url
                if isinstance(exc, DownloadAttemptError) and exc.remote and exc.remote.final_url:
                    failure_url = exc.remote.final_url
                    self.state.remember_mirror_failure(
                        failure_url,
                        error=last_error,
                        backoff_base_seconds=self.settings.download.mirror_backoff_base_seconds,
                        backoff_cap_seconds=self.settings.download.mirror_backoff_cap_seconds,
                    )
                self.journal.mirror_failure(discovery.plugin.slug, failure_url, last_error)

        if result is None:
            result = DownloadResult(
                plugin_slug=discovery.plugin.slug,
                candidate=discovery.selected,
                path=None,
                downloaded=False,
                skipped_reason=last_error or "all download candidates failed",
            )
            self.journal.error(
                f"{discovery.plugin.slug}: all download candidates failed: {result.skipped_reason}"
            )

        self.state.remember_download(result)
        self.state.save()
        return result

    def discover(
        self,
        selected_plugins: set[str] | None = None,
        progress_callback=None,
        should_cancel=None,
    ) -> list[DiscoverySelection]:
        plugin_specs = [
            plugin
            for plugin in self.plugins
            if not selected_plugins or plugin.slug in selected_plugins
        ]
        if not plugin_specs:
            return []
        if should_cancel and should_cancel():
            return []

        total = len(plugin_specs)
        workers = max(1, min(int(self.settings.download.discovery_workers), total))
        if workers == 1:
            discoveries: list[DiscoverySelection] = []
            for completed, plugin in enumerate(plugin_specs, start=1):
                if should_cancel and should_cancel():
                    break
                discovery = self.discover_one(plugin)
                discoveries.append(discovery)
                if progress_callback:
                    progress_callback(discovery, completed, total)
            return discoveries

        discoveries_by_index: dict[int, DiscoverySelection] = {}
        future_map: dict[object, int] = {}
        next_index = 0
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="distro-hunter-discover")
        try:
            while next_index < total and len(future_map) < workers:
                future_map[executor.submit(self._discover_with_fresh_context, plugin_specs[next_index])] = next_index
                next_index += 1

            completed = 0
            cancelled = False
            while future_map:
                done, _ = wait(set(future_map), return_when=FIRST_COMPLETED)
                for future in done:
                    index = future_map.pop(future)
                    discovery = future.result()
                    discoveries_by_index[index] = discovery
                    self._persist_discovery(discovery)
                    self.state.save()
                    completed += 1
                    if progress_callback:
                        progress_callback(discovery, completed, total)
                if should_cancel and should_cancel():
                    cancelled = True
                while not cancelled and next_index < total and len(future_map) < workers:
                    future_map[executor.submit(self._discover_with_fresh_context, plugin_specs[next_index])] = next_index
                    next_index += 1
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        return [discoveries_by_index[index] for index in range(total) if index in discoveries_by_index]

    def doctor_one(self, plugin: PluginSpec | str) -> DoctorResult:
        plugin_spec = self.get_plugin(plugin)
        started = perf_counter()
        try:
            ranked = rank_candidates(self._apply_plugin_overrides(plugin_spec.slug, plugin_spec.discover(self.context)))
        except Exception as exc:
            return DoctorResult(
                plugin=plugin_spec,
                status=DOCTOR_CHANGED_PAGE_SHAPE,
                error=str(exc),
                duration_seconds=perf_counter() - started,
            )

        selected = ranked[0] if ranked else None
        if selected is None:
            return DoctorResult(
                plugin=plugin_spec,
                status=DOCTOR_NO_CANDIDATES,
                duration_seconds=perf_counter() - started,
            )

        try:
            headers, final_url = self.context.web.inspect_remote_file(selected.url)
            filename = selected.filename or extract_filename(final_url) or extract_filename(selected.url)
            size_header = headers.get("Content-Length")
            remote = RemoteFileInfo(
                url=selected.url,
                final_url=final_url,
                filename=filename,
                size=int(size_header) if size_header and size_header.isdigit() else None,
                etag=headers.get("ETag"),
                last_modified=headers.get("Last-Modified"),
            )
        except Exception as exc:
            return DoctorResult(
                plugin=plugin_spec,
                status=DOCTOR_DOWNLOAD_HEAD_FAILED,
                selected=selected,
                error=str(exc),
                duration_seconds=perf_counter() - started,
            )

        return DoctorResult(
            plugin=plugin_spec,
            status=DOCTOR_OK,
            selected=selected,
            remote=remote,
            duration_seconds=perf_counter() - started,
        )

    def doctor(self, selected_plugins: set[str] | None = None) -> list[DoctorResult]:
        results: list[DoctorResult] = []
        for plugin in self.plugins:
            if selected_plugins and plugin.slug not in selected_plugins:
                continue
            result = self.doctor_one(plugin)
            health = self.state.remember_health(
                result.plugin.slug,
                status=result.status,
                healthy=result.healthy,
                error=result.error,
            )
            if isinstance(health, dict):
                result.health = health
            results.append(result)
        self.state.save()
        return results

    def report_records(self, selected_plugins: set[str] | None = None) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        state_plugins = self.state.data.get("plugins", {})
        known_slugs = set(state_plugins) | set(self.plugin_map)
        for plugin_slug in sorted(known_slugs):
            if selected_plugins and plugin_slug not in selected_plugins:
                continue
            plugin = self.plugin_map.get(plugin_slug)
            record = state_plugins.get(plugin_slug, {})
            selection = record.get("selection", {})
            download = record.get("download", {})
            remote = download.get("remote", {})
            checksum = download.get("checksum", {})
            health = record.get("health", {})
            metadata = (
                plugin.resolved_metadata()
                if plugin
                else infer_plugin_metadata(plugin_slug)
            )
            ventoy_subdir = (
                Path(plugin.ventoy_subdir)
                if plugin and plugin.ventoy_subdir
                else infer_plugin_subdir(plugin_slug, metadata)
            )
            records.append(
                {
                    "plugin_slug": plugin_slug,
                    "plugin_name": plugin.name if plugin else plugin_slug,
                    "plugin_family": metadata.family,
                    "plugin_architecture": metadata.architecture,
                    "plugin_edition_type": metadata.edition_type,
                    "plugin_source_kind": metadata.source_kind,
                    "plugin_ventoy_subdir": ventoy_subdir.as_posix(),
                    "selection_version": selection.get("version"),
                    "selection_filename": selection.get("filename"),
                    "selection_url": selection.get("url"),
                    "selection_selected_at": selection.get("selected_at"),
                    "download_path": download.get("path"),
                    "download_filename": download.get("filename"),
                    "download_downloaded": download.get("downloaded"),
                    "download_skipped_reason": download.get("skipped_reason"),
                    "download_updated_at": download.get("updated_at"),
                    "remote_url": remote.get("url"),
                    "remote_final_url": remote.get("final_url"),
                    "remote_filename": remote.get("filename"),
                    "remote_size": remote.get("size"),
                    "remote_etag": remote.get("etag"),
                    "remote_last_modified": remote.get("last_modified"),
                    "checksum_status": checksum.get("status"),
                    "checksum_algorithm": checksum.get("algorithm"),
                    "checksum_expected": checksum.get("expected"),
                    "checksum_actual": checksum.get("actual"),
                    "checksum_source": checksum.get("source"),
                    "health_healthy": health.get("healthy"),
                    "health_last_status": health.get("last_status"),
                    "health_last_checked_at": health.get("last_checked_at"),
                    "health_last_success_at": health.get("last_success_at"),
                    "health_last_failure_at": health.get("last_failure_at"),
                    "health_failure_count": health.get("failure_count"),
                    "health_last_error": health.get("last_error"),
                }
            )
        return records

    def download_discoveries(
        self,
        discoveries: list[DiscoverySelection],
        *,
        dry_run: bool = False,
        should_cancel=None,
    ) -> list[DownloadResult]:
        results: list[DownloadResult] = []
        for discovery in discoveries:
            if should_cancel and should_cancel():
                break
            if discovery.selected is None:
                continue
            results.append(self.download_one(discovery, dry_run=dry_run))
        return results

    def _manual_source_subdir(self, source_path: Path) -> Path | None:
        for rule in self.settings.ventoy.manual_sources:
            if not fnmatch(source_path.name.lower(), rule.pattern.lower()):
                continue
            if rule.subdir:
                return Path(rule.subdir)
            if rule.family or rule.edition_type:
                return metadata_subdir(
                    metadata_from_fields(
                        family=rule.family or self.settings.ventoy.manual_subdir,
                        architecture=rule.architecture,
                        edition_type=rule.edition_type,
                        source_kind=rule.source_kind,
                    )
                )
            return Path(self.settings.ventoy.manual_subdir)
        return None

    def _build_ventoy_route_map(self) -> dict[Path, Path]:
        routes: dict[Path, Path] = {}
        for plugin_slug, record in self.state.data.get("plugins", {}).items():
            download = record.get("download", {})
            path_text = download.get("path")
            if not path_text:
                continue
            source_path = Path(path_text)
            if not source_path.is_absolute():
                source_path = (self.settings.download.download_dir / source_path).resolve()
            plugin = self.plugin_map.get(plugin_slug)
            metadata = plugin.resolved_metadata() if plugin else infer_plugin_metadata(plugin_slug)
            subdir = Path(plugin.ventoy_subdir) if plugin and plugin.ventoy_subdir else infer_plugin_subdir(plugin_slug, metadata)
            routes[source_path.resolve()] = subdir

        if self.settings.download.download_dir.exists():
            for source_path in sorted(self.settings.download.download_dir.iterdir()):
                if not source_path.is_file():
                    continue
                resolved = source_path.resolve()
                if resolved in routes:
                    continue
                manual_subdir = self._manual_source_subdir(source_path)
                if manual_subdir is not None:
                    routes[resolved] = manual_subdir
        return routes

    def sync_ventoy(self) -> tuple[Path | None, list[Path]]:
        if not self.settings.ventoy.enabled:
            return None, []
        drive = detect_ventoy_drive(self.settings.ventoy)
        if drive is None:
            return None, []
        copied = sync_directory_to_ventoy(
            self.settings.download.download_dir,
            drive,
            self.settings.ventoy,
            route_map=self._build_ventoy_route_map(),
        )
        return drive.root, copied

    def validate(
        self,
        selected_plugins: set[str] | None = None,
    ) -> list[ValidateResult]:
        results: list[ValidateResult] = []
        for plugin in self.plugins:
            if selected_plugins and plugin.slug not in selected_plugins:
                continue

            record = self.state.get_plugin_record(plugin.slug)
            download = record.get("download", {}) if isinstance(record, dict) else {}
            selection = record.get("selection", {}) if isinstance(record, dict) else {}

            has_record = bool(download) or bool(selection)
            if not has_record:
                results.append(
                    ValidateResult(
                        plugin_slug=plugin.slug,
                        plugin_name=plugin.name,
                        status=VALID_STATUS_NO_RECORD,
                    )
                )
                continue

            dl_path = None
            if isinstance(download, dict):
                dl_path = download.get("path")
            full_path = (
                (self.settings.download.download_dir / dl_path).resolve()
                if dl_path
                else None
            )
            file_exists = full_path is not None and full_path.exists() and full_path.is_file()

            try:
                candidates = self._apply_plugin_overrides(
                    plugin.slug, plugin.discover(self.context)
                )
                ranked = rank_candidates(candidates)
                current = choose_best(candidates)
            except Exception as exc:
                results.append(
                    ValidateResult(
                        plugin_slug=plugin.slug,
                        plugin_name=plugin.name,
                        status=VALID_STATUS_ERROR,
                        downloaded_filename=Path(dl_path).name if dl_path else None,
                        downloaded_url=selection.get("url") if isinstance(selection, dict) else None,
                        downloaded_version=selection.get("version") if isinstance(selection, dict) else None,
                        downloaded_at=download.get("updated_at") if isinstance(download, dict) else None,
                        file_exists=file_exists,
                        error=str(exc),
                    )
                )
                continue

            if current is None:
                if not file_exists:
                    results.append(
                        ValidateResult(
                            plugin_slug=plugin.slug,
                            plugin_name=plugin.name,
                            status=VALID_STATUS_FILE_MISSING,
                            downloaded_filename=Path(dl_path).name if dl_path else None,
                            downloaded_url=selection.get("url") if isinstance(selection, dict) else None,
                            downloaded_version=selection.get("version") if isinstance(selection, dict) else None,
                            downloaded_at=download.get("updated_at") if isinstance(download, dict) else None,
                            file_exists=False,
                        )
                    )
                    continue

                results.append(
                    ValidateResult(
                        plugin_slug=plugin.slug,
                        plugin_name=plugin.name,
                        status=VALID_STATUS_UP_TO_DATE,
                        downloaded_filename=Path(dl_path).name if dl_path else None,
                        downloaded_url=selection.get("url") if isinstance(selection, dict) else None,
                        downloaded_version=selection.get("version") if isinstance(selection, dict) else None,
                        downloaded_at=download.get("updated_at") if isinstance(download, dict) else None,
                        file_exists=file_exists,
                    )
                )
                continue

            discovered_url = current.url
            discovered_filename = current.filename
            discovered_version = current.version
            stored_url = selection.get("url") if isinstance(selection, dict) else None

            if not file_exists:
                results.append(
                    ValidateResult(
                        plugin_slug=plugin.slug,
                        plugin_name=plugin.name,
                        status=VALID_STATUS_FILE_MISSING,
                        downloaded_filename=Path(dl_path).name if dl_path else None,
                        discovered_filename=discovered_filename,
                        downloaded_url=stored_url,
                        discovered_url=discovered_url,
                        downloaded_version=selection.get("version") if isinstance(selection, dict) else None,
                        discovered_version=discovered_version,
                        downloaded_at=download.get("updated_at") if isinstance(download, dict) else None,
                        file_exists=False,
                    )
                )
                continue

            if discovered_url != stored_url or (
                discovered_version and selection.get("version") and discovered_version != selection.get("version")
            ):
                results.append(
                    ValidateResult(
                        plugin_slug=plugin.slug,
                        plugin_name=plugin.name,
                        status=VALID_STATUS_OUTDATED,
                        downloaded_filename=Path(dl_path).name if dl_path else None,
                        discovered_filename=discovered_filename,
                        downloaded_url=stored_url,
                        discovered_url=discovered_url,
                        downloaded_version=selection.get("version") if isinstance(selection, dict) else None,
                        discovered_version=discovered_version,
                        downloaded_at=download.get("updated_at") if isinstance(download, dict) else None,
                        file_exists=True,
                    )
                )
                continue

            results.append(
                ValidateResult(
                    plugin_slug=plugin.slug,
                    plugin_name=plugin.name,
                    status=VALID_STATUS_UP_TO_DATE,
                    downloaded_filename=Path(dl_path).name if dl_path else None,
                    downloaded_url=stored_url,
                    downloaded_version=selection.get("version") if isinstance(selection, dict) else None,
                    downloaded_at=download.get("updated_at") if isinstance(download, dict) else None,
                    file_exists=True,
                )
            )

        return results

    def sync_download_result(self, result: DownloadResult) -> tuple[Path | None, list[Path]]:
        if not self.settings.ventoy.enabled or result.path is None:
            return None, []
        try:
            artifact_path = result.path.resolve()
        except OSError:
            artifact_path = result.path
        if not artifact_path.exists() or not artifact_path.is_file():
            return None, []

        drive = detect_ventoy_drive(self.settings.ventoy)
        if drive is None:
            return None, []
        copied = sync_paths_to_ventoy(
            [artifact_path],
            drive,
            self.settings.ventoy,
            route_map=self._build_ventoy_route_map(),
        )
        return drive.root, copied


def validate_rows(results: list[ValidateResult]) -> list[str]:
    rows: list[str] = []
    for result in results:
        base = f"{result.plugin_slug} ({result.plugin_name})"
        if result.status == VALID_STATUS_UP_TO_DATE:
            rows.append(f"{base}: ok — {result.downloaded_filename or 'n/a'}")
        elif result.status == VALID_STATUS_OUTDATED:
            rows.append(
                f"{base}: outdated — {result.downloaded_filename or 'n/a'} "
                f"-> {result.discovered_filename or result.discovered_url or 'n/a'}"
            )
        elif result.status == VALID_STATUS_FILE_MISSING:
            rows.append(f"{base}: file missing — {result.downloaded_filename or 'n/a'}")
        elif result.status == VALID_STATUS_NO_RECORD:
            rows.append(f"{base}: no download record")
        elif result.status == VALID_STATUS_ERROR:
            rows.append(f"{base}: error — {result.error}")
    return rows


def validate_summary(results: list[ValidateResult]) -> str:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    parts: list[str] = []
    for status, label in [
        (VALID_STATUS_UP_TO_DATE, "up-to-date"),
        (VALID_STATUS_OUTDATED, "outdated"),
        (VALID_STATUS_FILE_MISSING, "file missing"),
        (VALID_STATUS_NO_RECORD, "no record"),
        (VALID_STATUS_ERROR, "error"),
    ]:
        count = counts.get(status, 0)
        if count:
            parts.append(f"{count} {label}")
    return f"Validate summary: {', '.join(parts)}"


def discovery_rows(discoveries: list[DiscoverySelection]) -> list[str]:
    rows: list[str] = []
    for discovery in discoveries:
        if discovery.error:
            rows.append(f"{discovery.plugin.slug}: error: {discovery.error}")
            continue
        if discovery.selected is None:
            rows.append(f"{discovery.plugin.slug}: no candidates found")
            continue
        selected = discovery.selected
        rows.append(
            f"{discovery.plugin.slug}: {selected.filename or selected.url} "
            f"(score={score_candidate(selected)}, version={selected.version or 'n/a'})"
        )
    return rows


def doctor_rows(results: list[DoctorResult]) -> list[str]:
    def suffix(result: DoctorResult) -> str:
        extras: list[str] = []
        duration = getattr(result, "duration_seconds", None)
        if isinstance(duration, (int, float)):
            extras.append(f"{duration:.2f}s")
        health = getattr(result, "health", None)
        if isinstance(health, dict):
            last_success = health.get("last_success_at")
            extras.append(f"last_good={last_success if isinstance(last_success, str) and last_success else 'never'}")
            failures = health.get("failure_count")
            if isinstance(failures, int):
                extras.append(f"failures={failures}")
        return f" ({', '.join(extras)})" if extras else ""

    rows: list[str] = []
    for result in results:
        if result.status == DOCTOR_OK:
            selected = result.selected
            label = (selected.filename if selected and selected.filename else None) or (
                result.remote.filename if result.remote else None
            )
            rows.append(
                f"{result.plugin.slug}: ok: {label or (selected.url if selected else 'n/a')} "
                f"(version={selected.version if selected and selected.version else 'n/a'})"
                f"{suffix(result)}"
            )
            continue
        if result.status == DOCTOR_NO_CANDIDATES:
            rows.append(f"{result.plugin.slug}: no candidates{suffix(result)}")
            continue
        if result.status == DOCTOR_DOWNLOAD_HEAD_FAILED:
            target = result.selected.url if result.selected else result.plugin.slug
            rows.append(f"{result.plugin.slug}: download head failed: {target} -> {result.error}{suffix(result)}")
            continue
        rows.append(f"{result.plugin.slug}: changed page shape: {result.error}{suffix(result)}")
    return rows


def doctor_summary(results: list[DoctorResult]) -> str:
    counts = {
        DOCTOR_OK: 0,
        DOCTOR_NO_CANDIDATES: 0,
        DOCTOR_CHANGED_PAGE_SHAPE: 0,
        DOCTOR_DOWNLOAD_HEAD_FAILED: 0,
    }
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    total_duration = sum(
        float(result.duration_seconds)
        for result in results
        if isinstance(getattr(result, "duration_seconds", None), (int, float))
    )
    unhealthy = [result.plugin.slug for result in results if not result.healthy]
    duration_suffix = f" in {total_duration:.2f}s"
    unhealthy_suffix = f"; unhealthy={', '.join(unhealthy)}" if unhealthy else ""
    return (
        "Doctor summary: "
        f"{counts[DOCTOR_OK]} ok, "
        f"{counts[DOCTOR_NO_CANDIDATES]} no candidates, "
        f"{counts[DOCTOR_CHANGED_PAGE_SHAPE]} changed page shape, "
        f"{counts[DOCTOR_DOWNLOAD_HEAD_FAILED]} download head failed"
        f"{duration_suffix}"
        f"{unhealthy_suffix}"
    )
