import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Lock

from distro_hunter.config import DownloadSettings, GeneratorSettings, LoggingSettings, PluginSettings, Settings, VentoySettings
from distro_hunter.core import DiscoverySelection, DistroHunter
from distro_hunter.downloads import DownloadAttemptError
from distro_hunter.models import Candidate, DownloadResult, RemoteFileInfo
from distro_hunter.plugin_loader import PluginSpec
from distro_hunter.plugins import archlinux


class StubContext:
    def __init__(self, text: str) -> None:
        self.text = text

    def fetch_text(self, url: str) -> str:
        return self.text

    def normalize_url(self, base_url: str, link: str) -> str:
        return base_url + link


class FakeDownloads:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def process(
        self,
        plugin_slug: str,
        candidate: Candidate,
        *,
        dry_run: bool = False,
        progress_callback=None,
    ) -> DownloadResult:
        self.seen.append(candidate.url)
        if "bad" in candidate.url:
            raise DownloadAttemptError(
                "403 Forbidden",
                candidate=candidate,
                remote=RemoteFileInfo(
                    url=candidate.url,
                    final_url=candidate.url,
                    filename=candidate.filename,
                ),
            )
        return DownloadResult(
            plugin_slug=plugin_slug,
            candidate=candidate,
            path=None,
            downloaded=False,
            skipped_reason="dry run" if dry_run else "ok",
        )


class FakeState:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.saved_results: list[DownloadResult] = []
        self.health_updates: list[dict] = []
        self.backoff_urls: set[str] = set()
        self.mirror_failures: list[dict] = []
        self.mirror_successes: list[str] = []

    def get_plugin_record(self, plugin_slug: str) -> dict:
        return self.records.setdefault(plugin_slug, {})

    def remember_download(self, result: DownloadResult) -> None:
        self.saved_results.append(result)

    def remember_health(self, plugin_slug: str, *, status: str, healthy: bool, error: str | None = None) -> None:
        self.health_updates.append(
            {
                "plugin_slug": plugin_slug,
                "status": status,
                "healthy": healthy,
                "error": error,
            }
        )

    def remember_selection(self, plugin_slug: str, candidate: Candidate) -> None:
        self.get_plugin_record(plugin_slug)["selection"] = {
            "url": candidate.url,
            "filename": candidate.filename,
            "version": candidate.version,
        }

    def prioritize_mirror_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        return [candidate for _, candidate in sorted(enumerate(candidates), key=lambda item: (1 if item[1].url in self.backoff_urls else 0, item[0]))]

    def remember_mirror_failure(
        self,
        url: str | None,
        *,
        error: str,
        backoff_base_seconds: int,
        backoff_cap_seconds: int,
    ) -> None:
        if url is None:
            return
        self.backoff_urls.add(url)
        self.mirror_failures.append(
            {
                "url": url,
                "error": error,
                "backoff_base_seconds": backoff_base_seconds,
                "backoff_cap_seconds": backoff_cap_seconds,
            }
        )

    def remember_mirror_success(self, url: str | None) -> None:
        if url is None:
            return
        self.backoff_urls.discard(url)
        self.mirror_successes.append(url)

    def save(self) -> None:
        pass


class FakeJournal:
    def __init__(self) -> None:
        self.info_messages: list[str] = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def mirror_failure(self, plugin_slug: str, url: str, error: str) -> None:
        pass


