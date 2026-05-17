from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora Budgie"
PAGE_URL = "https://fedoraproject.org/en/spins/budgie/download/"
REGEX = r"Fedora-Budgie-Live-([\d.-]+)\.x86_64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=5,
    arch="x86_64",
)
