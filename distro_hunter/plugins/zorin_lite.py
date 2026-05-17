from __future__ import annotations

from distro_hunter.plugins.common import discover_exact_filename_candidates


NAME = "Zorin OS Lite"
PAGE_URL = "https://help.zorin.com/docs/getting-started/getting-zorin-os-lite/"
FILENAME = "Zorin-OS-17.3-Lite-64-bit-r2.iso"
PREFERRED_HOSTS = ("mirrors.edge.kernel.org", "mirror.clarkson.edu", "zorinos.mirror-services.net")


def discover(context):
    return discover_exact_filename_candidates(
        context,
        page_url=PAGE_URL,
        filename=FILENAME,
        version="17.3-r2",
        arch="amd64",
        priority=4,
        preferred_hosts=PREFERRED_HOSTS,
        max_candidates=3,
    )
