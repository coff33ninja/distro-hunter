from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "Debian Live Debian Junior"
PAGE_URL = "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/"
REGEX = r"https://cdimage\.debian\.org/debian-cd/current-live/amd64/iso-hybrid/debian-live-(\d+(?:\.\d+)*)-amd64-debian-junior\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=4,
        arch="amd64",
    )
