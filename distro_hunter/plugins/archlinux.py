from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from distro_hunter.models import Candidate


NAME = "Arch Linux"
PAGE_URL = "https://archlinux.org/download/"
MIRROR_RE = re.compile(r"https?://[^\"']+/iso/\d{4}\.\d{2}\.\d{2}/", re.IGNORECASE)
ISO_RE = re.compile(r"(archlinux-\d{4}\.\d{2}\.\d{2}-x86_64\.iso)", re.IGNORECASE)
MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[^\"']+)", re.IGNORECASE)


def discover(context) -> list[Candidate]:
    text = context.fetch_text(PAGE_URL)
    raw_mirrors = MIRROR_RE.findall(text)
    iso_match = ISO_RE.search(text)
    if not raw_mirrors or not iso_match:
        return []

    filename = iso_match.group(1)
    version = re.search(r"(\d{4}\.\d{2}\.\d{2})", filename)
    magnet = MAGNET_RE.search(html.unescape(text))
    mirrors: list[str] = []
    seen: set[str] = set()
    for mirror in raw_mirrors:
        host = urlparse(mirror).netloc.lower()
        if host in {"archlinux.org", "www.archlinux.org"}:
            continue
        if mirror in seen:
            continue
        seen.add(mirror)
        mirrors.append(mirror)

    candidates: list[Candidate] = []
    for mirror in mirrors[:10]:
        candidates.append(
            Candidate(
                url=context.normalize_url(mirror, filename),
                filename=filename,
                version=version.group(1) if version else None,
                arch="x86_64",
                source_page=PAGE_URL,
                magnet_url=magnet.group(1) if magnet else None,
                priority=6,
            )
        )
    return candidates
