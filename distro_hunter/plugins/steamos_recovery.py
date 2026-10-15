from __future__ import annotations

from distro_hunter.models import Candidate


NAME = "SteamOS Recovery"
VENTOY_SUBDIR = "steamos/recovery"
PAGE_URL = "https://steamdeck-images.steamos.cloud/recovery/"
IMAGE_URL = "https://steamdeck-images.steamos.cloud/recovery/steamdeck-repair-latest.img.bz2"


def discover(context) -> list[Candidate]:
    return [
        Candidate(
            url=IMAGE_URL,
            filename="steamdeck-repair-latest.img.bz2",
            version="latest",
            arch="x86_64",
            source_page=PAGE_URL,
            notes="Compressed Steam Deck recovery image; Distro Hunter decompresses it to .img after download",
            priority=4,
        )
    ]
