from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "NixOS Graphical"
PAGE_URL = "https://nixos.org/download/"
ISO_RE = re.compile(
    r"https://channels\.nixos\.org/nixos-(\d+\.\d+)/latest-nixos-graphical-x86_64-linux\.iso$",
    re.IGNORECASE,
)


def discover(context) -> list[Candidate]:
    candidates: list[Candidate] = []
    for link in context.fetch_links(PAGE_URL):
        match = ISO_RE.search(link)
        if not match:
            continue
        candidates.append(
            Candidate(
                url=link,
                filename=link.rsplit("/", 1)[-1],
                version=match.group(1),
                arch="x86_64",
                source_page=PAGE_URL,
                priority=5,
            )
        )
    return candidates

