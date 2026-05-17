from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "Kali Netinst"
PAGE_URL = "https://www.kali.org/get-kali/"
REGEX = r"https://cdimage\.kali\.org/kali-(\d+\.\d+)/kali-linux-\d+\.\d+-installer-netinst-amd64\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=5,
        arch="amd64",
        torrent_suffix=".torrent",
    )
