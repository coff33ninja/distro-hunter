from __future__ import annotations

import re

from distro_hunter.models import Candidate


NAME = "Linux Mint Edge (HWE)"
PAGE_URL = "https://mirrors.kernel.org/linuxmint/hwe/"
ISO_RE = re.compile(r"(linuxmint-(\d+\.\d+)-cinnamon-64bit-hwe-[\d.]+\.iso)", re.IGNORECASE)
PREFERRED_HOSTS = ("pub.linuxmint.io", "mirrors.kernel.org", "www.mirrorservice.org")


def discover(context):
    links = context.fetch_links(PAGE_URL)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for link in links:
        if not link.lower().startswith("http"):
            continue
        match = ISO_RE.search(link)
        if not match:
            continue
        filename = match.group(1)
        version = match.group(2) + "-hwe"
        if filename in seen:
            continue
        seen.add(filename)
        candidates.append(
            Candidate(
                url=link,
                filename=filename,
                version=version,
                arch="amd64",
                source_page=PAGE_URL,
                priority=4,
            )
        )
    return candidates
