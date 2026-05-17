from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "Debian Netinst"
PAGE_URL = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"
ISO_RE = re.compile(r"debian-(\d+(?:\.\d+)*)-amd64-netinst\.iso$", re.IGNORECASE)


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
                arch="amd64",
                source_page=PAGE_URL,
                priority=5,
            )
        )
    return candidates

