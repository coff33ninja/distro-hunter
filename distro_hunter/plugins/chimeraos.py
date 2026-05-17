from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "ChimeraOS"
PAGE_URL = "https://chimeraos.org/download"
REGEX = r"chimeraos-(\d{4}\.\d{2}\.\d{2})-x86_64\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=6,
        arch="x86_64",
    )

