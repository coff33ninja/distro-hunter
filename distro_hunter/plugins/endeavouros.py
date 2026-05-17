from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "EndeavourOS"
PAGE_URL = "https://endeavouros.com/latest-release/"
REGEX = r"EndeavourOS_[A-Za-z]+-(\d{4}\.\d{2}\.\d{2})\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=6,
        arch="x86_64",
        torrent_suffix=".torrent",
        require_https=True,
    )

