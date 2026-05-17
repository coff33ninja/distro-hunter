import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from distro_hunter.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_load_settings_expands_profiles_and_parses_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "profiles": ["minimal", "gaming"],
                            "directories": [],
                            "overrides": {
                                "ubuntu_lts": {
                                    "disabled_hosts": ["mirror.example.org"],
                                    "include": ["iso"],
                                    "exclude": ["beta"],
                                    "forced_urls": ["https://downloads.example.org/custom.iso"],
                                    "priority_boost": 7,
                                }
                            },
                        },
                        "download": {
                            "discovery_workers": 3,
                        },
                        "ventoy": {
                            "enabled": False,
                            "manual_sources": [
                                {
                                    "pattern": "bazzite-*.iso",
                                    "family": "bazzite",
                                    "edition_type": "desktop",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(config_path)

            self.assertIn("archlinux", settings.plugins.builtin)
            self.assertIn("chimeraos", settings.plugins.builtin)
            self.assertNotIn("fedora_workstation", settings.plugins.builtin)
            override = settings.plugins.overrides["ubuntu_lts"]
            self.assertEqual(override.disabled_hosts, ["mirror.example.org"])
            self.assertEqual(override.include, ["iso"])
            self.assertEqual(override.exclude, ["beta"])
            self.assertEqual(override.forced_urls, ["https://downloads.example.org/custom.iso"])
            self.assertEqual(override.priority_boost, 7)
            self.assertEqual(settings.download.discovery_workers, 3)
            self.assertEqual(len(settings.ventoy.manual_sources), 1)
            self.assertEqual(settings.ventoy.manual_sources[0].pattern, "bazzite-*.iso")
            self.assertEqual(settings.ventoy.manual_sources[0].family, "bazzite")
            self.assertEqual(settings.ventoy.manual_sources[0].edition_type, "desktop")
            self.assertEqual(settings.ventoy.manual_sources[0].source_kind, "manual")

    def test_load_settings_rejects_unknown_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "profiles": ["definitely_not_real"],
                            "directories": [],
                        },
                        "ventoy": {"enabled": False},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_settings(config_path)

    def test_load_settings_discovers_aria2_from_path_when_configured_location_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            discovered = root / "bin" / "aria2c.exe"
            discovered.parent.mkdir(parents=True)
            discovered.write_bytes(b"")
            config_path.write_text(
                json.dumps(
                    {
                        "download": {
                            "aria2_path": "C:/missing/aria2c.exe",
                        },
                        "ventoy": {"enabled": False},
                    }
                ),
                encoding="utf-8",
            )

            with patch("distro_hunter.config.shutil.which", return_value=str(discovered)):
                settings = load_settings(config_path)

            self.assertEqual(settings.download.aria2_path, discovered.resolve())

    def test_load_settings_discovers_repo_local_aria2_when_configured_location_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            repo_local = root / "tools" / "aria2" / "aria2c.exe"
            repo_local.parent.mkdir(parents=True)
            repo_local.write_bytes(b"")
            config_path.write_text(
                json.dumps(
                    {
                        "download": {
                            "aria2_path": "C:/missing/aria2c.exe",
                        },
                        "ventoy": {"enabled": False},
                    }
                ),
                encoding="utf-8",
            )

            with patch("distro_hunter.config.shutil.which", return_value=None):
                settings = load_settings(config_path)

            self.assertEqual(settings.download.aria2_path, repo_local.resolve())


if __name__ == "__main__":
    unittest.main()
