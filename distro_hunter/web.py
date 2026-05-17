from __future__ import annotations

import hashlib
import http.client
import re
import socket
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Iterable

from distro_hunter.utils import ensure_directory
from distro_hunter.url_utils import extract_links_from_html, normalize_link


RETRIABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}
LINK_WHITESPACE_RE = re.compile(r"\s+")
CONTENT_RANGE_TOTAL_RE = re.compile(r"bytes\s+\d+-\d+/(\d+|\*)", re.IGNORECASE)
MIN_DOWNLOAD_TIMEOUT_SECONDS = 120


class WebClient:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: int,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        page_cache_dir: Path | None = None,
        page_cache_ttl_seconds: int = 0,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.page_cache_dir = page_cache_dir.resolve() if page_cache_dir else None
        self.page_cache_ttl_seconds = max(0, int(page_cache_ttl_seconds))
        self._page_cache: dict[str, str] = {}
        self._page_final_urls: dict[str, str] = {}

    def _cache_path_for_url(self, url: str) -> Path | None:
        if self.page_cache_dir is None or self.page_cache_ttl_seconds <= 0:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.page_cache_dir / f"{digest}.html"

    def _load_disk_cached_page(self, url: str) -> str | None:
        cache_path = self._cache_path_for_url(url)
        if cache_path is None or not cache_path.exists():
            return None
        age_seconds = time.time() - cache_path.stat().st_mtime
        if age_seconds > self.page_cache_ttl_seconds:
            return None
        return cache_path.read_text(encoding="utf-8")

    def _store_disk_cached_page(self, url: str, text: str) -> None:
        cache_path = self._cache_path_for_url(url)
        if cache_path is None:
            return
        ensure_directory(cache_path.parent)
        temp_path = cache_path.parent / f"{cache_path.name}.{time.time_ns()}.tmp"
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(cache_path)

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code in RETRIABLE_HTTP_CODES
        return isinstance(
            exc,
            (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
                socket.timeout,
                ConnectionResetError,
            ),
        )

    def _download_timeout_seconds(self) -> int:
        return max(int(self.timeout_seconds), MIN_DOWNLOAD_TIMEOUT_SECONDS)

    def _response_supports_resume(self, response) -> bool:
        return bool(
            response.headers.get("Content-Range")
            or getattr(response, "status", None) == 206
        )

    def _response_total_bytes(self, response, *, resumed_bytes: int = 0) -> int | None:
        content_range = response.headers.get("Content-Range")
        if content_range:
            match = CONTENT_RANGE_TOTAL_RE.search(content_range)
            if match and match.group(1).isdigit():
                return int(match.group(1))

        total_header = response.headers.get("Content-Length")
        if total_header and total_header.isdigit():
            total = int(total_header)
            if resumed_bytes and self._response_supports_resume(response):
                return resumed_bytes + total
            return total
        return None

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * attempt
        if delay > 0:
            time.sleep(delay)

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        read_body: bool = True,
    ) -> tuple[bytes, Message, str]:
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, headers=request_headers, method=method)
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read() if read_body else b""
                    return body, response.headers, response.geturl()
            except Exception as exc:
                if attempt >= self.retry_attempts or not self._should_retry(exc):
                    raise
                self._sleep_before_retry(attempt)
        raise RuntimeError("unreachable")

    def fetch_text(self, url: str) -> str:
        if url not in self._page_cache:
            cached = self._load_disk_cached_page(url)
            if cached is not None:
                self._page_cache[url] = cached
            else:
                body, _, final_url = self._request(url, method="GET")
                text = body.decode("utf-8", "ignore")
                self._page_cache[url] = text
                self._page_final_urls[url] = final_url
                self._store_disk_cached_page(url, text)
        return self._page_cache[url]

    def fetch_links(self, url: str) -> list[str]:
        html_text = self.fetch_text(url)
        base_url = self._page_final_urls.get(url, url)
        deduped: list[str] = []
        seen: set[str] = set()

        for link in extract_links_from_html(html_text, base_url):
            cleaned = LINK_WHITESPACE_RE.sub("", link)
            if cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)

        return deduped

    def inspect_remote_file(self, url: str) -> tuple[Message, str]:
        try:
            _, headers, final_url = self._request(url, method="HEAD", read_body=False)
            return headers, final_url
        except urllib.error.HTTPError as exc:
            if exc.code not in {403, 405}:
                raise
        _, headers, final_url = self._request(
            url,
            method="GET",
            headers={"Range": "bytes=0-0"},
            read_body=True,
        )
        return headers, final_url

    def download(self, url: str, destination: str, progress_callback=None) -> None:
        destination_path = Path(destination)
        for attempt in range(1, self.retry_attempts + 1):
            existing_bytes = destination_path.stat().st_size if destination_path.exists() else 0
            request_headers = {"User-Agent": self.user_agent}
            if existing_bytes > 0:
                request_headers["Range"] = f"bytes={existing_bytes}-"
            request = urllib.request.Request(url, headers=request_headers)
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self._download_timeout_seconds(),
                ) as response:
                    resuming = existing_bytes > 0 and self._response_supports_resume(response)
                    if not resuming:
                        existing_bytes = 0

                    total = self._response_total_bytes(response, resumed_bytes=existing_bytes)
                    downloaded = existing_bytes
                    if progress_callback and downloaded:
                        progress_callback(downloaded, total)

                    with open(destination, "ab" if resuming else "wb") as handle:
                        if not resuming:
                            handle.seek(0)
                            handle.truncate()

                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            handle.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total)
                return
            except Exception as exc:
                if attempt >= self.retry_attempts or not self._should_retry(exc):
                    raise
                self._sleep_before_retry(attempt)


def filter_links(links: Iterable[str], *, include: Iterable[str], exclude: Iterable[str]) -> list[str]:
    include_terms = [term.lower() for term in include]
    exclude_terms = [term.lower() for term in exclude]
    output: list[str] = []
    for link in links:
        lowered = link.lower()
        if include_terms and not all(term in lowered for term in include_terms):
            continue
        if any(term in lowered for term in exclude_terms):
            continue
        output.append(link)
    return output
