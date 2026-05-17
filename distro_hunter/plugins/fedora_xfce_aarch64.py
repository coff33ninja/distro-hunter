from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora Xfce ARM64"
PAGE_URL = "https://fedoraproject.org/en/spins/xfce/download/"
REGEX = r"Fedora-Xfce-Live-([\d.-]+)\.aarch64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=4,
    arch="aarch64",
)
