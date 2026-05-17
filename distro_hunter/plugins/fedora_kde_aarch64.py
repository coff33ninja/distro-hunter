from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora KDE Plasma ARM64"
PAGE_URL = "https://fedoraproject.org/en/kde/download/"
REGEX = r"Fedora-KDE-Desktop-Live-([\d.-]+)\.aarch64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=4,
    arch="aarch64",
)
