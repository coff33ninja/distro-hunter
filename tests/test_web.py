import io
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from distro_hunter.web import WebClient


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        url: str = "https://example.org/file.iso",
        headers: dict[str, str] | None = None,
        status: int = 200,
    ) -> None:
        self._body = io.BytesIO(body)
        self._headers = Message()
        for key, value in (headers or {}).items():
            self._headers[key] = value
        self._url = url
        self.status = status

    @property
    def headers(self) -> Message:
        return self._headers

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class WebClientTests(unittest.TestCase):
    def test_request_retries_transient_http_error(self) -> None:
        client = WebClient("test-agent", timeout_seconds=5, retry_attempts=3, retry_backoff_seconds=0)
        transient = urllib.error.HTTPError(
            "https://example.org/page",
            503,
            "Service Unavailable",
            hdrs=Message(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=[transient, FakeResponse(b"ok")]) as mocked_urlopen:
            body, _, _ = client._request("https://example.org/page")

        self.assertEqual(body, b"ok")
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_request_does_not_retry_non_transient_http_error(self) -> None:
        client = WebClient("test-agent", timeout_seconds=5, retry_attempts=3, retry_backoff_seconds=0)
        missing = urllib.error.HTTPError(
            "https://example.org/page",
            404,
            "Not Found",
            hdrs=Message(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=[missing]) as mocked_urlopen:
            with self.assertRaises(urllib.error.HTTPError):
                client._request("https://example.org/page")

        self.assertEqual(mocked_urlopen.call_count, 1)

    def test_download_retries_after_url_error(self) -> None:
        client = WebClient("test-agent", timeout_seconds=5, retry_attempts=3, retry_backoff_seconds=0)
        failure = urllib.error.URLError("temporary failure")
        response = FakeResponse(b"payload", headers={"Content-Length": "7"})

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "file.iso"
            with patch("urllib.request.urlopen", side_effect=[failure, response]) as mocked_urlopen:
                client.download("https://example.org/file.iso", str(destination))

            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertEqual(mocked_urlopen.call_count, 2)

    def test_download_resumes_partial_file_after_timeout(self) -> None:
        class FlakyResponse(FakeResponse):
            def __init__(self) -> None:
                super().__init__(b"", headers={"Content-Length": "7"})
                self._reads = 0

            def read(self, size: int = -1) -> bytes:
                self._reads += 1
                if self._reads == 1:
                    return b"pay"
                raise TimeoutError("timed out")

        client = WebClient("test-agent", timeout_seconds=5, retry_attempts=2, retry_backoff_seconds=0)
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
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "pages"
            url = "https://example.org/page"

            with patch("urllib.request.urlopen", return_value=FakeResponse(b"hello")) as mocked_urlopen:
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

            with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be used")) as mocked_urlopen:
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

            with patch("urllib.request.urlopen", return_value=FakeResponse(b"new")) as mocked_urlopen:
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

    def test_fetch_links_uses_final_url_and_strips_whitespace(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
