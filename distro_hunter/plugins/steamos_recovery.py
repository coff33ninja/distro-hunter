from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "SteamOS Recovery"
VENTOY_SUBDIR = "steamos/recovery"
PAGE_URL = "https://store.steampowered.com/steamos/download?ver=custom"
IMAGE_RE = re.compile(
    r"https://steamdeck-images\.steamos\.cloud/recovery/steamdeck-repair-latest\.img\.bz2$",
    re.IGNORECASE,
)


def discover(context) -> list[Candidate]:
    candidates: list[Candidate] = []
    for link in context.fetch_links(PAGE_URL):
        if not IMAGE_RE.search(link):
            continue
        candidates.append(
            Candidate(
                url=link,
                filename=link.rsplit("/", 1)[-1],
                version="latest",
                arch="x86_64",
                source_page=PAGE_URL,
                notes="Compressed Steam Deck recovery image; Distro Hunter decompresses it to .img after download",
                priority=4,
            )
        )
    return candidates
