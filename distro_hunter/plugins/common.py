from __future__ import annotations

import re
from urllib.parse import urlparse

from distro_hunter.models import Candidate


def discover_regex_candidates(
    context,
    *,
    page_url: str,
    regex: str,
    priority: int,
    arch: str,
    torrent_suffix: str | None = None,
    version_builder=None,
    notes: str | None = None,
    require_https: bool = False,
) -> list[Candidate]:
    compiled = re.compile(regex, re.IGNORECASE)
    links = context.fetch_links(page_url)
    link_set = set(links)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for link in links:
        if require_https and not link.lower().startswith("https://"):
            continue
        match = compiled.search(link)
        if not match or link in seen:
            continue
        seen.add(link)
        version = version_builder(match, link) if version_builder else (match.group(1) if match.groups() else None)
        torrent_url = None
        if torrent_suffix:
            candidate_torrent = link + torrent_suffix
            if candidate_torrent in link_set:
                torrent_url = candidate_torrent
        candidates.append(
            Candidate(
                url=link,
                filename=link.rsplit("/", 1)[-1],
                version=version,
                arch=arch,
                source_page=page_url,
                torrent_url=torrent_url,
                notes=notes,
                priority=priority,
            )
        )
    return candidates


def discover_exact_filename_candidates(
    context,
    *,
    page_url: str,
    filename: str,
    version: str | None,
    arch: str,
    priority: int,
    preferred_hosts: tuple[str, ...] = (),
    torrent_url: str | None = None,
    notes: str | None = None,
    max_candidates: int = 5,
) -> list[Candidate]:
    target = filename.lower()
    links = [
        link
        for link in context.fetch_links(page_url)
        if link.lower().startswith("http") and link.lower().endswith(target)
    ]

    def host_rank(link: str) -> tuple[int, str]:
        host = urlparse(link).netloc.lower()
        for index, preferred in enumerate(preferred_hosts):
            preferred_host = preferred.lower()
            if host == preferred_host or host.endswith(f".{preferred_host}"):
                return index, link
        return len(preferred_hosts), link

    candidates: list[Candidate] = []
    for link in sorted(dict.fromkeys(links), key=host_rank)[:max_candidates]:
        candidates.append(
            Candidate(
                url=link,
                filename=filename,
                version=version,
                arch=arch,
                source_page=page_url,
                torrent_url=torrent_url,
                notes=notes,
                priority=priority,
            )
        )
    return candidates


def build_regex_discover(
    *,
    page_url: str,
    regex: str,
    priority: int,
    arch: str,
    torrent_suffix: str | None = None,
    version_builder=None,
    notes: str | None = None,
    require_https: bool = False,
):
    def discover(context):
        return discover_regex_candidates(
            context,
            page_url=page_url,
            regex=regex,
            priority=priority,
            arch=arch,
            torrent_suffix=torrent_suffix,
            version_builder=version_builder,
            notes=notes,
            require_https=require_https,
        )

    discover.__name__ = "discover"
    return discover


def build_static_candidate_discover(
    *,
    page_url: str,
    filename: str,
    version: str | None,
    arch: str,
    priority: int,
    torrent_suffix: str | None = None,
    notes: str | None = None,
):
    def discover(context):
        url = context.normalize_url(page_url, filename)
        torrent_url = context.normalize_url(page_url, filename + torrent_suffix) if torrent_suffix else None
        return [
            Candidate(
                url=url,
                filename=filename,
                version=version,
                arch=arch,
                source_page=page_url,
                torrent_url=torrent_url,
                notes=notes,
                priority=priority,
            )
        ]

    discover.__name__ = "discover"
    return discover


def build_ubuntu_thank_you_discover(
    *,
    page_url: str,
    thank_you_regex: str,
    iso_regex: str,
    arch: str,
    priority: int,
    include_lts: bool | None = None,
    torrent_suffix: str | None = None,
    priority_builder=None,
):
    thank_you_re = re.compile(thank_you_regex, re.IGNORECASE)
    iso_re = re.compile(iso_regex, re.IGNORECASE)

    def discover(context) -> list[Candidate]:
        candidates: list[Candidate] = []
        for thank_you in context.fetch_links(page_url):
            lowered = thank_you.lower()
            if include_lts is True and "lts=true" not in lowered:
                continue
            if include_lts is False and "lts=true" in lowered:
                continue
            match = thank_you_re.search(thank_you)
            if not match:
                continue
            version = match.group(1) if match.groups() else None
            candidate_priority = (
                priority_builder(thank_you, version, priority) if priority_builder else priority
            )
            for link in context.fetch_links(thank_you):
                if not iso_re.search(link):
                    continue
                candidates.append(
                    Candidate(
                        url=link,
                        filename=link.rsplit("/", 1)[-1],
                        version=version,
                        arch=arch,
                        source_page=thank_you,
                        torrent_url=link + torrent_suffix if torrent_suffix else None,
                        priority=candidate_priority,
                    )
                )
        return candidates

    discover.__name__ = "discover"
    return discover
