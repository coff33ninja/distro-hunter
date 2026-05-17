from __future__ import annotations

import re
from collections.abc import Iterable

from distro_hunter.models import Candidate


GOOD_KEYWORDS = {
    "iso": 4,
    "amd64": 5,
    "x86_64": 5,
    "desktop": 3,
    "workstation": 3,
    "live": 2,
    "lts": 2,
    "netinst": 2,
}

BAD_KEYWORDS = {
    "torrent": -6,
    ".sig": -8,
    "sha256": -8,
    "sha512": -8,
    "arm64": -6,
    "aarch64": -6,
    "ppc": -6,
    "s390": -6,
    "beta": -4,
    "rc": -4,
    "raw.xz": -6,
    "raw": -3,
}


def version_key(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", value))


def score_candidate(candidate: Candidate) -> int:
    text = " ".join(
        part
        for part in [
            candidate.url,
            candidate.filename or "",
            candidate.version or "",
            candidate.arch or "",
            candidate.notes or "",
        ]
        if part
    ).lower()

    score = candidate.priority
    for key, weight in GOOD_KEYWORDS.items():
        if key in text:
            score += weight
    for key, weight in BAD_KEYWORDS.items():
        if key in text:
            score += weight

    if candidate.url.lower().endswith(".iso"):
        score += 8
    if candidate.torrent_url or candidate.magnet_url:
        score += 1
    if re.search(r"\d{4}\.\d{2}(?:\.\d{2})?", text):
        score += 3
    if re.search(r"\d+\.\d+(?:\.\d+)?", text):
        score += 2
    return score


def rank_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            score_candidate(candidate),
            version_key(candidate.version or candidate.filename or candidate.url),
        ),
        reverse=True,
    )


def choose_best(candidates: Iterable[Candidate]) -> Candidate | None:
    ranked = rank_candidates(candidates)
    return ranked[0] if ranked else None

