import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from distro_hunter.models import Candidate, DownloadResult, RemoteFileInfo
from distro_hunter.state import MAX_HISTORY_EVENTS, STATE_VERSION, StateStore


class StateStoreTests(unittest.TestCase):
    def test_remember_download_stores_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            artifact = download_dir / "ubuntu.iso"
            artifact.write_bytes(b"iso")
            state_path = root / "state.json"
            store = StateStore(state_path, download_dir=download_dir)

            result = DownloadResult(
                plugin_slug="ubuntu_lts",
                candidate=Candidate(url="https://example.org/ubuntu.iso", filename="ubuntu.iso"),
                path=artifact,
                downloaded=True,
                remote=RemoteFileInfo(
                    url="https://example.org/ubuntu.iso",
                    final_url="https://mirror.example.org/ubuntu.iso",
                    filename="ubuntu.iso",
                ),
            )

            store.remember_download(result)

            download_record = store.get_plugin_record("ubuntu_lts")["download"]
            self.assertEqual(download_record["path"], "ubuntu.iso")
            self.assertEqual(download_record["filename"], "ubuntu.iso")
            self.assertTrue(download_record["downloaded"])

    def test_state_store_migrates_absolute_download_paths_to_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            state_path = root / "state.json"
            payload = {
                "plugins": {
                    "ubuntu_lts": {
                        "download": {
                            "path": str(download_dir / "ubuntu.iso"),
                            "filename": "ubuntu.iso",
                        }
                    }
                }
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            store = StateStore(state_path, download_dir=download_dir)

            self.assertEqual(store.data["state_version"], STATE_VERSION)
            self.assertEqual(
                store.data["plugins"]["ubuntu_lts"]["download"]["path"],
                "ubuntu.iso",
            )
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["plugins"]["ubuntu_lts"]["download"]["path"], "ubuntu.iso")

    def test_state_store_falls_back_to_filename_for_stale_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            state_path = root / "state.json"
            payload = {
                "plugins": {
                    "ubuntu_lts": {
                        "download": {
                            "path": r"J:\SCRIPTS\DISTRO-HUNTER\downloads\ubuntu.iso",
                            "filename": "ubuntu.iso",
                        }
                    }
                }
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            store = StateStore(state_path, download_dir=download_dir)

            self.assertEqual(
                store.data["plugins"]["ubuntu_lts"]["download"]["path"],
                "ubuntu.iso",
            )

    def test_state_store_migrates_downloaded_flag_from_local_artifact_presence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            (download_dir / "ubuntu.iso").write_bytes(b"iso")
            state_path = root / "state.json"
            payload = {
                "state_version": STATE_VERSION,
                "plugins": {
                    "ubuntu_lts": {
                        "download": {
                            "path": "ubuntu.iso",
                            "filename": "ubuntu.iso",
                            "downloaded": False,
                        }
                    }
                },
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            store = StateStore(state_path, download_dir=download_dir)

            self.assertTrue(store.data["plugins"]["ubuntu_lts"]["download"]["downloaded"])

    def test_remember_download_marks_existing_artifact_available_after_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            artifact = download_dir / "ubuntu.iso"
            artifact.write_bytes(b"iso")
            store = StateStore(root / "state.json", download_dir=download_dir)

            store.remember_download(
                DownloadResult(
                    plugin_slug="ubuntu_lts",
                    candidate=Candidate(url="https://example.org/ubuntu.iso", filename="ubuntu.iso"),
                    path=artifact,
                    downloaded=False,
                    skipped_reason="local file matches remote metadata",
                    remote=RemoteFileInfo(
                        url="https://example.org/ubuntu.iso",
                        final_url="https://mirror.example.org/ubuntu.iso",
                        filename="ubuntu.iso",
                    ),
                )
            )

            self.assertTrue(store.get_plugin_record("ubuntu_lts")["download"]["downloaded"])

    def test_remember_health_tracks_failures_and_resets_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            store = StateStore(state_path, download_dir=root / "downloads")

            store.remember_health("ubuntu_lts", status="download head failed", healthy=False, error="timed out")
            first = store.get_plugin_record("ubuntu_lts")["health"]
            self.assertFalse(first["healthy"])
            self.assertEqual(first["last_status"], "download head failed")
            self.assertEqual(first["failure_count"], 1)
            self.assertEqual(first["last_error"], "timed out")
            self.assertIsNotNone(first["last_failure_at"])

            store.remember_health("ubuntu_lts", status="no candidates", healthy=False)
            second = store.get_plugin_record("ubuntu_lts")["health"]
            self.assertEqual(second["failure_count"], 2)
            self.assertEqual(second["last_error"], "no candidates")

            store.remember_health("ubuntu_lts", status="ok", healthy=True)
            final = store.get_plugin_record("ubuntu_lts")["health"]
            self.assertTrue(final["healthy"])
            self.assertEqual(final["last_status"], "ok")
            self.assertEqual(final["failure_count"], 0)
            self.assertIsNone(final["last_error"])
            self.assertIsNotNone(final["last_success_at"])

    def test_history_tracks_selection_download_and_health_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            state_path = root / "state.json"
            store = StateStore(state_path, download_dir=download_dir)

            candidate = Candidate(url="https://example.org/ubuntu-24.04.4.iso", filename="ubuntu-24.04.4.iso", version="24.04.4")
            store.remember_selection("ubuntu_lts", candidate)
            store.remember_selection("ubuntu_lts", candidate)
            store.remember_health("ubuntu_lts", status="ok", healthy=True)
            store.remember_health("ubuntu_lts", status="ok", healthy=True)
            store.remember_download(
                DownloadResult(
                    plugin_slug="ubuntu_lts",
                    candidate=candidate,
                    path=download_dir / "ubuntu-24.04.4.iso",
                    downloaded=False,
                    skipped_reason="dry run",
                    remote=RemoteFileInfo(
                        url="https://example.org/ubuntu-24.04.4.iso",
                        final_url="https://mirror.example.org/ubuntu-24.04.4.iso",
                        filename="ubuntu-24.04.4.iso",
                    ),
                )
            )
            store.remember_download(
                DownloadResult(
                    plugin_slug="ubuntu_lts",
                    candidate=candidate,
                    path=download_dir / "ubuntu-24.04.4.iso",
                    downloaded=False,
                    skipped_reason="dry run",
                    remote=RemoteFileInfo(
                        url="https://example.org/ubuntu-24.04.4.iso",
                        final_url="https://mirror.example.org/ubuntu-24.04.4.iso",
                        filename="ubuntu-24.04.4.iso",
                    ),
                )
            )
            store.remember_selection(
                "ubuntu_lts",
                Candidate(url="https://example.org/ubuntu-24.04.5.iso", filename="ubuntu-24.04.5.iso", version="24.04.5"),
            )

            history = store.get_plugin_record("ubuntu_lts")["history"]
            self.assertEqual([entry["event"] for entry in history], ["selection", "health", "download", "selection"])
            self.assertEqual(history[-1]["version"], "24.04.5")

    def test_history_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            store = StateStore(state_path, download_dir=root / "downloads")

            for index in range(MAX_HISTORY_EVENTS + 5):
                store.remember_health("ubuntu_lts", status=f"status-{index}", healthy=False)

            history = store.get_plugin_record("ubuntu_lts")["history"]
            self.assertEqual(len(history), MAX_HISTORY_EVENTS)
            self.assertEqual(history[0]["status"], "status-5")

    def test_remember_mirror_failure_sets_backoff_and_success_clears_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            store = StateStore(state_path, download_dir=root / "downloads")

            store.remember_mirror_failure(
                "https://bad.example/releases/test.iso",
                error="403 Forbidden",
                backoff_base_seconds=60,
                backoff_cap_seconds=300,
            )
            first = store.data["mirrors"]["bad.example"]
            first_backoff = datetime.fromisoformat(first["backoff_until"])
            self.assertEqual(first["failure_count"], 1)
            self.assertEqual(first["last_error"], "403 Forbidden")
            self.assertEqual(store.mirror_host_for_url("https://bad.example/other.iso"), "bad.example")
            self.assertIsNotNone(store.mirror_backoff_until("https://bad.example/other.iso"))

            store.remember_mirror_failure(
                "https://bad.example/releases/test.iso",
                error="timeout",
                backoff_base_seconds=60,
                backoff_cap_seconds=300,
            )
            second = store.data["mirrors"]["bad.example"]
            second_backoff = datetime.fromisoformat(second["backoff_until"])
            self.assertEqual(second["failure_count"], 2)
            self.assertEqual(second["last_error"], "timeout")
            self.assertGreater(second_backoff, first_backoff)

            store.remember_mirror_success("https://bad.example/releases/test.iso")
            final = store.data["mirrors"]["bad.example"]
            self.assertEqual(final["failure_count"], 0)
            self.assertIsNone(final["backoff_until"])
            self.assertIsNone(final["last_error"])
            self.assertIsNotNone(final["last_success_at"])

    def test_prioritize_mirror_candidates_deprioritizes_hosts_in_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            store = StateStore(state_path, download_dir=root / "downloads")

            bad = Candidate(url="https://bad.example/test.iso", filename="test.iso")
            good = Candidate(url="https://good.example/test.iso", filename="test.iso")

            store.remember_mirror_failure(
                bad.url,
                error="timed out",
                backoff_base_seconds=60,
                backoff_cap_seconds=300,
            )

            ordered = store.prioritize_mirror_candidates([bad, good])
            self.assertEqual([candidate.url for candidate in ordered], [good.url, bad.url])

            store.remember_mirror_success(bad.url)
            restored = store.prioritize_mirror_candidates([bad, good])
            self.assertEqual([candidate.url for candidate in restored], [bad.url, good.url])


if __name__ == "__main__":
    unittest.main()
