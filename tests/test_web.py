"""Tests for distro_hunter.web."""

# pylint: disable=protected-access
import io
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from distro_hunter.web import WebClient


class FakeResponse:
    """Minimal urllib response stub for tests."""

    def __init__(
        self,
        body: bytes,
        *,
        url: str = "https://example.org/file.iso",
        headers: dict[str, str] | None = None,
        status: int = 200,
    ) -> None:
        """Initialize a fake response."""
        self._body = io.BytesIO(body)
        self._headers = Message()
        for key, value in (headers or {}).items():
            self._headers[key] = value
        self._url = url
        self.status = status

    @property
    def headers(self) -> Message:
        """Return response headers."""
        return self._headers

    def read(self, size: int = -1) -> bytes:
        """Read up to *size* bytes from the body."""
        return self._body.read(size)

    def geturl(self) -> str:
        """Return the final URL."""
        return self._url

    def __enter__(self):
        """Return self for context manager protocol."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Return None (do not suppress exceptions)."""


class WebClientTests(unittest.TestCase):
    """Tests for WebClient retry, caching, and download behavior."""

    def test_request_retries_transient_http_error(self) -> None:
        """Retry on transient HTTP errors and succeed."""
        client = WebClient(
            "test-agent", timeout_seconds=5, retry_attempts=3, retry_backoff_seconds=0
        )
        transient = urllib.error.HTTPError(
            "https://example.org/page",
            503,
            "Service Unavailable",
            hdrs=Message(),
            fp=None,
        )

        with patch(
            "urllib.request.urlopen", side_effect=[transient, FakeResponse(b"ok")]
        ) as mocked_urlopen:
            body, _, _ = client._request("https://example.org/page")

        self.assertEqual(body, b"ok")
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_request_does_not_retry_non_transient_http_error(self) -> None:
        """Do not retry on non-transient HTTP errors."""
        client = WebClient(
            "test-agent", timeout_seconds=5, retry_attempts=3, retry_backoff_seconds=0
        )
        missing = urllib.error.HTTPError(
            "https://example.org/page",
            404,
            "Not Found",
            hdrs=Message(),
            fp=None,
        )

        with (
            patch("urllib.request.urlopen", side_effect=[missing]) as mocked_urlopen,
            self.assertRaises(urllib.error.HTTPError),
        ):
            client._request("https://example.org/page")

        self.assertEqual(mocked_urlopen.call_count, 1)

    def test_download_retries_after_url_error(self) -> None:
        """Retry download after a URLError and succeed."""
        client = WebClient(
            "test-agent", timeout_seconds=5, retry_attempts=3, retry_backoff_seconds=0
        )
        failure = urllib.error.URLError("temporary failure")
        response = FakeResponse(b"payload", headers={"Content-Length": "7"})

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "file.iso"
            with patch(
                "urllib.request.urlopen", side_effect=[failure, response]
            ) as mocked_urlopen:
                client.download("https://example.org/file.iso", str(destination))

            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertEqual(mocked_urlopen.call_count, 2)

    def test_download_resumes_partial_file_after_timeout(self) -> None:
        """Resume a partial download after a timeout."""

        class FlakyResponse(FakeResponse):
            """Response that times out on first read, succeeds on retry."""

            def __init__(self) -> None:
                """Initialize flaky response."""
                super().__init__(b"", headers={"Content-Length": "7"})
                self._reads = 0

            def read(self, size: int = -1) -> bytes:
                """Return partial data then raise TimeoutError."""
                self._reads += 1
                if self._reads == 1:
                    return b"pay"
                raise TimeoutError("timed out")

        client = WebClient(
            "test-agent", timeout_seconds=5, retry_attempts=2, retry_backoff_seconds=0
        )
        requests: list[urllib.request.Request] = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            if len(requests) == 1:
                self.assertEqual(timeout, 120)
                self.assertIsNone(request.headers.get("Range"))
                return FlakyResponse()
            self.assertEqual(request.headers.get("Range"), "bytes=3-")
            self.assertEqual(timeout, 120)
            return FakeResponse(
                b"load",
                headers={
                    "Content-Length": "4",
                    "Content-Range": "bytes 3-6/7",
                },
                status=206,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "file.iso.part"
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                client.download("https://example.org/file.iso", str(destination))

            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertEqual(len(requests), 2)

    def test_fetch_text_uses_disk_cache_across_client_instances(self) -> None:
        """Second client instance reads from disk cache without network."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "pages"
            url = "https://example.org/page"

            with patch(
                "urllib.request.urlopen", return_value=FakeResponse(b"hello")
            ) as mocked_urlopen:
                first = WebClient(
                    "test-agent",
                    timeout_seconds=5,
                    retry_attempts=1,
                    retry_backoff_seconds=0,
                    page_cache_dir=cache_dir,
                    page_cache_ttl_seconds=3600,
                )
                self.assertEqual(first.fetch_text(url), "hello")
                self.assertEqual(mocked_urlopen.call_count, 1)

            with patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("network should not be used"),
            ) as mocked_urlopen:
                second = WebClient(
                    "test-agent",
                    timeout_seconds=5,
                    retry_attempts=1,
                    retry_backoff_seconds=0,
                    page_cache_dir=cache_dir,
                    page_cache_ttl_seconds=3600,
                )
                self.assertEqual(second.fetch_text(url), "hello")
                self.assertEqual(mocked_urlopen.call_count, 0)

    def test_fetch_text_refreshes_expired_disk_cache(self) -> None:
        """Expired cache entries trigger a fresh fetch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "pages"
            url = "https://example.org/page"
            first = WebClient(
                "test-agent",
                timeout_seconds=5,
                retry_attempts=1,
                retry_backoff_seconds=0,
                page_cache_dir=cache_dir,
                page_cache_ttl_seconds=1,
            )

            with patch("urllib.request.urlopen", return_value=FakeResponse(b"old")):
                self.assertEqual(first.fetch_text(url), "old")

            cache_files = list(cache_dir.glob("*.html"))
            self.assertEqual(len(cache_files), 1)
            stale_time = cache_files[0].stat().st_mtime - 10
            os.utime(cache_files[0], (stale_time, stale_time))

            with patch(
                "urllib.request.urlopen", return_value=FakeResponse(b"new")
            ) as mocked_urlopen:
                second = WebClient(
                    "test-agent",
                    timeout_seconds=5,
                    retry_attempts=1,
                    retry_backoff_seconds=0,
                    page_cache_dir=cache_dir,
                    page_cache_ttl_seconds=1,
                )
                self.assertEqual(second.fetch_text(url), "new")
                self.assertEqual(mocked_urlopen.call_count, 1)

    def test_concurrent_fetch_text_publishes_single_cache_file(self) -> None:
        """Concurrent writers produce exactly one cache file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "pages"
            url = "https://example.org/page"

            def load(_index: int) -> str:
                client = WebClient(
                    "test-agent",
                    timeout_seconds=5,
                    retry_attempts=1,
                    retry_backoff_seconds=0,
                    page_cache_dir=cache_dir,
                    page_cache_ttl_seconds=3600,
                )
                return client.fetch_text(url)

            with (
                patch(
                    "urllib.request.urlopen",
                    side_effect=lambda *a, **k: FakeResponse(b"hello"),
                ),
                ThreadPoolExecutor(max_workers=8) as executor,
            ):
                results = list(executor.map(load, range(32)))

            self.assertEqual(results, ["hello"] * 32)
            cache_files = list(cache_dir.glob("*.html"))
            self.assertEqual(len(cache_files), 1)
            self.assertEqual(cache_files[0].read_text(encoding="utf-8"), "hello")
            self.assertEqual(list(cache_dir.glob("*.tmp")), [])

    def test_fetch_links_uses_final_url_and_strips_whitespace(self) -> None:
        """Relative links resolve against the redirect target."""
        client = WebClient(
            "test-agent",
            timeout_seconds=5,
            retry_attempts=1,
            retry_backoff_seconds=0,
        )
        body = b'<a href=" downloads/\ninstaller.iso ">Download</a>'
        response = FakeResponse(
            body,
            url="https://mirror.example.org/releases/",
        )

        with patch("urllib.request.urlopen", return_value=response):
            links = client.fetch_links("https://example.org/start")

        self.assertEqual(
            links,
            ["https://mirror.example.org/releases/downloads/installer.iso"],
        )

    def test_fetch_links_reuses_cached_final_url_on_disk_cache_hit(self) -> None:
        """Disk-cached pages reuse the stored final URL for link resolution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "pages"
            url = "https://example.org/start"
            body = b'<a href="downloads/installer.iso">Download</a>'
            expected = ["https://mirror.example.org/releases/downloads/installer.iso"]

            with patch(
                "urllib.request.urlopen",
                return_value=FakeResponse(body, url="https://mirror.example.org/releases/"),
            ):
                first = WebClient(
                    "test-agent",
                    timeout_seconds=5,
                    retry_attempts=1,
                    retry_backoff_seconds=0,
                    page_cache_dir=cache_dir,
                    page_cache_ttl_seconds=3600,
                )
                self.assertEqual(first.fetch_links(url), expected)

            with patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("network should not be used"),
            ):
                second = WebClient(
                    "test-agent",
                    timeout_seconds=5,
                    retry_attempts=1,
                    retry_backoff_seconds=0,
                    page_cache_dir=cache_dir,
                    page_cache_ttl_seconds=3600,
                )
                self.assertEqual(second.fetch_links(url), expected)

            self.assertEqual(list(cache_dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
