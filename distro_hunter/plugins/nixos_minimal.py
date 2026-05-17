from __future__ import annotations

from distro_hunter.plugins.common import discover_regex_candidates


NAME = "NixOS Minimal"
PAGE_URL = "https://nixos.org/download/"
REGEX = r"https://channels\.nixos\.org/nixos-(\d+\.\d+)/latest-nixos-minimal-x86_64-linux\.iso$"


def discover(context):
    return discover_regex_candidates(
        context,
        page_url=PAGE_URL,
        regex=REGEX,
        priority=5,
        arch="x86_64",
    )

