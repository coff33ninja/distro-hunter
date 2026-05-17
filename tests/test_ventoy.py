import tempfile
import unittest
from pathlib import Path

from distro_hunter.config import DownloadSettings, GeneratorSettings, LoggingSettings, ManualSourceRule, PluginSettings, Settings, VentoySettings
from distro_hunter.core import DistroHunter
from distro_hunter.plugin_loader import PluginSpec
from distro_hunter.plugin_metadata import metadata_from_fields
from distro_hunter.ventoy import DriveInfo, infer_plugin_subdir, sync_directory_to_ventoy, sync_paths_to_ventoy


class VentoySyncTests(unittest.TestCase):
    def test_sync_organizes_files_into_linux_subfolders(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as drive_root:
            source_path = Path(source_dir)
            drive_path = Path(drive_root)
            destination = drive_path / "ISO" / "Linux"
            destination.mkdir(parents=True)

            steam = source_path / "steamdeck-repair-latest.img"
            ubuntu = source_path / "ubuntu-24.04.4-live-server-amd64.iso"
            manual = source_path / "manual-custom.iso"
            steam.write_bytes(b"steam")
            ubuntu.write_bytes(b"ubuntu")
            manual.write_bytes(b"manual")
            (source_path / "ubuntu.iso").write_bytes(b"ubuntu")
            (source_path / "ignore.txt").write_bytes(b"nope")

            drive = DriveInfo(root=drive_path, label="Ventoy", drive_type=2, score=100)
            settings = VentoySettings(
                destination_subdir="ISO/Linux",
                copy_extensions=[".iso", ".img"],
                organize_by_plugin=True,
                manual_subdir="manual",
            )
            route_map = {
                steam.resolve(): infer_plugin_subdir("steamos_recovery"),
                ubuntu.resolve(): infer_plugin_subdir("ubuntu_server_lts"),
            }

            copied = sync_directory_to_ventoy(source_path, drive, settings, route_map=route_map)

            self.assertEqual(
                {str(path.relative_to(drive_path)).replace("\\", "/") for path in copied},
                {
                    "ISO/Linux/manual/manual-custom.iso",
                    "ISO/Linux/manual/ubuntu.iso",
                    "ISO/Linux/steamos/recovery/steamdeck-repair-latest.img",
                    "ISO/Linux/ubuntu/server/ubuntu-24.04.4-live-server-amd64.iso",
                },
            )
            self.assertTrue((destination / "steamos" / "recovery" / steam.name).exists())
            self.assertTrue((destination / "ubuntu" / "server" / ubuntu.name).exists())
            self.assertTrue((destination / "manual" / manual.name).exists())
            self.assertTrue((destination / "manual" / "ubuntu.iso").exists())
            self.assertFalse((destination / "ignore.txt").exists())

    def test_sync_prunes_nested_linux_subfolders(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as drive_root:
            source_path = Path(source_dir)
            drive_path = Path(drive_root)
            destination = drive_path / "ISO" / "Linux"
            (destination / "ubuntu" / "server").mkdir(parents=True)
            (destination / "manual").mkdir(parents=True)

            kept = source_path / "ubuntu-24.04.4-live-server-amd64.iso"
            kept.write_bytes(b"keep")
            (destination / "ubuntu" / "server" / kept.name).write_bytes(b"keep")
            (destination / "manual" / "old.img").write_bytes(b"old")

            drive = DriveInfo(root=drive_path, label="Ventoy", drive_type=2, score=100)
            settings = VentoySettings(
                destination_subdir="ISO/Linux",
                copy_extensions=[".iso", ".img"],
                organize_by_plugin=True,
                prune_removed=True,
            )
            route_map = {
                kept.resolve(): infer_plugin_subdir("ubuntu_server_lts"),
            }

            copied = sync_directory_to_ventoy(source_path, drive, settings, route_map=route_map)

            self.assertEqual(copied, [])
            self.assertTrue((destination / "ubuntu" / "server" / kept.name).exists())
            self.assertFalse((destination / "manual" / "old.img").exists())

    def test_sync_paths_to_ventoy_copies_selected_artifact_only(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as drive_root:
            source_path = Path(source_dir)
            drive_path = Path(drive_root)
            selected = source_path / "ubuntu-24.04.4-live-server-amd64.iso"
            ignored = source_path / "manual-custom.iso"
            selected.write_bytes(b"ubuntu")
            ignored.write_bytes(b"manual")

            drive = DriveInfo(root=drive_path, label="Ventoy", drive_type=2, score=100)
            settings = VentoySettings(destination_subdir="ISO/Linux", copy_extensions=[".iso"], organize_by_plugin=True)
            route_map = {
                selected.resolve(): infer_plugin_subdir("ubuntu_server_lts"),
                ignored.resolve(): Path("manual"),
            }

            copied = sync_paths_to_ventoy([selected], drive, settings, route_map=route_map)

            self.assertEqual(
                {str(path.relative_to(drive_path)).replace("\\", "/") for path in copied},
                {"ISO/Linux/ubuntu/server/ubuntu-24.04.4-live-server-amd64.iso"},
            )
            self.assertTrue((drive_path / "ISO" / "Linux" / "ubuntu" / "server" / selected.name).exists())
            self.assertFalse((drive_path / "ISO" / "Linux" / "manual" / ignored.name).exists())

    def test_infer_plugin_subdir_uses_family_and_type(self) -> None:
        self.assertEqual(infer_plugin_subdir("ubuntu_server_lts"), Path("ubuntu/server"))
        self.assertEqual(infer_plugin_subdir("steamos_recovery"), Path("steamos/recovery"))
        self.assertEqual(infer_plugin_subdir("garuda_dr460nized_gaming"), Path("garuda/dr460nized-gaming"))

    def test_build_ventoy_route_map_uses_manual_source_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            tracked = download_dir / "ubuntu.iso"
            tracked.write_bytes(b"ubuntu")
            manual = download_dir / "bazzite-deck.iso"
            manual.write_bytes(b"bazzite")

            hunter = object.__new__(DistroHunter)
            hunter.settings = Settings(
                config_path=root / "config.json",
                state_file=root / "state.json",
                plugins=PluginSettings(builtin=[], directories=[]),
                download=DownloadSettings(download_dir=download_dir, aria2_path=None, prefer_aria2=False),
                ventoy=VentoySettings(
                    enabled=True,
                    manual_sources=[
                        ManualSourceRule(
                            pattern="bazzite-*.iso",
                            family="bazzite",
                            edition_type="deck",
                        )
                    ],
                ),
                generator=GeneratorSettings(output_dir=root / "generated"),
                logging=LoggingSettings(run_log_file=None, mirror_failures_file=None, jsonl_log_file=None),
            )
            hunter.plugin_map = {
                "ubuntu_server_lts": PluginSpec(
                    slug="ubuntu_server_lts",
                    name="Ubuntu Server LTS",
                    module=object(),
                    metadata=metadata_from_fields(family="ubuntu", edition_type="server", source_kind="html"),
                )
            }
            hunter.state = type(
                "State",
                (),
                {
                    "data": {
                        "plugins": {
                            "ubuntu_server_lts": {
                                "download": {
                                    "path": "ubuntu.iso",
                                }
                            }
                        }
                    }
                },
            )()

            routes = DistroHunter._build_ventoy_route_map(hunter)

            self.assertEqual(routes[tracked.resolve()], Path("ubuntu/server"))
            self.assertEqual(routes[manual.resolve()], Path("bazzite/deck"))
