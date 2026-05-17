from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "Manjaro KDE"
PAGE_URL = "https://manjaro.org/products/download/x86"
REGEX = r"manjaro-kde-([\d.]+-\d+)-linux\d+\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=5,
        arch="x86_64",
    )

