from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from filecmp import cmp as files_match
from fnmatch import fnmatch
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from py7zr.exceptions import ArchiveError, PasswordRequired
from requests.exceptions import RequestException

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
from distro_hunter.plugin_loader import DiscoveryContext, PluginSpec, load_plugins
from distro_hunter.plugin_metadata import (
    infer_plugin_metadata,
    metadata_from_fields,
    metadata_subdir,
)
from distro_hunter.scoring import choose_best, rank_candidates, score_candidate
from distro_hunter.startup_checks import collect_startup_warnings
from distro_hunter.state import StateStore
from distro_hunter.utils import extract_filename
from distro_hunter.ventoy import (
    detect_ventoy_drive,
    infer_plugin_subdir,
    sync_directory_to_ventoy,
    sync_paths_to_ventoy,
    ventoy_target_path,
)

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
        return not any(term in lowered for term in override.exclude)

    def _discover_plugin(self, plugin_spec: PluginSpec, context: DiscoveryContext) -> DiscoverySelection:
        try:
            candidates = self._apply_plugin_overrides(plugin_spec.slug, plugin_spec.discover(context))
            ranked = rank_candidates(candidates)
            downloadable = [candidate for candidate in candidates if _candidate_is_downloadable(candidate)]
            selected = choose_best(downloadable)
            return DiscoverySelection(plugin=plugin_spec, ranked=ranked, selected=selected)
        except (OSError, RequestException, TypeError, ValueError) as exc:
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
        downloadable = [
            candidate
            for candidate in discovery.ranked
            if _candidate_is_downloadable(candidate)
        ]
        selected = discovery.selected
        if selected is not None and not _candidate_is_downloadable(selected):
            selected = choose_best(downloadable)
        if selected is None and downloadable:
            selected = choose_best(downloadable)
        if selected is None:
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
        ordered_candidates = self.state.prioritize_mirror_candidates(
            downloadable or [selected]
        )
        preferred_due_to_backoff = (
            ordered_candidates and ordered_candidates[0].url != selected.url
        )

        if discovery.plugin.batch_download:
            batch_results: list[DownloadResult] = []
            batch_errors: list[str] = []
            for candidate in downloadable:
                try:
                    batch_result = self.downloads.process(
                        discovery.plugin.slug,
                        candidate,
                        dry_run=dry_run,
                        progress_callback=progress_callback,
                    )
                    batch_results.append(batch_result)
                    self.state.remember_mirror_success(
                        batch_result.remote.final_url
                        if batch_result.remote
                        else candidate.url
                    )
                except (OSError, TypeError, ValueError, DownloadAttemptError) as exc:
                    error = f"{candidate.filename or candidate.url}: {exc}"
                    batch_errors.append(error)
                    self.journal.mirror_failure(
                        discovery.plugin.slug,
                        candidate.url,
                        str(exc),
                    )

            artifacts = list(
                dict.fromkeys(
                    artifact
                    for batch_result in batch_results
                    for artifact in (
                        batch_result.artifact_paths
                        or ([batch_result.path] if batch_result.path else [])
                    )
                )
            )
            first_result = batch_results[0] if batch_results else None
            result = DownloadResult(
                plugin_slug=discovery.plugin.slug,
                candidate=selected,
                path=first_result.path if first_result else None,
                downloaded=any(item.downloaded for item in batch_results),
                skipped_reason=(
                    "; ".join(batch_errors) if batch_errors else
                    ("all media set downloads failed" if not batch_results else None)
                ),
                remote=first_result.remote if first_result else None,
                checksum=first_result.checksum if first_result else None,
                pruned_paths=[
                    path for item in batch_results for path in item.pruned_paths
                ],
                artifact_paths=artifacts,
            )
            if batch_errors:
                self.journal.error(
                    f"{discovery.plugin.slug}: incomplete media set: "
                    + "; ".join(batch_errors)
                )
            self.state.remember_download(result)
            self.state.save()
            return result

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
                if candidate.url != selected.url:
                    if preferred_due_to_backoff and candidate.url == ordered_candidates[0].url:
                        self.journal.info(
                            f"{discovery.plugin.slug}: preferred remembered healthy mirror {candidate.url}"
                        )
                    else:
                        self.journal.info(
                            f"{discovery.plugin.slug}: recovered using fallback candidate {candidate.url}"
                        )
                break
            except (OSError, TypeError, ValueError, DownloadAttemptError) as exc:
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
                candidate=selected,
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
            candidates = self._apply_plugin_overrides(
                plugin_spec.slug,
                plugin_spec.discover(self.context),
            )
            ranked = rank_candidates(
                [candidate for candidate in candidates if _candidate_is_downloadable(candidate)]
            )
        except Exception as exc:  # noqa: BLE001 - doctor must catch any failure
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
        except Exception as exc:  # noqa: BLE001 - doctor must catch any failure
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
            plugin = self.plugin_map.get(plugin_slug)
            metadata = plugin.resolved_metadata() if plugin else infer_plugin_metadata(plugin_slug)
            subdir = Path(plugin.ventoy_subdir) if plugin and plugin.ventoy_subdir else infer_plugin_subdir(plugin_slug, metadata)
            filename = download.get("filename")
            path_texts = [
                path_text,
                *download.get("artifact_paths", []),
                *([filename] if isinstance(filename, str) else []),
            ]
            for artifact_path_text in path_texts:
                source_path = Path(artifact_path_text)
                if not source_path.is_absolute():
                    source_path = (
                        self.settings.download.download_dir / source_path
                    ).resolve()
                if (
                    not source_path.is_file()
                    and Path(artifact_path_text).parent == Path(".")
                    and self.settings.download.download_dir.name != "downloads"
                ):
                    legacy_source = (
                        self.settings.download.download_dir.parent
                        / "downloads"
                        / Path(artifact_path_text).name
                    )
                    if legacy_source.is_file():
                        source_path = legacy_source.resolve()
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

    def _extract_sync_archives(
        self,
        source_dir: Path,
        route_map: dict[Path, Path],
    ) -> dict[Path, list[Path]]:
        extracted_archives: dict[Path, list[Path]] = {}
        if not self.settings.download.extract_7z:
            return extracted_archives

        for archive_path in sorted(source_dir.glob("*.7z")):
            try:
                artifact_paths = self.downloads.extract_local_7z_images(archive_path)
                archive_route = route_map.get(archive_path.resolve())
                if archive_route is None:
                    archive_route = self._manual_source_subdir(archive_path) or Path(
                        self.settings.ventoy.manual_subdir
                    )
                for artifact_path in artifact_paths:
                    route_map[artifact_path.resolve()] = archive_route
                self.state.record_extracted_artifacts(archive_path, artifact_paths)
                extracted_archives[archive_path.resolve()] = artifact_paths
            except (ArchiveError, OSError, PasswordRequired, ValueError) as error:
                self.journal.error(f"7z extraction failed for {archive_path}: {error}")
        return extracted_archives

    def sync_ventoy(self) -> tuple[Path | None, list[Path]]:
        if not self.settings.ventoy.enabled:
            return None, []
        drive = detect_ventoy_drive(self.settings.ventoy)
        if drive is None:
            return None, []
        route_map = self._build_ventoy_route_map()
        source_dir = self.settings.download.download_dir
        extracted_archives = self._extract_sync_archives(source_dir, route_map)
        destination = drive.root / self.settings.ventoy.destination_subdir
        allowed_extensions = tuple(entry.lower() for entry in self.settings.ventoy.copy_extensions)
        legacy_download_dir = (source_dir.parent / "downloads").resolve()
        external_sources = {
            source
            for source in route_map
            if source.parent == legacy_download_dir
            and source_dir.resolve() != legacy_download_dir
            and source.is_file()
        }
        tracked_targets = {
            source.resolve(): ventoy_target_path(
                source,
                destination,
                self.settings.ventoy,
                route_map,
            )
            for source in route_map
        }
        recovered_paths = {
            source: target
            for source, target in tracked_targets.items()
            if not source.exists() and target.is_file()
        }
        if recovered_paths:
            self.state.relocate_download_artifacts(recovered_paths)

        planned_sources = {
            source.resolve()
            for source in source_dir.iterdir()
            if source.is_file() and source.name.lower().endswith(allowed_extensions)
        }
        planned_sources.update(
            source
            for source in external_sources
            if source.name.lower().endswith(allowed_extensions)
        )
        planned_paths = {
            source: ventoy_target_path(source, destination, self.settings.ventoy, route_map)
            for source in sorted(planned_sources)
        }

        def report_sync_error(source: Path, error: OSError) -> None:
            self.journal.error(f"Ventoy sync failed for {source}: {error}")

        copied = sync_directory_to_ventoy(
            source_dir,
            drive,
            self.settings.ventoy,
            route_map=route_map,
            on_error=report_sync_error,
        )
        moved_paths: dict[Path, Path] = {}
        for source, target in planned_paths.items():
            if not target.is_file():
                continue
            if not source.exists():
                moved_paths[source] = target
                continue
            if self.settings.ventoy.overwrite_existing:
                continue
            try:
                matches = files_match(source, target, shallow=False)
            except OSError as error:
                report_sync_error(source, error)
                continue
            if not matches:
                self.journal.warning(
                    f"Retaining {source}; existing Ventoy file differs at {target}"
                )
                continue
            try:
                source.unlink()
            except OSError as error:
                report_sync_error(source, error)
                continue
            moved_paths[source] = target
        if moved_paths:
            self.state.relocate_download_artifacts(moved_paths)

        for archive_path, artifact_paths in extracted_archives.items():
            artifact_targets = {
                artifact_path: ventoy_target_path(
                    artifact_path,
                    destination,
                    self.settings.ventoy,
                    route_map,
                )
                for artifact_path in artifact_paths
            }
            try:
                all_synced = all(
                    target.is_file()
                    and (
                        not artifact_path.is_file()
                        or files_match(artifact_path, target, shallow=False)
                    )
                    for artifact_path, target in artifact_targets.items()
                )
            except OSError as error:
                self.journal.error(
                    f"Could not verify extracted images for {archive_path}: {error}"
                )
                continue

            if not all_synced:
                self.journal.warning(
                    f"Retaining {archive_path}; one or more extracted images are not synced"
                )
                continue

            self.state.relocate_download_artifacts(artifact_targets)
            try:
                archive_path.unlink()
            except OSError as error:
                self.journal.error(f"Could not remove consumed archive {archive_path}: {error}")
                continue
            self.state.mark_download_consumed(archive_path)
            for artifact_path in artifact_paths:
                if not artifact_path.exists():
                    continue
                try:
                    artifact_path.unlink()
                except OSError as error:
                    self.journal.error(
                        f"Could not remove duplicate extracted image {artifact_path}: {error}"
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
                current = ranked[0] if ranked else None
            except (OSError, TypeError, ValueError) as exc:
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
        paths = result.artifact_paths or [result.path]
        artifacts: list[Path] = []
        for path in paths:
            try:
                artifact_path = path.resolve()
            except OSError:
                artifact_path = path
            if artifact_path.exists() and artifact_path.is_file():
                artifacts.append(artifact_path)
        if not artifacts:
            return None, []

        drive = detect_ventoy_drive(self.settings.ventoy)
        if drive is None:
            return None, []
        copied = sync_paths_to_ventoy(
            artifacts,
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
        candidates = discovery.ranked or ([discovery.selected] if discovery.selected is not None else [])
        if not candidates:
            rows.append(f"{discovery.plugin.slug}: no candidates found")
            continue
        plugin_metadata = discovery.plugin.resolved_metadata()
        display_candidates = [
            candidate
            for candidate in candidates
            if candidate is discovery.selected or candidate.metadata.get("downloadable") is False
        ]
        for candidate in display_candidates:
            source = candidate.metadata.get("source_kind") or plugin_metadata.source_kind or "unknown"
            edition = candidate.metadata.get("edition_type") or plugin_metadata.edition_type or "n/a"
            architecture = candidate.arch or plugin_metadata.architecture or "n/a"
            kind = (
                "link-only"
                if candidate.metadata.get("downloadable") is False
                else f"score={score_candidate(candidate)}"
            )
            rows.append(
                f"{discovery.plugin.slug}: {candidate.filename or candidate.url} "
                f"(source={source}, edition={edition}, arch={architecture}, "
                f"version={candidate.version or 'n/a'}, {kind}, url={candidate.url})"
            )
    return rows


def _candidate_is_downloadable(candidate: Candidate) -> bool:
    return candidate.metadata.get("downloadable") is not False


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
