from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora Sway"
PAGE_URL = "https://fedoraproject.org/spins/sway/download/"
REGEX = r"Fedora-Sway-Live-([\d.-]+)\.x86_64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=4,
    arch="x86_64",
)
