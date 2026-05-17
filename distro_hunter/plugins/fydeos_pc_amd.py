from __future__ import annotations

from distro_hunter.plugins.fydeos_common import discover_fydeos_variant


NAME = "FydeOS for PC (AMD Graphics)"
PAGE_URL = "https://fydeos.io/download/pc/apu/"
EDITION_TYPE = "amd"


def discover(context):
    return discover_fydeos_variant(
        context,
        page_url=PAGE_URL,
        arch="x86_64",
        priority=5,
        notes="Downloads the official FydeOS raw disk archive; Distro Hunter extracts the .bin.zip payload to a Ventoy-friendly .img",
    )
