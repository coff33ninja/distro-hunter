from __future__ import annotations

from distro_hunter.plugins.common import discover_exact_filename_candidates


NAME = "Zorin OS Education"
PAGE_URL = "https://zorin.com/os/download/18/education/"
FILENAME = "Zorin-OS-18-Education-64-bit-r3.iso"
PREFERRED_HOSTS = ("mirrors.edge.kernel.org", "mirror.clarkson.edu", "zorinos.mirror-services.net")


def discover(context):
    return discover_exact_filename_candidates(
        context,
        page_url=PAGE_URL,
        filename=FILENAME,
        version="18-r3",
        arch="amd64",
        priority=5,
        preferred_hosts=PREFERRED_HOSTS,
        max_candidates=3,
    )
