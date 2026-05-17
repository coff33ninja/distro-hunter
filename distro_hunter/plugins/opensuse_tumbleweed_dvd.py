from __future__ import annotations

from distro_hunter.plugins.common import build_static_candidate_discover


NAME = "openSUSE Tumbleweed DVD"
PAGE_URL = "https://download.opensuse.org/tumbleweed/iso/"
FILENAME = "openSUSE-Tumbleweed-DVD-x86_64-Current.iso"


discover = build_static_candidate_discover(
    page_url=PAGE_URL,
    filename=FILENAME,
    version="current",
    arch="x86_64",
    priority=5,
)
