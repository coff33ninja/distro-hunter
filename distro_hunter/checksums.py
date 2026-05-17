from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from distro_hunter.exceptions import ChecksumMismatchError
from distro_hunter.models import Candidate, ChecksumResult, RemoteFileInfo
from distro_hunter.url_utils import extract_filename, strip_query_params, get_directory_url
from distro_hunter.utils import deduplicate


ALGORITHM_LENGTHS = {
    "sha512": 128,
    "sha256": 64,
}
SIGNATURE_SUFFIXES = (".asc", ".sig", ".gpg")
DIRECT_SUFFIXES = {
    "sha512": [".sha512"],
    "sha256": [".sha256", ".sha256sum", ".sha256.txt"],
}
DIRECTORY_FILES = {
    "sha512": ["SHA512SUMS", "SHA512SUMS.txt", "sha512sums.txt"],
    "sha256": ["SHA256SUMS", "SHA256SUMS.txt", "sha256sums.txt", "CHECKSUMS", "CHECKSUM"],
}


@dataclass(slots=True)
class ExpectedChecksum:
    algorithm: str
    digest: str
    source: str


def _preferred_algorithms_for_url(url: str) -> list[str]:
    lowered = url.lower()
    if "sha512" in lowered:
        return ["sha512"]
    if "sha256" in lowered:
        return ["sha256"]
    return ["sha512", "sha256"]


def _target_names(candidate: Candidate, remote: RemoteFileInfo | None) -> set[str]:
    names = {
        name
        for name in [
            candidate.filename,
            extract_filename(candidate.url),
            remote.filename if remote else None,
            extract_filename(remote.final_url) if remote else None,
            extract_filename(remote.url) if remote else None,
        ]
        if name
    }
    return names


def _parse_checksum_line(line: str, algorithm: str, target_names: set[str]) -> str | None:
    length = ALGORITHM_LENGTHS[algorithm]
    digest_match = re.fullmatch(rf"(?i)([a-f0-9]{{{length}}})", line)
    if digest_match:
        return digest_match.group(1).lower()

    pair_match = re.match(rf"(?i)^([a-f0-9]{{{length}}})\s+[* ]?(.+)$", line)
    if pair_match:
        name = Path(pair_match.group(2).strip()).name
        if name in target_names:
            return pair_match.group(1).lower()
        return None

    named_match = re.match(rf"(?i)^[A-Z0-9_-]+\s*\((.+?)\)\s*=\s*([a-f0-9]{{{length}}})$", line)
    if named_match:
        name = Path(named_match.group(1).strip()).name
        if name in target_names:
            return named_match.group(2).lower()
    return None


def _extract_checksum(text: str, algorithm: str, target_names: set[str]) -> str | None:
    digest_only: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        digest = _parse_checksum_line(line, algorithm, target_names)
        if digest is None:
            continue
        if re.fullmatch(rf"(?i)[a-f0-9]{{{ALGORITHM_LENGTHS[algorithm]}}}", line):
            digest_only.append(digest)
            continue
        return digest
    if len(digest_only) == 1:
        return digest_only[0]
    return None


def checksum_source_urls(web, candidate: Candidate, remote: RemoteFileInfo | None) -> list[str]:
    urls: list[str] = []

    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    for key in ("checksum_url", "checksum_urls"):
        value = metadata.get(key)
        if isinstance(value, str):
            urls.append(value)
        elif isinstance(value, list):
            urls.extend(str(entry) for entry in value)

    if candidate.source_page:
        try:
            page_links = web.fetch_links(candidate.source_page)
        except Exception:
            page_links = []
        for link in page_links:
            lowered = link.lower()
            if any(lowered.endswith(suffix) for suffix in SIGNATURE_SUFFIXES):
                continue
            if any(term in lowered for term in ("sha256", "sha512", "checksum")):
                urls.append(link)

    for base_url in deduplicate([url for url in [candidate.url, remote.final_url if remote else None] if url]):
        stripped = strip_query_params(base_url)
        for algorithm in ("sha512", "sha256"):
            for suffix in DIRECT_SUFFIXES[algorithm]:
                urls.append(stripped + suffix)
        directory = get_directory_url(base_url)
        if directory:
            for algorithm in ("sha512", "sha256"):
                for filename in DIRECTORY_FILES[algorithm]:
                    urls.append(directory + filename)
    return deduplicate(urls)


def resolve_expected_checksum(web, candidate: Candidate, remote: RemoteFileInfo | None) -> ExpectedChecksum | None:
    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    direct_digest = metadata.get("checksum_expected") or metadata.get("expected_checksum")
    direct_algorithm = metadata.get("checksum_algorithm") or metadata.get("expected_checksum_algorithm")
    if isinstance(direct_digest, str) and isinstance(direct_algorithm, str):
        normalized_digest = direct_digest.strip().lower()
        normalized_algorithm = direct_algorithm.strip().lower()
        expected_length = ALGORITHM_LENGTHS.get(normalized_algorithm)
        if expected_length and re.fullmatch(rf"[a-f0-9]{{{expected_length}}}", normalized_digest):
            direct_source = metadata.get("checksum_source") or metadata.get("checksum_url") or candidate.source_page or candidate.url
            return ExpectedChecksum(
                algorithm=normalized_algorithm,
                digest=normalized_digest,
                source=str(direct_source),
            )

    target_names = _target_names(candidate, remote)
    if not target_names:
        return None

    for url in checksum_source_urls(web, candidate, remote):
        try:
            text = web.fetch_text(url)
        except Exception:
            continue
        for algorithm in _preferred_algorithms_for_url(url):
            digest = _extract_checksum(text, algorithm, target_names)
            if digest:
                return ExpectedChecksum(algorithm=algorithm, digest=digest, source=url)
    return None


def verify_file_checksum(path: Path, expected: ExpectedChecksum) -> ChecksumResult:
    digest = hashlib.new(expected.algorithm)
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.digest.lower():
        raise ChecksumMismatchError(
            f"checksum mismatch ({expected.algorithm}): expected {expected.digest.lower()} got {actual.lower()}"
        )
    return ChecksumResult(
        status="verified",
        algorithm=expected.algorithm,
        expected=expected.digest.lower(),
        actual=actual.lower(),
        source=expected.source,
    )
