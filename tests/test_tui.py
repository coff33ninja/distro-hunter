import types
import unittest

from distro_hunter.plugin_loader import PluginSpec
from distro_hunter.tui import build_plugin_options, filter_plugins, ordered_selected_plugin_slugs, plugin_filter_summary


def make_plugin(slug: str, name: str, **module_attrs: object) -> PluginSpec:
    attrs = {"discover": lambda context: []}
    attrs.update(module_attrs)
    return PluginSpec(slug=slug, name=name, module=types.SimpleNamespace(**attrs))


class TuiHelperTests(unittest.TestCase):
    def test_filter_plugins_matches_name_and_slug_terms(self) -> None:
        plugins = [
            make_plugin("ubuntu_lts", "Ubuntu Desktop LTS"),
            make_plugin("ubuntu_server_lts", "Ubuntu Server LTS"),
            make_plugin("fedora_workstation", "Fedora Workstation"),
        ]

        ubuntu = filter_plugins(plugins, "ubuntu")
        server_lts = filter_plugins(plugins, "server lts")

        self.assertEqual([plugin.slug for plugin in ubuntu], ["ubuntu_lts", "ubuntu_server_lts"])
        self.assertEqual([plugin.slug for plugin in server_lts], ["ubuntu_server_lts"])

    def test_filter_plugins_can_match_metadata_terms(self) -> None:
        plugins = [
            make_plugin("pop_os_arm_nvidia", "Pop!_OS ARM NVIDIA", API_URL="https://api.pop-os.org/builds"),
            make_plugin("ubuntu_server_lts", "Ubuntu Server LTS", PAGE_URL="https://ubuntu.com/download/server"),
        ]

        api = filter_plugins(plugins, "api")
        arm64 = filter_plugins(plugins, "arm64")

        self.assertEqual([plugin.slug for plugin in api], ["pop_os_arm_nvidia"])
        self.assertEqual([plugin.slug for plugin in arm64], ["pop_os_arm_nvidia"])

    def test_build_plugin_options_marks_selected_entries(self) -> None:
        plugins = [
            make_plugin("ubuntu_lts", "Ubuntu Desktop LTS"),
            make_plugin("fedora_workstation", "Fedora Workstation"),
        ]

        options = build_plugin_options(plugins, {"fedora_workstation"})

        self.assertEqual(
            options,
            [
                ("Ubuntu Desktop LTS [ubuntu_lts]", "ubuntu_lts", False),
                ("Fedora Workstation [fedora_workstation]", "fedora_workstation", True),
            ],
        )

    def test_ordered_selected_plugin_slugs_preserves_catalog_order(self) -> None:
        plugins = [
            make_plugin("ubuntu_lts", "Ubuntu Desktop LTS"),
            make_plugin("fedora_workstation", "Fedora Workstation"),
            make_plugin("steamos_recovery", "SteamOS Recovery"),
        ]

        selected = ordered_selected_plugin_slugs(plugins, {"steamos_recovery", "ubuntu_lts"})

        self.assertEqual(selected, ["ubuntu_lts", "steamos_recovery"])

    def test_plugin_filter_summary_reports_visible_and_selected_counts(self) -> None:
        self.assertEqual(
            plugin_filter_summary("ubuntu", total=87, visible=10, selected=14),
            'Filter "ubuntu": showing 10 of 87 plugins, selected 14 total',
        )
        self.assertEqual(
            plugin_filter_summary("", total=87, visible=87, selected=87),
            "Showing 87 of 87 plugins, selected 87 total",
        )


if __name__ == "__main__":
    unittest.main()
