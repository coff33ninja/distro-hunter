import types
import unittest
from pathlib import Path

from distro_hunter.plugin_metadata import infer_plugin_metadata, metadata_from_fields, metadata_subdir


class PluginMetadataTests(unittest.TestCase):
    def test_infer_plugin_metadata_from_slug_and_module_hints(self) -> None:
        module = types.SimpleNamespace(API_URL="https://api.pop-os.org/builds/24.04/generic?arch=arm64")

        metadata = infer_plugin_metadata("pop_os_arm_nvidia", module)

        self.assertEqual(metadata.family, "pop-os")
        self.assertEqual(metadata.architecture, "arm64")
        self.assertEqual(metadata.edition_type, "nvidia")
        self.assertEqual(metadata.source_kind, "api")

    def test_metadata_subdir_uses_family_and_edition(self) -> None:
        metadata = metadata_from_fields(family="Ubuntu", edition_type="Server LTS", source_kind="html")

        self.assertEqual(metadata_subdir(metadata), Path("ubuntu/server-lts"))


if __name__ == "__main__":
    unittest.main()