class ResilienceTests(unittest.TestCase):
    def test_arch_plugin_skips_archlinux_org_direct_iso(self) -> None:
        html = """
        <a href="https://archlinux.org/iso/2026.03.01/">bad</a>
        <a href="https://mirror.example.net/archlinux/iso/2026.03.01/">good</a>
        archlinux-2026.03.01-x86_64.iso
        magnet:?xt=urn:btih:test
        """
        candidates = archlinux.discover(StubContext(html))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].url,
            "https://mirror.example.net/archlinux/iso/2026.03.01/archlinux-2026.03.01-x86_64.iso",
        )

    def test_download_discoveries_falls_back_to_next_candidate(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.downloads = FakeDownloads()
        hunter.state = FakeState()
        hunter.journal = FakeJournal()
        hunter.settings = type(
            "Settings",
            (),
            {
                "download": type(
                    "DownloadSettings",
                    (),
                    {
                        "mirror_backoff_base_seconds": 60,
                        "mirror_backoff_cap_seconds": 300,
                    },
                )()
            },
        )()

        plugin = PluginSpec(slug="test_plugin", name="Test Plugin", module=object())
        selected = Candidate(url="https://bad.example/test.iso", filename="test.iso")
        fallback = Candidate(url="https://good.example/test.iso", filename="test.iso")
        discovery = DiscoverySelection(
            plugin=plugin,
            ranked=[selected, fallback],
            selected=selected,
        )

        results = DistroHunter.download_discoveries(hunter, [discovery], dry_run=True)

        self.assertEqual(hunter.downloads.seen, [selected.url, fallback.url])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].candidate.url, fallback.url)
        self.assertEqual(hunter.state.mirror_failures[0]["url"], selected.url)
        self.assertEqual(hunter.state.mirror_successes, [fallback.url])

    def test_download_discoveries_prefers_known_healthy_mirror_before_backoff_host(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.downloads = FakeDownloads()
        hunter.state = FakeState()
        hunter.journal = FakeJournal()
        hunter.settings = type(
            "Settings",
            (),
            {
                "download": type(
                    "DownloadSettings",
                    (),
                    {
                        "mirror_backoff_base_seconds": 60,
                        "mirror_backoff_cap_seconds": 300,
                    },
                )()
            },
        )()
        hunter.state.backoff_urls.add("https://bad.example/test.iso")

        plugin = PluginSpec(slug="test_plugin", name="Test Plugin", module=object())
        selected = Candidate(url="https://bad.example/test.iso", filename="test.iso")
        fallback = Candidate(url="https://good.example/test.iso", filename="test.iso")
        discovery = DiscoverySelection(
            plugin=plugin,
            ranked=[selected, fallback],
            selected=selected,
        )

        results = DistroHunter.download_discoveries(hunter, [discovery], dry_run=True)

        self.assertEqual(hunter.downloads.seen, [fallback.url])
        self.assertEqual(results[0].candidate.url, fallback.url)
        self.assertIn(
            "test_plugin: preferred remembered healthy mirror https://good.example/test.iso",
            hunter.journal.info_messages,
        )

    def test_discover_one_persists_health_for_no_candidates(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.context = object()
        hunter.state = FakeState()
        hunter.journal = FakeJournal()
        hunter.plugin_map = {}

        plugin = PluginSpec(
            slug="empty_plugin",
            name="Empty Plugin",
            module=type("Module", (), {"discover": staticmethod(lambda context: [])})(),
        )

        discovery = DistroHunter.discover_one(hunter, plugin)

        self.assertIsNone(discovery.selected)
        self.assertEqual(hunter.state.health_updates[0]["plugin_slug"], "empty_plugin")
        self.assertEqual(hunter.state.health_updates[0]["status"], "no candidates")
        self.assertFalse(hunter.state.health_updates[0]["healthy"])

    def test_discover_one_logs_version_delta_when_selection_changes(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.context = object()
        hunter.state = FakeState()
        hunter.journal = FakeJournal()
        hunter.plugin_map = {}
        hunter.state.records["ubuntu_lts"] = {
            "selection": {
                "url": "https://example.org/ubuntu-24.04.3.iso",
                "filename": "ubuntu-24.04.3.iso",
                "version": "24.04.3",
            }
        }

        plugin = PluginSpec(
            slug="ubuntu_lts",
            name="Ubuntu LTS",
            module=type(
                "Module",
                (),
                {
                    "discover": staticmethod(
                        lambda context: [
                            Candidate(
                                url="https://example.org/ubuntu-24.04.4.iso",
                                filename="ubuntu-24.04.4.iso",
                                version="24.04.4",
                            )
                        ]
                    )
                },
            )(),
        )

        discovery = DistroHunter.discover_one(hunter, plugin)

        self.assertEqual(discovery.selected.version, "24.04.4")
        self.assertIn("ubuntu_lts: version changed 24.04.3 -> 24.04.4", hunter.journal.info_messages)

    def test_discover_uses_concurrent_workers_and_preserves_plugin_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings(
                config_path=root / "config.json",
                state_file=root / "state.json",
                plugins=PluginSettings(builtin=[], directories=[]),
                download=DownloadSettings(
                    download_dir=root / "downloads",
                    aria2_path=None,
                    prefer_aria2=False,
                    discovery_workers=4,
                ),
                ventoy=VentoySettings(enabled=False),
                generator=GeneratorSettings(output_dir=root / "generated"),
                logging=LoggingSettings(run_log_file=None, mirror_failures_file=None, jsonl_log_file=None),
            )

            hunter = object.__new__(DistroHunter)
            hunter.settings = settings
            hunter.context = object()
            hunter.state = FakeState()
            hunter.journal = FakeJournal()

            active = 0
            max_active = 0
            lock = Lock()

            def discover_factory(index: int):
                def discover(context) -> list[Candidate]:
                    nonlocal active, max_active
                    with lock:
                        active += 1
                        max_active = max(max_active, active)
                    time.sleep(0.05)
                    with lock:
                        active -= 1
                    return [Candidate(url=f"https://example.org/test-{index}.iso", filename=f"test-{index}.iso")]

                return discover

            hunter.plugins = [
                PluginSpec(
                    slug=f"plugin_{index}",
                    name=f"Plugin {index}",
                    module=type("Module", (), {"discover": staticmethod(discover_factory(index))})(),
                )
                for index in range(4)
            ]
            hunter.plugin_map = {plugin.slug: plugin for plugin in hunter.plugins}

            discoveries = DistroHunter.discover(hunter)

            self.assertGreater(max_active, 1)
            self.assertEqual(
                [discovery.plugin.slug for discovery in discoveries],
                [plugin.slug for plugin in hunter.plugins],
            )

    def test_discover_stops_submitting_new_plugins_after_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings(
                config_path=root / "config.json",
                state_file=root / "state.json",
                plugins=PluginSettings(builtin=[], directories=[]),
                download=DownloadSettings(
                    download_dir=root / "downloads",
                    aria2_path=None,
                    prefer_aria2=False,
                    discovery_workers=2,
                ),
                ventoy=VentoySettings(enabled=False),
                generator=GeneratorSettings(output_dir=root / "generated"),
                logging=LoggingSettings(run_log_file=None, mirror_failures_file=None, jsonl_log_file=None),
            )

            hunter = object.__new__(DistroHunter)
            hunter.settings = settings
            hunter.context = object()
            hunter.state = FakeState()
            hunter.journal = FakeJournal()

            seen: list[str] = []
            lock = Lock()

            def discover_factory(index: int):
                def discover(context) -> list[Candidate]:
                    with lock:
                        seen.append(f"plugin_{index}")
                    time.sleep(0.05)
                    return [Candidate(url=f"https://example.org/test-{index}.iso", filename=f"test-{index}.iso")]

                return discover

            hunter.plugins = [
                PluginSpec(
                    slug=f"plugin_{index}",
                    name=f"Plugin {index}",
                    module=type("Module", (), {"discover": staticmethod(discover_factory(index))})(),
                )
                for index in range(5)
            ]
            hunter.plugin_map = {plugin.slug: plugin for plugin in hunter.plugins}

            cancelled = Event()

            def callback(discovery: DiscoverySelection, completed: int, total: int) -> None:
                if completed == 1:
                    cancelled.set()

            discoveries = DistroHunter.discover(
                hunter,
                progress_callback=callback,
                should_cancel=cancelled.is_set,
            )

            self.assertLess(len(seen), 5)
            self.assertLess(len(discoveries), 5)

    def test_download_discoveries_stop_when_cancellation_is_requested(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.downloads = FakeDownloads()
        hunter.state = FakeState()
        hunter.journal = FakeJournal()
        hunter.settings = type(
            "Settings",
            (),
            {
                "download": type(
                    "DownloadSettings",
                    (),
                    {
                        "mirror_backoff_base_seconds": 60,
                        "mirror_backoff_cap_seconds": 300,
                    },
                )()
            },
        )()

        cancelled = Event()
        original_process = hunter.downloads.process

        def process_and_cancel(*args, **kwargs):
            result = original_process(*args, **kwargs)
            cancelled.set()
            return result

        hunter.downloads.process = process_and_cancel

        discoveries = [
            DiscoverySelection(
                plugin=PluginSpec(slug=f"plugin_{index}", name=f"Plugin {index}", module=object()),
                ranked=[Candidate(url=f"https://good.example/test-{index}.iso", filename=f"test-{index}.iso")],
                selected=Candidate(url=f"https://good.example/test-{index}.iso", filename=f"test-{index}.iso"),
            )
            for index in range(3)
        ]

        results = DistroHunter.download_discoveries(
            hunter,
            discoveries,
            dry_run=True,
            should_cancel=cancelled.is_set,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(hunter.downloads.seen, ["https://good.example/test-0.iso"])


if __name__ == "__main__":
    unittest.main()
