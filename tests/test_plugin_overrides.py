import unittest

from distro_hunter.config import PluginOverrideSettings, PluginSettings
from distro_hunter.core import DistroHunter
from distro_hunter.models import Candidate
from distro_hunter.plugin_loader import PluginSpec


class FakeState:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.health_updates: list[dict] = []

    def get_plugin_record(self, plugin_slug: str) -> dict:
        return self.records.setdefault(plugin_slug, {})

    def remember_selection(self, plugin_slug: str, candidate: Candidate) -> None:
        self.get_plugin_record(plugin_slug)["selection"] = {"url": candidate.url}

    def remember_health(self, plugin_slug: str, *, status: str, healthy: bool, error: str | None = None) -> None:
        self.health_updates.append({"plugin_slug": plugin_slug, "status": status, "healthy": healthy, "error": error})

    def save(self) -> None:
        pass


class FakeJournal:
    def __init__(self) -> None:
        self.info_messages: list[str] = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def error(self, message: str) -> None:
        self.info_messages.append(message)


class PluginOverrideTests(unittest.TestCase):
    def test_discover_one_applies_forced_urls_filters_and_priority_boost(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.context = object()
        hunter.state = FakeState()
        hunter.journal = FakeJournal()
        hunter.plugin_map = {}
        hunter.settings = type(
            "Settings",
            (),
            {
                "plugins": PluginSettings(
                    builtin=[],
                    directories=[],
                    overrides={
                        "ubuntu_lts": PluginOverrideSettings(
                            disabled_hosts=["blocked.example.org"],
                            include=["iso"],
                            exclude=["beta"],
                            forced_urls=["https://forced.example.org/custom.iso"],
                            priority_boost=5,
                        )
                    },
                )
            },
        )()

        plugin = PluginSpec(
            slug="ubuntu_lts",
            name="Ubuntu LTS",
            module=type(
                "Module",
                (),
                {
                    "discover": staticmethod(
                        lambda context: [
                            Candidate(url="https://blocked.example.org/build.iso", filename="build.iso", priority=1),
                            Candidate(url="https://downloads.example.org/build-beta.iso", filename="build-beta.iso", priority=1),
                            Candidate(url="https://downloads.example.org/build.img", filename="build.img", priority=10),
                            Candidate(url="https://downloads.example.org/build.iso", filename="build.iso", priority=1),
                        ]
                    )
                },
            )(),
        )

        discovery = DistroHunter.discover_one(hunter, plugin)

        self.assertEqual(discovery.selected.url, "https://forced.example.org/custom.iso")
        self.assertEqual(
            [candidate.url for candidate in discovery.ranked],
            [
                "https://forced.example.org/custom.iso",
                "https://downloads.example.org/build.iso",
            ],
        )
        self.assertEqual(hunter.state.health_updates[0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
