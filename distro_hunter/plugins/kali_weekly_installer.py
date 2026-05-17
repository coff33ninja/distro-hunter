from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "Kali Weekly Installer"
PAGE_URL = "https://www.kali.org/get-kali/"
REGEX = r"https://cdimage\.kali\.org/kali-weekly/kali-linux-(\d{4}-W\d+)-installer-amd64\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=4,
        arch="amd64",
        torrent_suffix=".torrent",
    )
