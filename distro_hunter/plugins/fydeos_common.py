from __future__ import annotations

import re
from urllib.parse import urlparse

from distro_hunter.models import Candidate


OFFICIAL_DOWNLOAD_HOST = "download.fydeos.io"
FYDEOS_DOWNLOAD_RE = re.compile(
    r"(?i)https://download\.fydeos\.io/.+\.(?:bin\.zip|img\.xz|ova)$"
)
FYDEOS_VERSION_RE = re.compile(r"(?i)[_-]v([^/_]+?)-io\.(?:bin\.zip|img\.xz|ova)$")
FYDEOS_SHA_RE_TEMPLATE = r"SHA-256\s*\({filename}\).*?<code[^>]*>([a-f0-9]{{64}})</code>"


def _extract_version(filename: str) -> str | None:
    match = FYDEOS_VERSION_RE.search(filename)
    if not match:
        return None
    return match.group(1)


def discover_fydeos_variant(
    context,
    *,
    page_url: str,
    arch: str,
    priority: int,
    notes: str | None = None,
) -> list[Candidate]:
    page_text = context.fetch_text(page_url)
    candidates: list[Candidate] = []
    seen: set[str] = set()

    for link in context.fetch_links(page_url):
        if link in seen or not FYDEOS_DOWNLOAD_RE.search(link):
            continue
        host = (urlparse(link).hostname or "").lower()
        if host != OFFICIAL_DOWNLOAD_HOST:
            continue
        seen.add(link)
        filename = link.rsplit("/", 1)[-1]
        checksum_match = re.search(
            FYDEOS_SHA_RE_TEMPLATE.format(filename=re.escape(filename)),
            page_text,
            re.IGNORECASE | re.DOTALL,
        )
        metadata = {
            "checksum_url": page_url,
        }
        if checksum_match:
            metadata.update(
                {
                    "checksum_algorithm": "sha256",
                    "checksum_expected": checksum_match.group(1).lower(),
                    "checksum_source": page_url,
                }
            )
        candidates.append(
            Candidate(
                url=link,
                filename=filename,
                version=_extract_version(filename),
                arch=arch,
                source_page=page_url,
                notes=notes,
                priority=priority,
                metadata=metadata,
            )
        )
    return candidates
