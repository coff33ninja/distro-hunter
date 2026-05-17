from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "AlmaLinux GNOME Live"
PAGE_URL = "https://repo.almalinux.org/almalinux/10/live/x86_64/"
ISO_RE = re.compile(r"AlmaLinux-10-latest-x86_64-Live-GNOME\.iso$", re.IGNORECASE)


def discover(context) -> list[Candidate]:
    candidates: list[Candidate] = []
    for link in context.fetch_links(PAGE_URL):
        if not ISO_RE.search(link):
            continue
        candidates.append(
            Candidate(
                url=link,
                filename=link.rsplit("/", 1)[-1],
                version="10-latest",
                arch="x86_64",
                source_page=PAGE_URL,
                priority=5,
            )
        )
    return candidates

