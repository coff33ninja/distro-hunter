import unittest

from distro_hunter.plugins import systemrescue
from distro_hunter.scoring import choose_best


class StubContext:
    def __init__(self, links: list[str]) -> None:
        self.links = links

    def fetch_links(self, url: str) -> list[str]:
        return list(self.links)


class SystemRescuePluginTests(unittest.TestCase):
    def test_discover_returns_fastly_and_sourceforge_candidates(self) -> None:
        context = StubContext(
            [
                "https://sourceforge.net/projects/systemrescuecd/files/sysresccd-x86/13.00/systemrescue-13.00-amd64.iso/download",
                "https://fastly-cdn.system-rescue.org/releases/13.00/systemrescue-13.00-amd64.iso",
                "https://www.system-rescue.org/releases/13.00/systemrescue-13.00-amd64.iso.sha256",
            ]
        )

        candidates = systemrescue.discover(context)

        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.filename == "systemrescue-13.00-amd64.iso" for candidate in candidates))
        self.assertTrue(all(candidate.version == "13.00" for candidate in candidates))
        self.assertEqual(choose_best(candidates).url, "https://fastly-cdn.system-rescue.org/releases/13.00/systemrescue-13.00-amd64.iso")


if __name__ == "__main__":
    unittest.main()
