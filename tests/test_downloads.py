import bz2
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from distro_hunter.checksums import ExpectedChecksum
from distro_hunter.config import DownloadSettings, GeneratorSettings, LoggingSettings, PluginSettings, Settings, VentoySettings
from distro_hunter.downloads import DownloadManager
from distro_hunter.models import Candidate
from distro_hunter.state import StateStore


class FakeState:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def get_plugin_record(self, plugin_slug: str) -> dict:
        return self.records.setdefault(plugin_slug, {})

    def find_download_owner(self, path_text: str, *, excluding_plugin: str | None = None):
        return None

    def download_history_paths(self, plugin_slug: str) -> list[str]:
        return []


class FakeWeb:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self.payload = payload
        self.final_url = final_url
        self.download_calls = 0

    def inspect_remote_file(self, url: str):
        return {"Content-Length": str(len(self.payload))}, self.final_url

    def download(self, url: str, destination: str, progress_callback=None) -> None:
        self.download_calls += 1
        Path(destination).write_bytes(self.payload)
        if progress_callback:
            progress_callback(len(self.payload), len(self.payload))


class DownloadManagerTests(unittest.TestCase):
    def _settings(self, download_dir: Path) -> Settings:
        return Settings(
            config_path=download_dir / "config.example.json",
            state_file=download_dir / "state.json",
            plugins=PluginSettings(builtin=[], directories=[]),
            download=DownloadSettings(
                download_dir=download_dir,
                aria2_path=None,
                prefer_aria2=False,
                decompress_bz2=True,
            ),
            ventoy=VentoySettings(enabled=False),
            generator=GeneratorSettings(output_dir=download_dir),
            logging=LoggingSettings(run_log_file=None, mirror_failures_file=None),
        )

    def test_process_decompresses_bz2_artifacts_after_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            payload = bz2.compress(b"steam deck image")
            manager = DownloadManager(self._settings(download_dir), FakeState())
            manager.web = FakeWeb(payload, "https://example.com/steamdeck-repair-latest.img.bz2")

            result = manager.process(
                "steamos_recovery",
                Candidate(url="https://example.com/steamdeck-repair-latest.img.bz2"),
            )

            archive_path = download_dir / "steamdeck-repair-latest.img.bz2"
            output_path = download_dir / "steamdeck-repair-latest.img"
            self.assertTrue(result.downloaded)
            self.assertEqual(result.path, output_path)
            self.assertTrue(archive_path.exists())
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"steam deck image")

    def test_process_rebuilds_missing_decompressed_image_without_redownloading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            payload = bz2.compress(b"steam deck image")
            archive_path = download_dir / "steamdeck-repair-latest.img.bz2"
            archive_path.write_bytes(payload)

            manager = DownloadManager(self._settings(download_dir), FakeState())
            fake_web = FakeWeb(payload, "https://example.com/steamdeck-repair-latest.img.bz2")
            manager.web = fake_web

            result = manager.process(
                "steamos_recovery",
                Candidate(url="https://example.com/steamdeck-repair-latest.img.bz2"),
            )

            output_path = download_dir / "steamdeck-repair-latest.img"
            self.assertFalse(result.downloaded)
            self.assertEqual(result.skipped_reason, "local file matches remote metadata")
            self.assertEqual(result.path, output_path)
            self.assertEqual(fake_web.download_calls, 0)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"steam deck image")

    def test_process_uses_collision_safe_filename_when_another_plugin_owns_default_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            state = StateStore(download_dir / "state.json", download_dir=download_dir)
            state.data["plugins"]["plugin_a"] = {
                "download": {
                    "path": "latest.iso",
                    "filename": "latest.iso",
                    "remote": {
                        "url": "https://mirror-a.example/latest.iso",
                        "final_url": "https://mirror-a.example/latest.iso",
                    },
                }
            }

            manager = DownloadManager(self._settings(download_dir), state)
            manager.web = FakeWeb(b"payload", "https://mirror-b.example/latest.iso")

            result = manager.process("plugin_b", Candidate(url="https://mirror-b.example/latest.iso", filename="latest.iso"))

            self.assertEqual(result.path, download_dir / "plugin_b--latest.iso")
            self.assertEqual(result.candidate.filename, "plugin_b--latest.iso")
            self.assertTrue((download_dir / "plugin_b--latest.iso").exists())

    def test_process_prunes_older_downloads_for_plugin_when_retention_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            state = StateStore(download_dir / "state.json", download_dir=download_dir)
            old_path = download_dir / "ubuntu-old.iso"
            old_path.write_bytes(b"old")
            state.data["plugins"]["ubuntu_lts"] = {
                "download": {
                    "path": "ubuntu-old.iso",
                    "filename": "ubuntu-old.iso",
                    "downloaded": True,
                    "remote": {
                        "url": "https://example.org/ubuntu-old.iso",
                        "final_url": "https://example.org/ubuntu-old.iso",
                    },
                },
                "history": [
                    {
                        "recorded_at": "2026-03-30T00:00:00+00:00",
                        "event": "download",
                        "path": "ubuntu-old.iso",
                        "filename": "ubuntu-old.iso",
                        "downloaded": True,
                        "skipped_reason": None,
                    }
                ],
            }
            settings = self._settings(download_dir)
            settings.download.retention_keep_latest = 1
            manager = DownloadManager(settings, state)
            manager.web = FakeWeb(b"new-payload", "https://example.org/ubuntu-new.iso")

            result = manager.process("ubuntu_lts", Candidate(url="https://example.org/ubuntu-new.iso", filename="ubuntu-new.iso"))

            self.assertTrue(result.downloaded)
            self.assertEqual(result.path, download_dir / "ubuntu-new.iso")
            self.assertFalse(old_path.exists())
            self.assertEqual(result.pruned_paths, [old_path.resolve()])

    def test_process_reuses_cached_verified_checksum_for_unchanged_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            state = StateStore(download_dir / "state.json", download_dir=download_dir)
            local_path = download_dir / "ubuntu.iso"
            local_path.write_bytes(b"iso-payload")
            local_stat = local_path.stat()
            state.data["plugins"]["ubuntu_lts"] = {
                "download": {
                    "path": "ubuntu.iso",
                    "filename": "ubuntu.iso",
                    "remote": {
                        "url": "https://example.org/ubuntu.iso",
                        "final_url": "https://example.org/ubuntu.iso",
                        "size": len(b"iso-payload"),
                        "etag": "same",
                        "last_modified": "Tue, 11 Mar 2026 00:00:00 GMT",
                    },
                    "checksum": {
                        "status": "verified",
                        "algorithm": "sha256",
                        "expected": "abc123",
                        "actual": "abc123",
                        "source": "https://example.org/ubuntu.sha256",
                        "file_size": local_stat.st_size,
                        "file_mtime_ns": local_stat.st_mtime_ns,
                    },
                }
            }

            manager = DownloadManager(self._settings(download_dir), state)
            manager.web = FakeWeb(b"iso-payload", "https://example.org/ubuntu.iso")
            manager._resolve_expected_checksum = lambda candidate, remote: ExpectedChecksum(
                algorithm="sha256",
                digest="abc123",
                source="https://example.org/ubuntu.sha256",
            )

            with patch("distro_hunter.downloads.verify_file_checksum", side_effect=AssertionError("should not rehash")):
                result = manager.process(
                    "ubuntu_lts",
                    Candidate(
                        url="https://example.org/ubuntu.iso",
                        filename="ubuntu.iso",
                    ),
                )

            self.assertFalse(result.downloaded)
            self.assertEqual(result.skipped_reason, "local file matches remote metadata")
            self.assertEqual(result.checksum.status, "verified")

    def test_process_extracts_single_disk_image_from_zip_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            archive_path = download_dir / "FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("FydeOS_for_PC_iris_v22.0-SP1-io.bin", b"fydeos-image")

            manager = DownloadManager(self._settings(download_dir), FakeState())
            fake_web = FakeWeb(archive_path.read_bytes(), "https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip")
            manager.web = fake_web

            result = manager.process(
                "fydeos_pc_modern",
                Candidate(url="https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip"),
            )

            output_path = download_dir / "FydeOS_for_PC_iris_v22.0-SP1-io.img"
            self.assertFalse(result.downloaded)
            self.assertEqual(result.skipped_reason, "local file matches remote metadata")
            self.assertEqual(result.path, output_path)
            self.assertEqual(fake_web.download_calls, 0)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), b"fydeos-image")
