from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "Kali Installer"
PAGE_URL = "https://www.kali.org/get-kali/"
ISO_RE = re.compile(
    r"https://cdimage\.kali\.org/kali-(\d+\.\d+)/kali-linux-\d+\.\d+-installer-amd64\.iso$",
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
                arch="amd64",
                source_page=PAGE_URL,
                torrent_url=link + ".torrent",
                priority=5,
            )
        )
    return candidates

