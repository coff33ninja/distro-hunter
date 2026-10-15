from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora Cinnamon"
PAGE_URL = "https://fedoraproject.org/spins/cinnamon/download/"
REGEX = r"Fedora-Cinnamon-Live-([\d.-]+)\.x86_64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=5,
    arch="x86_64",
)
