from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "Nobara Steam HTPC"
PAGE_URL = "https://nobaraproject.org/download-nobara/"
REGEX = r"Nobara-(\d+)-Steam-HTPC-(\d{4}-\d{2}-\d{2})\.iso$"


def _version(match, link):
    return f"{match.group(1)}-{match.group(2)}"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=7,
        arch="x86_64",
        version_builder=_version,
        notes="gaming couch",
    )

