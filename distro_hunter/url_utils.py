"""Centralized URL handling utilities."""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit, urljoin as urllib_urljoin


HREF_RE = re.compile(r"""href=["']([^"'#]+)["']""", re.IGNORECASE)
URL_RE = re.compile(r"""https?://[^\s"'<>]+""", re.IGNORECASE)


def extract_filename(url: str) -> str | None:
    """Extract filename from URL path.

    Args:
        url: The URL to extract filename from

    Returns:
        The filename (HTML-unescaped) or None if path is empty
    """
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if not name:
        return None
    return html.unescape(name)


def strip_query_params(url: str) -> str:
    """Remove query parameters from URL, keeping scheme, netloc, and path.

    Args:
        url: The URL to strip

    Returns:
        URL without query string or fragment
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def get_directory_url(url: str) -> str | None:
    """Get the directory portion of a URL.

    Args:
        url: The URL to extract directory from

    Returns:
        Directory URL with trailing slash, or None if already at root

    Example:
        >>> get_directory_url("https://example.com/path/to/file.iso")
        "https://example.com/path/to/"
    """
    stripped = strip_query_params(url)
    if "/" not in stripped.rsplit("/", 1)[0]:
        return None
    return stripped.rsplit("/", 1)[0] + "/"


def normalize_link(base_url: str, link: str) -> str:
    """Normalize a relative or absolute link against a base URL.

    Handles:
    - HTML entities (e.g., &quot;)
    - Whitespace trimming
    - Relative URL resolution

    Args:
        base_url: The base URL for relative link resolution
        link: The link to normalize (relative or absolute)

    Returns:
        Normalized absolute URL
    """
    cleaned = html.unescape(link).strip()
    return urllib_urljoin(base_url, cleaned)


def extract_links_from_html(html_text: str, base_url: str) -> list[str]:
    """Extract all href links and bare URLs from HTML content.

    Finds both:
    - href attribute values
    - Bare URLs in text

    Automatically deduplicates results.

    Args:
        html_text: The HTML content to parse
        base_url: Base URL for resolving relative links

    Returns:
        List of normalized, deduplicated URLs
    """
    found: list[str] = []

    # Extract href attributes
    for raw in HREF_RE.findall(html_text):
        found.append(normalize_link(base_url, raw))

    # Extract bare URLs
    for raw in URL_RE.findall(html.unescape(html_text)):
        found.append(raw.rstrip(").,;"))

    # Deduplicate while preserving order
    deduped: list[str] = []
    seen: set[str] = set()
    for link in found:
        if link not in seen:
            seen.add(link)
            deduped.append(link)

    return deduped
