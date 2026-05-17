from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora i3 ARM64"
PAGE_URL = "https://fedoraproject.org/en/spins/i3/download/"
REGEX = r"Fedora-i3-Live-([\d.-]+)\.aarch64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=3,
    arch="aarch64",
)
