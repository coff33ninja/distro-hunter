import types
import unittest

from distro_hunter.core import (
    DOCTOR_CHANGED_PAGE_SHAPE,
    DOCTOR_DOWNLOAD_HEAD_FAILED,
    DOCTOR_NO_CANDIDATES,
    DOCTOR_OK,
    DistroHunter,
    doctor_rows,
    doctor_summary,
)
from distro_hunter.models import Candidate
from distro_hunter.plugin_loader import PluginSpec


class FakeWeb:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def inspect_remote_file(self, url: str):
        if self.error:
            raise self.error
        return (
            {
                "Content-Length": "1024",
                "ETag": '"test-etag"',
                "Last-Modified": "Mon, 30 Mar 2026 18:00:00 GMT",
            },
            "https://mirror.example.org/test.iso",
        )


def make_plugin(slug: str, discover):
    module = types.SimpleNamespace(discover=discover)
    return PluginSpec(slug=slug, name=slug.replace("_", " ").title(), module=module)


def make_hunter(web: FakeWeb) -> DistroHunter:
    hunter = object.__new__(DistroHunter)
    hunter.context = types.SimpleNamespace(web=web)
    return hunter


class DoctorTests(unittest.TestCase):
    def test_doctor_one_reports_changed_page_shape_on_discovery_error(self) -> None:
        plugin = make_plugin("broken_plugin", lambda context: (_ for _ in ()).throw(RuntimeError("unexpected markup")))
        hunter = make_hunter(FakeWeb())

        result = DistroHunter.doctor_one(hunter, plugin)

        self.assertEqual(result.status, DOCTOR_CHANGED_PAGE_SHAPE)
        self.assertEqual(result.error, "unexpected markup")

    def test_doctor_one_reports_no_candidates(self) -> None:
        plugin = make_plugin("empty_plugin", lambda context: [])
        hunter = make_hunter(FakeWeb())

        result = DistroHunter.doctor_one(hunter, plugin)

        self.assertEqual(result.status, DOCTOR_NO_CANDIDATES)
        self.assertIsNone(result.selected)

    def test_doctor_one_reports_download_head_failure(self) -> None:
        plugin = make_plugin(
            "head_failure",
            lambda context: [Candidate(url="https://example.org/test.iso", filename="test.iso", version="1.0")],
        )
        hunter = make_hunter(FakeWeb(error=RuntimeError("timed out")))

        result = DistroHunter.doctor_one(hunter, plugin)

        self.assertEqual(result.status, DOCTOR_DOWNLOAD_HEAD_FAILED)
        self.assertEqual(result.error, "timed out")
        self.assertEqual(result.selected.url, "https://example.org/test.iso")

    def test_doctor_one_reports_ok_with_remote_metadata(self) -> None:
        plugin = make_plugin(
            "healthy_plugin",
            lambda context: [Candidate(url="https://example.org/test.iso", filename="test.iso", version="1.0")],
        )
        hunter = make_hunter(FakeWeb())

        result = DistroHunter.doctor_one(hunter, plugin)

        self.assertEqual(result.status, DOCTOR_OK)
        self.assertTrue(result.healthy)
        self.assertEqual(result.remote.final_url, "https://mirror.example.org/test.iso")
        self.assertEqual(result.remote.size, 1024)

    def test_doctor_rows_and_summary_render_expected_statuses(self) -> None:
        broken = make_plugin("broken_plugin", lambda context: [])
        empty = make_plugin("empty_plugin", lambda context: [])
        failed = make_plugin("failed_plugin", lambda context: [])
        healthy = make_plugin("healthy_plugin", lambda context: [])

        results = [
            types.SimpleNamespace(
                plugin=healthy,
                status=DOCTOR_OK,
                healthy=True,
                selected=Candidate(url="https://example.org/test.iso", filename="test.iso", version="1.0"),
                remote=None,
                error=None,
                duration_seconds=0.25,
                health={"last_success_at": "2026-03-30T18:00:00+00:00", "failure_count": 0},
            ),
            types.SimpleNamespace(
                plugin=empty,
                status=DOCTOR_NO_CANDIDATES,
                healthy=False,
                selected=None,
                remote=None,
                error=None,
                duration_seconds=0.10,
                health={"last_success_at": None, "failure_count": 1},
            ),
            types.SimpleNamespace(
                plugin=failed,
                status=DOCTOR_DOWNLOAD_HEAD_FAILED,
                healthy=False,
                selected=Candidate(url="https://example.org/test.iso", filename="test.iso", version="1.0"),
                remote=None,
                error="timed out",
                duration_seconds=0.50,
                health={"last_success_at": "2026-03-29T18:00:00+00:00", "failure_count": 2},
            ),
            types.SimpleNamespace(
                plugin=broken,
                status=DOCTOR_CHANGED_PAGE_SHAPE,
                healthy=False,
                selected=None,
                remote=None,
                error="unexpected markup",
                duration_seconds=0.75,
                health={"last_success_at": "2026-03-28T18:00:00+00:00", "failure_count": 3},
            ),
        ]

        rows = doctor_rows(results)
        summary = doctor_summary(results)

        self.assertEqual(
            rows[0],
            "healthy_plugin: ok: test.iso (version=1.0) (0.25s, last_good=2026-03-30T18:00:00+00:00, failures=0)",
        )
        self.assertEqual(rows[1], "empty_plugin: no candidates (0.10s, last_good=never, failures=1)")
        self.assertEqual(
            rows[2],
            "failed_plugin: download head failed: https://example.org/test.iso -> timed out (0.50s, last_good=2026-03-29T18:00:00+00:00, failures=2)",
        )
        self.assertEqual(
            rows[3],
            "broken_plugin: changed page shape: unexpected markup (0.75s, last_good=2026-03-28T18:00:00+00:00, failures=3)",
        )
        self.assertEqual(
            summary,
            "Doctor summary: 1 ok, 1 no candidates, 1 changed page shape, 1 download head failed in 1.60s; unhealthy=empty_plugin, failed_plugin, broken_plugin",
        )

    def test_doctor_persists_health_metadata(self) -> None:
        plugin = make_plugin(
            "healthy_plugin",
            lambda context: [Candidate(url="https://example.org/test.iso", filename="test.iso", version="1.0")],
        )
        hunter = make_hunter(FakeWeb())
        hunter.plugins = [plugin]
        hunter.state = types.SimpleNamespace(records={}, save_calls=0)

        def remember_health(plugin_slug: str, *, status: str, healthy: bool, error: str | None = None) -> None:
            record = {
                "status": status,
                "healthy": healthy,
                "error": error,
            }
            hunter.state.records[plugin_slug] = record
            return record

        def save() -> None:
            hunter.state.save_calls += 1

        hunter.state.remember_health = remember_health
        hunter.state.save = save

        results = DistroHunter.doctor(hunter)

        self.assertEqual(len(results), 1)
        self.assertEqual(hunter.state.records["healthy_plugin"]["status"], DOCTOR_OK)
        self.assertTrue(hunter.state.records["healthy_plugin"]["healthy"])
        self.assertEqual(hunter.state.save_calls, 1)
        self.assertIsNotNone(results[0].health)
        self.assertEqual(results[0].health["status"], DOCTOR_OK)


if __name__ == "__main__":
    unittest.main()
