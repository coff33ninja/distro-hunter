from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "Debian Live KDE"
PAGE_URL = "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/"
REGEX = r"https://cdimage\.debian\.org/debian-cd/current-live/amd64/iso-hybrid/debian-live-(\d+(?:\.\d+)*)-amd64-kde\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=5,
        arch="amd64",
    )
