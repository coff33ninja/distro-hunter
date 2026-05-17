import unittest

from distro_hunter.plugins.common import (
    build_regex_discover,
    build_static_candidate_discover,
    build_ubuntu_thank_you_discover,
    discover_exact_filename_candidates,
)
from distro_hunter.plugins.fydeos_common import discover_fydeos_variant


class StubContext:
    def __init__(self, links: list[str]) -> None:
        self._links = links

    def fetch_links(self, url: str) -> list[str]:
        return list(self._links)

    def normalize_url(self, base_url: str, link: str) -> str:
        return base_url.rstrip("/") + "/" + link.lstrip("/")


class StubPageContext:
    def __init__(self, pages: dict[str, list[str]]) -> None:
        self.pages = pages

    def fetch_links(self, url: str) -> list[str]:
        return list(self.pages.get(url, []))

    def normalize_url(self, base_url: str, link: str) -> str:
        return base_url.rstrip("/") + "/" + link.lstrip("/")


class StubFydeContext:
    def __init__(self, page_url: str, text: str, links: list[str]) -> None:
        self.page_url = page_url
        self.text = text
        self.links = links

    def fetch_text(self, url: str) -> str:
        self_url = self.page_url
        if url != self_url:
            raise AssertionError(f"unexpected text fetch: {url}")
        return self.text

    def fetch_links(self, url: str) -> list[str]:
        self_url = self.page_url
        if url != self_url:
            raise AssertionError(f"unexpected link fetch: {url}")
        return list(self.links)


class CommonPluginTests(unittest.TestCase):
    def test_exact_filename_candidates_prefers_hosts(self) -> None:
        candidates = discover_exact_filename_candidates(
            StubContext(
                [
                    "https://other.example/linuxmint-22.3-cinnamon-64bit.iso",
                    "https://mirrors.kernel.org/linuxmint/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso",
                    "https://pub.linuxmint.io/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso",
                ]
            ),
            page_url="https://linuxmint.com/edition.php?id=326",
            filename="linuxmint-22.3-cinnamon-64bit.iso",
            version="22.3",
            arch="amd64",
            priority=5,
            preferred_hosts=("pub.linuxmint.io", "mirrors.kernel.org"),
            max_candidates=3,
        )

        self.assertEqual(candidates[0].url, "https://pub.linuxmint.io/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso")
        self.assertEqual(candidates[1].url, "https://mirrors.kernel.org/linuxmint/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso")

    def test_exact_filename_candidates_limits_and_filters(self) -> None:
        candidates = discover_exact_filename_candidates(
            StubContext(
                [
                    "ftp://pub.linuxmint.io/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso",
                    "https://pub.linuxmint.io/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso",
                    "https://mirrors.kernel.org/linuxmint/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso",
                    "https://pub.linuxmint.io/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso.sig",
                ]
            ),
            page_url="https://linuxmint.com/edition.php?id=326",
            filename="linuxmint-22.3-cinnamon-64bit.iso",
            version="22.3",
            arch="amd64",
            priority=5,
            preferred_hosts=("pub.linuxmint.io", "mirrors.kernel.org"),
            max_candidates=1,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://pub.linuxmint.io/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso")

    def test_build_regex_discover_wraps_common_candidate_logic(self) -> None:
        discover = build_regex_discover(
            page_url="https://example.org/releases/",
            regex=r"example-([\d.]+)-x86_64\.iso$",
            priority=5,
            arch="x86_64",
            torrent_suffix=".torrent",
        )

        candidates = discover(
            StubContext(
                [
                    "https://example.org/releases/example-1.2.3-x86_64.iso",
                    "https://example.org/releases/example-1.2.3-x86_64.iso.torrent",
                ]
            )
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].version, "1.2.3")
        self.assertEqual(candidates[0].torrent_url, "https://example.org/releases/example-1.2.3-x86_64.iso.torrent")

    def test_build_static_candidate_discover_returns_fixed_candidate(self) -> None:
        discover = build_static_candidate_discover(
            page_url="https://download.example.org/current/",
            filename="example-current.iso",
            version="current",
            arch="x86_64",
            priority=4,
        )

        candidates = discover(StubContext([]))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://download.example.org/current/example-current.iso")
        self.assertEqual(candidates[0].source_page, "https://download.example.org/current/")

    def test_build_ubuntu_thank_you_discover_filters_lts_and_builds_torrents(self) -> None:
        thank_you_lts = "https://ubuntu.com/download/server/thank-you?version=24.04.4&architecture=amd64&lts=true"
        thank_you_latest = "https://ubuntu.com/download/server/thank-you?version=25.10&architecture=amd64"
        discover = build_ubuntu_thank_you_discover(
            page_url="https://ubuntu.com/download/server",
            thank_you_regex=r"thank-you\?version=([\d.]+).*?architecture=amd64",
            iso_regex=r"ubuntu-([\d.]+)-live-server-amd64\.iso$",
            arch="amd64",
            priority=6,
            include_lts=False,
            torrent_suffix=".torrent",
        )

        candidates = discover(
            StubPageContext(
                {
                    "https://ubuntu.com/download/server": [thank_you_lts, thank_you_latest],
                    thank_you_lts: ["https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-live-server-amd64.iso"],
                    thank_you_latest: ["https://releases.ubuntu.com/25.10/ubuntu-25.10-live-server-amd64.iso"],
                }
            )
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].version, "25.10")
        self.assertEqual(candidates[0].torrent_url, "https://releases.ubuntu.com/25.10/ubuntu-25.10-live-server-amd64.iso.torrent")

    def test_discover_fydeos_variant_prefers_official_link_and_extracts_checksum_metadata(self) -> None:
        page_url = "https://fydeos.io/download/pc/intel-iris/"
        filename = "FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip"
        html = (
            '<a href="https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip">Official</a>'
            '<a href="https://drive.google.com/file/d/example/view">Mirror</a>'
            '<h3>SHA-256 (FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip)</h3>'
            '<code id="hash">c69b8129113cecef93df276378eb9d06908207eb76f62f5910cc4a7431eeafb9</code>'
        )

        candidates = discover_fydeos_variant(
            StubFydeContext(
                page_url,
                html,
                [
                    "https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip",
                    "https://drive.google.com/file/d/example/view",
                ],
            ),
            page_url=page_url,
            arch="x86_64",
            priority=5,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].filename, filename)
        self.assertEqual(candidates[0].version, "22.0-SP1")
        self.assertEqual(candidates[0].metadata["checksum_algorithm"], "sha256")
        self.assertEqual(
            candidates[0].metadata["checksum_expected"],
            "c69b8129113cecef93df276378eb9d06908207eb76f62f5910cc4a7431eeafb9",
        )
