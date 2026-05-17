from __future__ import annotations

from distro_hunter.plugins.common import build_static_candidate_discover


NAME = "openSUSE Tumbleweed Rescue"
PAGE_URL = "https://download.opensuse.org/tumbleweed/iso/"
FILENAME = "openSUSE-Tumbleweed-Rescue-CD-x86_64-Current.iso"


discover = build_static_candidate_discover(
    page_url=PAGE_URL,
    filename=FILENAME,
    version="current",
    arch="x86_64",
    priority=4,
)
