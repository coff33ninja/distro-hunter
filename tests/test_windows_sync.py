from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import py7zr

from distro_hunter.config import Settings, load_settings
from distro_hunter.core import DistroHunter
from distro_hunter.downloads import DownloadManager
from distro_hunter.journal import RunJournal
from distro_hunter.models import Candidate, DownloadResult
from distro_hunter.plugin_loader import load_plugins
from distro_hunter.plugins.windows_common import CATALOG, ventoy_subdir
from distro_hunter.state import StateStore
from distro_hunter.ventoy import (
    DriveInfo,
    infer_plugin_subdir,
    sync_directory_to_ventoy,
    sync_paths_to_ventoy,
)

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_11_X64 = Path("ISO/Windows/Windows 11/official/x64")
WINDOWS_1_0_X86 = Path("ISO/Windows/Windows 1.0/official/x86")


def _windows_hunter_for_sync(settings: Settings) -> DistroHunter:
    hunter = object.__new__(DistroHunter)
    hunter.settings = settings
    hunter.state = StateStore(settings.state_file, download_dir=settings.download.download_dir)
    hunter.plugin_map = {plugin.slug: plugin for plugin in load_plugins(settings)}
    hunter.downloads = DownloadManager(settings, hunter.state)
    hunter.journal = RunJournal(settings.logging)
    return hunter


def _windows_library_path(drive_root: Path, filename: str) -> Path:
    return drive_root / WINDOWS_11_X64 / filename


def _windows_state_path(filename: str) -> str:
    return (Path("../ventoy") / WINDOWS_11_X64 / filename).as_posix()


def _windows_1_0_state_path(filename: str) -> str:
    return (Path("../ventoy") / WINDOWS_1_0_X86 / filename).as_posix()


EXPECTED = {
    "windows_11_24h2_x64": "Windows 11/official/x64",
    "windows_10_22h2_x86": "Windows 10/official/x86",
    "windows_8_x64": "Windows 8/official/x64",
    "windows_8_1_x64": "Windows 8.1/official/x64",
    "windows_7_sp1_x64": "Windows 7/official/x64",
    "windows_xp_pro_sp3_x86": "Windows XP/official/x86",
    "windows_95_rtm_x86": "Windows 95/official/x86",
    "windows_me_x86": "Windows Me/official/x86",
    "windows_nt_4_0_server_x86": "Windows NT 4.0/official/x86",
    "windows_neptune_5111_x86": "Windows Neptune/official/x86",
    "windows_server_2022_x64": "Windows Server/2022/official/x64",
    "windows_1_04_x86": "Windows 1.0/official/x86",
}


