import tempfile
import unittest
from pathlib import Path

from distro_hunter.config import DownloadSettings, GeneratorSettings, LoggingSettings, PluginSettings, Settings, VentoySettings
from distro_hunter.startup_checks import collect_startup_warnings


class StartupChecksTests(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            config_path=root / "config.json",
            state_file=root / "state.json",
            plugins=PluginSettings(builtin=[], directories=[]),
            download=DownloadSettings(
                download_dir=root / "downloads",
                aria2_path=None,
                prefer_aria2=True,
                prefer_torrent=False,
            ),
            ventoy=VentoySettings(enabled=True),
            generator=GeneratorSettings(output_dir=root / "generated"),
            logging=LoggingSettings(run_log_file=None, mirror_failures_file=None, jsonl_log_file=None),
        )

    def test_collect_startup_warnings_reports_missing_aria2_and_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(Path(temp_dir))

            warnings = collect_startup_warnings(settings, plugin_count=0)

            self.assertTrue(any("prefer_aria2" in warning for warning in warnings))
            self.assertTrue(any("No plugins" in warning for warning in warnings))

    def test_collect_startup_warnings_reports_torrent_and_ventoy_misconfiguration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(Path(temp_dir))
            settings.download.prefer_torrent = True
            settings.ventoy.volume_labels = []
            settings.ventoy.marker_paths = []

            warnings = collect_startup_warnings(settings, plugin_count=5)

            self.assertTrue(any("torrent" in warning.lower() for warning in warnings))
            self.assertTrue(any("Ventoy detection" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
