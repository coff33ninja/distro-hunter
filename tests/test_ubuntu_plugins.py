import unittest

from distro_hunter.plugins import ubuntu_server_latest


class StubContext:
    def __init__(self, pages: dict[str, list[str]]) -> None:
        self.pages = pages

    def fetch_links(self, url: str) -> list[str]:
        return list(self.pages.get(url, []))


class UbuntuPluginTests(unittest.TestCase):
    def test_ubuntu_server_latest_skips_lts_links(self) -> None:
        thank_you_lts = "https://ubuntu.com/download/server/thank-you?version=24.04.4&architecture=amd64&lts=true"
        thank_you_latest = "https://ubuntu.com/download/server/thank-you?version=25.10&architecture=amd64"
        context = StubContext(
            {
                ubuntu_server_latest.PAGE_URL: [thank_you_lts, thank_you_latest],
                thank_you_lts: [
                    "https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-live-server-amd64.iso",
                ],
                thank_you_latest: [
                    "https://releases.ubuntu.com/25.10/ubuntu-25.10-live-server-amd64.iso",
                ],
            }
        )

        candidates = ubuntu_server_latest.discover(context)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].version, "25.10")
        self.assertEqual(
            candidates[0].url,
            "https://releases.ubuntu.com/25.10/ubuntu-25.10-live-server-amd64.iso",
        )


if __name__ == "__main__":
    unittest.main()