class WindowsSyncLayoutTests(unittest.TestCase):
    def test_windows_profile_extracts_and_syncs_floppy_images(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        self.assertTrue(settings.download.extract_7z)
        self.assertIn(".img", settings.ventoy.copy_extensions)

    def test_subdir_matches_canonical_windows_library_layout(self) -> None:
        for slug, expected in EXPECTED.items():
            self.assertEqual(ventoy_subdir(slug), expected, slug)
        for slug in CATALOG:
            parts = ventoy_subdir(slug).split("/")
            self.assertGreaterEqual(len(parts), 3, slug)
            self.assertTrue(all(parts), slug)

    def test_windows_and_linux_sync_side_by_side_on_one_drive(self) -> None:
        windows = load_settings(ROOT / "config.windows.json")
        linux = load_settings(ROOT / "config.json")
        plugins = {plugin.slug: plugin for plugin in load_plugins(windows)}

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)
            win_iso = base / "win" / "Windows_11_24H2_26100_x64_en-US.iso"
            lin_iso = base / "lin" / "ubuntu-24.04-desktop-amd64.iso"
            for path in (win_iso, lin_iso):
                path.parent.mkdir(parents=True)
                path.write_bytes(b"iso")

            sync_paths_to_ventoy(
                [win_iso],
                drive,
                windows.ventoy,
                route_map={win_iso.resolve(): Path(plugins["windows_11_24h2_x64"].ventoy_subdir)},
            )
            linux_subdir = infer_plugin_subdir("ubuntu_lts")
            sync_directory_to_ventoy(
                lin_iso.parent,
                drive,
                linux.ventoy,
                route_map={lin_iso.resolve(): linux_subdir},
            )

            self.assertTrue(
                (
                    drive.root
                    / "ISO/Windows/Windows 11/official/x64/Windows_11_24H2_26100_x64_en-US.iso"
                ).is_file()
            )
            self.assertTrue((drive.root / "ISO/Linux" / linux_subdir / lin_iso.name).is_file())
            self.assertFalse(win_iso.exists())  # moved, like the Linux flow

    def test_sync_download_result_copies_every_extracted_image(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)
            images = [base / "downloads" / f"disk{index}.img" for index in (1, 2, 3)]
            for image in images:
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_bytes(b"image")

            result = DownloadResult(
                plugin_slug="windows_dos_6_0_x86",
                candidate=Candidate(url="https://archive.org/download/set/disk1.img"),
                path=images[0],
                downloaded=True,
                artifact_paths=images,
            )
            hunter = object.__new__(DistroHunter)
            hunter.settings = settings
            with (
                patch("distro_hunter.core.detect_ventoy_drive", return_value=drive),
                patch.object(DistroHunter, "_build_ventoy_route_map", return_value={}),
            ):
                sync_root, copied = hunter.sync_download_result(result)

            self.assertEqual(sync_root, drive.root)
            self.assertEqual(len(copied), 3)
            self.assertEqual(
                {path.name for path in copied},
                {"disk1.img", "disk2.img", "disk3.img"},
            )
            self.assertTrue(all(path.is_file() for path in copied))

    def test_sync_ventoy_updates_only_moved_artifact_paths(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp) / "downloads"
            download_dir.mkdir()
            settings.download.download_dir = download_dir
            settings.state_file = Path(tmp) / "state.json"
            drive = DriveInfo(root=Path(tmp) / "ventoy", label="Ventoy", drive_type=2, score=1)
            moved_source = download_dir / "disk1.iso"
            skipped_source = download_dir / "disk2.iso"
            moved_source.write_bytes(b"disk one")
            skipped_source.write_bytes(b"disk two")
            skipped_target = _windows_library_path(drive.root, "disk2.iso")
            skipped_target.parent.mkdir(parents=True)
            skipped_target.write_bytes(b"existing disk two")
            recovered_target = _windows_library_path(drive.root, "disk3.iso")
            recovered_target.parent.mkdir(parents=True, exist_ok=True)
            recovered_target.write_bytes(b"previously moved disk three")

            hunter = _windows_hunter_for_sync(settings)
            hunter.state.get_plugin_record("windows_11_24h2_x64")["download"] = {
                "path": moved_source.name,
                "filename": moved_source.name,
                "artifact_paths": [
                    moved_source.name,
                    skipped_source.name,
                    "disk3.iso",
                ],
                "downloaded": True,
            }
            hunter.state.save()
            with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                _, copied = hunter.sync_ventoy()

            moved_target = _windows_library_path(drive.root, "disk1.iso")
            moved_state_path = _windows_state_path("disk1.iso")
            self.assertEqual(copied, [moved_target])
            self.assertFalse(moved_source.exists())
            self.assertTrue(skipped_source.exists())

            download = StateStore(settings.state_file, download_dir=download_dir).get_plugin_record(
                "windows_11_24h2_x64"
            )["download"]
            self.assertEqual(download["path"], moved_state_path)
            self.assertEqual(
                download["artifact_paths"],
                [
                    moved_state_path,
                    skipped_source.name,
                    _windows_state_path("disk3.iso"),
                ],
            )

    def test_sync_removes_download_when_matching_ventoy_file_exists(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            download_dir = base / "downloads"
            download_dir.mkdir()
            settings.download.download_dir = download_dir
            settings.state_file = base / "state.json"
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)
            source = download_dir / "disk.iso"
            source.write_bytes(b"same image contents")
            target = _windows_library_path(drive.root, source.name)
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())

            hunter = _windows_hunter_for_sync(settings)
            hunter.state.get_plugin_record("windows_11_24h2_x64")["download"] = {
                "path": f"../downloads/{source.name}",
                "filename": source.name,
                "artifact_paths": [f"../downloads/{source.name}"],
                "downloaded": True,
            }
            hunter.state.save()
            with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                _, copied = hunter.sync_ventoy()

            self.assertEqual(copied, [])
            self.assertFalse(source.exists())
            self.assertTrue(target.is_file())
            download = StateStore(
                settings.state_file,
                download_dir=download_dir,
            ).get_plugin_record("windows_11_24h2_x64")["download"]
            self.assertEqual(download["path"], _windows_state_path("disk.iso"))
            self.assertEqual(download["artifact_paths"], [_windows_state_path("disk.iso")])

    def test_sync_reconciles_state_tracked_image_from_sibling_downloads(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            download_dir = base / "downloads_windows"
            download_dir.mkdir()
            legacy_download_dir = base / "downloads"
            legacy_download_dir.mkdir()
            settings.download.download_dir = download_dir
            settings.state_file = base / "state.json"
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)
            source = legacy_download_dir / "disk.iso"
            source.write_bytes(b"same image contents")
            target = _windows_library_path(drive.root, source.name)
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())

            hunter = _windows_hunter_for_sync(settings)
            hunter.state.get_plugin_record("windows_11_24h2_x64")["download"] = {
                "path": f"../downloads/{source.name}",
                "filename": source.name,
                "artifact_paths": [f"../downloads/{source.name}"],
                "downloaded": True,
            }
            hunter.state.save()
            with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                _, copied = hunter.sync_ventoy()

            self.assertEqual(copied, [])
            self.assertFalse(source.exists())
            self.assertTrue(target.is_file())
            download = StateStore(
                settings.state_file,
                download_dir=download_dir,
            ).get_plugin_record("windows_11_24h2_x64")["download"]
            self.assertEqual(download["path"], _windows_state_path("disk.iso"))
            self.assertEqual(download["artifact_paths"], [_windows_state_path("disk.iso")])

    def test_sync_moves_state_tracked_image_from_sibling_downloads(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            download_dir = base / "downloads_windows"
            download_dir.mkdir()
            legacy_download_dir = base / "downloads"
            legacy_download_dir.mkdir()
            settings.download.download_dir = download_dir
            settings.state_file = base / "state.json"
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)
            source = legacy_download_dir / "disk.iso"
            source.write_bytes(b"new image contents")

            hunter = _windows_hunter_for_sync(settings)
            hunter.state.get_plugin_record("windows_11_24h2_x64")["download"] = {
                "path": f"../downloads/{source.name}",
                "filename": source.name,
                "artifact_paths": [f"../downloads/{source.name}"],
                "downloaded": True,
            }
            hunter.state.save()
            with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                _, copied = hunter.sync_ventoy()

            target = _windows_library_path(drive.root, source.name)
            self.assertEqual(copied, [target])
            self.assertFalse(source.exists())
            self.assertEqual(target.read_bytes(), b"new image contents")
            download = StateStore(
                settings.state_file,
                download_dir=download_dir,
            ).get_plugin_record("windows_11_24h2_x64")["download"]
            self.assertEqual(download["path"], _windows_state_path("disk.iso"))

    def test_sync_extracts_7z_images_and_deletes_archive_after_sync(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            download_dir = base / "downloads"
            download_dir.mkdir()
            settings.download.download_dir = download_dir
            settings.state_file = base / "state.json"
            archive_path = download_dir / "windows-1.04.7z"
            source_image = base / "disk.img"
            source_image.write_bytes(b"floppy image")
            with py7zr.SevenZipFile(archive_path, "w") as archive:
                archive.write(source_image, "Disk1.img")

            state = StateStore(settings.state_file, download_dir=download_dir)
            state.get_plugin_record("windows_1_04_x86")["download"] = {
                "path": archive_path.name,
                "filename": archive_path.name,
                "artifact_paths": [],
                "downloaded": True,
            }
            state.save()
            hunter = _windows_hunter_for_sync(settings)
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)

            with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                _, copied = hunter.sync_ventoy()

            output_name = "windows-1.04--Disk1.img"
            target = drive.root / WINDOWS_1_0_X86 / output_name
            self.assertEqual(copied, [target])
            self.assertFalse(archive_path.exists())
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), b"floppy image")
            download = StateStore(
                settings.state_file,
                download_dir=download_dir,
            ).get_plugin_record("windows_1_04_x86")["download"]
            self.assertFalse(download["downloaded"])
            self.assertEqual(download["artifact_paths"], [_windows_1_0_state_path(output_name)])

    def test_sync_deletes_7z_when_existing_image_matches_and_keeps_conflicts(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        for target_content, should_delete in (
            (b"floppy image", True),
            (b"different image", False),
        ):
            with self.subTest(should_delete=should_delete), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                download_dir = base / "downloads"
                download_dir.mkdir()
                settings.download.download_dir = download_dir
                settings.state_file = base / "state.json"
                archive_path = download_dir / "windows-1.04.7z"
                source_image = base / "disk.img"
                source_image.write_bytes(b"floppy image")
                with py7zr.SevenZipFile(archive_path, "w") as archive:
                    archive.write(source_image, "Disk1.img")

                state = StateStore(settings.state_file, download_dir=download_dir)
                state.get_plugin_record("windows_1_04_x86")["download"] = {
                    "path": archive_path.name,
                    "filename": archive_path.name,
                    "artifact_paths": [],
                    "downloaded": True,
                }
                state.save()
                hunter = _windows_hunter_for_sync(settings)
                drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)
                target = drive.root / WINDOWS_1_0_X86 / "windows-1.04--Disk1.img"
                target.parent.mkdir(parents=True)
                target.write_bytes(target_content)

                with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                    hunter.sync_ventoy()

                self.assertEqual(archive_path.exists(), not should_delete)
                self.assertEqual(
                    (download_dir / "windows-1.04--Disk1.img").exists(),
                    not should_delete,
                )

    def test_sync_retains_7z_when_archive_extraction_fails(self) -> None:
        settings = load_settings(ROOT / "config.windows.json")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            download_dir = base / "downloads"
            download_dir.mkdir()
            settings.download.download_dir = download_dir
            settings.state_file = base / "state.json"
            archive_path = download_dir / "windows-1.04.7z"
            archive_path.write_bytes(b"not a 7z archive")

            state = StateStore(settings.state_file, download_dir=download_dir)
            state.get_plugin_record("windows_1_04_x86")["download"] = {
                "path": archive_path.name,
                "filename": archive_path.name,
                "artifact_paths": [],
                "downloaded": True,
            }
            state.save()
            hunter = _windows_hunter_for_sync(settings)
            drive = DriveInfo(root=base / "ventoy", label="Ventoy", drive_type=2, score=1)

            with patch("distro_hunter.core.detect_ventoy_drive", return_value=drive):
                _, copied = hunter.sync_ventoy()

            self.assertEqual(copied, [])
            self.assertTrue(archive_path.is_file())
            download = StateStore(
                settings.state_file,
                download_dir=download_dir,
            ).get_plugin_record("windows_1_04_x86")["download"]
            self.assertTrue(download["downloaded"])


if __name__ == "__main__":
    unittest.main()
