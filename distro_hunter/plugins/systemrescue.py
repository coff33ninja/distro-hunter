from __future__ import annotations

import re
from urllib.parse import urlparse

from distro_hunter.models import Candidate


NAME = "SystemRescue"
PAGE_URL = "https://www.system-rescue.org/Download/"
ISO_RE = re.compile(r"systemrescue-(\d+(?:\.\d+)+)-amd64\.iso(?:/download)?(?:\?.*)?$", re.IGNORECASE)
HOST_PRIORITIES = {
    "fastly-cdn.system-rescue.org": 7,
    "sourceforge.net": 6,
}


def discover(context) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for link in context.fetch_links(PAGE_URL):
        match = ISO_RE.search(link)
        if not match or link in seen:
            continue
        seen.add(link)
        version = match.group(1)
        filename = f"systemrescue-{version}-amd64.iso"
        host = urlparse(link).hostname or ""
        candidates.append(
            Candidate(
                url=link,
                filename=filename,
                version=version,
                arch="amd64",
                source_page=PAGE_URL,
                notes="rescue",
                priority=HOST_PRIORITIES.get(host.lower(), 5),
            )
        )
    return candidates
