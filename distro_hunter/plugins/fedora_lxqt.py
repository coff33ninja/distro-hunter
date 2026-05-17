from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Fedora LXQt"
PAGE_URL = "https://fedoraproject.org/en/spins/lxqt/download/"
REGEX = r"Fedora-LXQt-Live-([\d.-]+)\.x86_64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=4,
    arch="x86_64",
)
