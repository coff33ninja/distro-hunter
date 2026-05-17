from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "Rocky Linux Boot"
PAGE_URL = "https://download.rockylinux.org/pub/rocky/9/isos/x86_64/"
ISO_RE = re.compile(r"Rocky-9-latest-x86_64-boot\.iso$", re.IGNORECASE)


def discover(context) -> list[Candidate]:
    candidates: list[Candidate] = []
    for link in context.fetch_links(PAGE_URL):
        if not ISO_RE.search(link):
            continue
        candidates.append(
            Candidate(
                url=link,
                filename=link.rsplit("/", 1)[-1],
                version="9-latest",
                arch="x86_64",
                source_page=PAGE_URL,
                priority=5,
            )
        )
    return candidates
