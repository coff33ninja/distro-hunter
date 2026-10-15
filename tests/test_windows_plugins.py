from __future__ import annotations

import importlib
import json
import re
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

from distro_hunter.core import DistroHunter, DiscoverySelection, discovery_rows
from distro_hunter.models import DownloadResult
from distro_hunter.plugin_loader import PluginSpec
from distro_hunter.plugin_metadata import metadata_from_fields
from distro_hunter.plugins import windows_common
from distro_hunter.scoring import choose_best

SHA1 = "9d18f7814564421381c94e13c09a9c427baf8018"
UUP_UUID = "ac94e557-eb76-4c8b-a064-0c72d6d3e09c"
UUP_24H2_PAYLOAD = {
    "response": {
        "builds": {
            "1": {
                "title": "Windows 11, version 24H2 (26100.100)",
                "build": "26100.100",
                "arch": "amd64",
                "created": 100,
                "uuid": "bc5fa74a-6fe1-4508-ae6c-cf629a931552",
            },
            "2": {
                "title": "Windows 11, version 24H2 (26100.200)",
                "build": "26100.200",
                "arch": "amd64",
                "created": 200,
                "uuid": UUP_UUID,
            },
            "3": {
                "title": "Windows 11, version 24H2 (26100.300)",
                "build": "26100.300",
                "arch": "arm64",
                "created": 300,
                "uuid": "afa7a3e2-7ee1-40aa-b405-1c4f975cc2b1",
            },
            "4": {
                "title": "Windows 10, version 22H2 (19045.1)",
                "build": "19045.1",
                "arch": "amd64",
                "created": 400,
                "uuid": "1922909f-701e-4a59-ae0c-8e981d5f3703",
            },
        }
    }
}
UUP_FUTURE_PAYLOAD = {
    "response": {
        "builds": {
            "1": {
                "title": "Windows 11, version 27H1 (27000.100)",
                "build": "27000.100",
                "arch": "amd64",
                "created": 500,
                "uuid": "27000000-0000-4000-8000-000000000001",
            },
            "2": {
                "title": "Windows 11, version 26H2 (26300.200)",
                "build": "26300.200",
                "arch": "amd64",
                "created": 450,
                "uuid": "26300000-0000-4000-8000-000000000002",
            },
            "3": {
                "title": "Windows 11, version 26H2 (26300.100)",
                "build": "26300.100",
                "arch": "amd64",
                "created": 400,
                "uuid": "26300000-0000-4000-8000-000000000003",
            },
            "4": {
                "title": "Windows 11, version 26H2 (26300.200)",
                "build": "26300.200",
                "arch": "arm64",
                "created": 425,
                "uuid": "26300000-0000-4000-8000-000000000004",
            },
            "5": {
                "title": "Cumulative Update for .NET Framework for Windows 11, version 27H1",
                "build": "27000.200",
                "arch": "amd64",
                "created": 600,
                "uuid": "27000000-0000-4000-8000-000000000005",
            },
        }
    }
}


class FakeContext:
    def __init__(self, files: list[dict], uup_payload: dict | None = None) -> None:
        self.files = files
        self.uup_payload = uup_payload or {"response": {"builds": {}}}
        self.urls: list[str] = []

    def fetch_text(self, url: str) -> str:
        self.urls.append(url)
        if url.startswith("https://api.uupdump.net/listid.php?"):
            return json.dumps(self.uup_payload)
        return json.dumps({"files": self.files})


class WindowsPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        windows_common._cache.clear()

    def test_every_catalog_entry_has_a_stub_and_valid_regexes(self) -> None:
        for slug, spec in windows_common.CATALOG.items():
            module = importlib.import_module(f"distro_hunter.plugins.{slug}")
            self.assertEqual(module.NAME, spec.name)
            self.assertEqual(module.METADATA["family"], "windows")
            for _identifier, pattern in spec.sources:
                re.compile(pattern)

    def test_discover_builds_verified_archive_candidates(self) -> None:
        context = FakeContext(
            [
                {"name": "Windows 11/23H2/Win11_23H2_English_x64.iso", "sha1": SHA1},
                {"name": "Windows 11/22H2/Win11_22H2_English_x64.iso", "sha1": "0" * 40},
            ]
        )
        module = importlib.import_module("distro_hunter.plugins.windows_11_23h2_x64")
        best = choose_best(module.discover(context))

        self.assertIsNotNone(best)
        self.assertEqual(
            best.url,
            "https://archive.org/download/windows-iso-collection-flutter/Windows%2011/23H2/Win11_23H2_English_x64.iso",
        )
        self.assertEqual(best.filename, "Windows_11_23H2_22631_x64_en-US.iso")
        self.assertEqual(best.metadata["checksum_algorithm"], "sha1")
        self.assertEqual(best.metadata["checksum_expected"], SHA1)

    def test_metadata_is_fetched_once_per_item(self) -> None:
        context = FakeContext([{"name": "Windows 95/x/win95.iso", "sha1": SHA1}])
        windows_common.discover_spec(context, windows_common.CATALOG["windows_95_rtm_x86"])
        windows_common.discover_spec(context, windows_common.CATALOG["windows_95_osr2_x86"])
        self.assertEqual(len(context.urls), len(windows_common.TREE_ITEMS))

    def test_discover_includes_latest_matching_uup_build_as_link_only(self) -> None:
        context = FakeContext([], UUP_24H2_PAYLOAD)

        candidates = windows_common.discover_spec(
            context,
            windows_common.CATALOG["windows_11_24h2_x64"],
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].url, f"https://uupdump.net/selectlang.php?id={UUP_UUID}")
        self.assertEqual(candidates[0].version, "26100.200")
        self.assertEqual(candidates[0].arch, "x86_64")
        self.assertFalse(candidates[0].metadata["downloadable"])
        self.assertEqual(candidates[0].metadata["source_kind"], "UUP Dump")
        self.assertEqual(candidates[1].version, "26100.100")
        self.assertTrue(
            any(url.startswith("https://api.uupdump.net/listid.php?") for url in context.urls)
        )

    def test_catalog_includes_windows_11_26h2_and_live_server_2025_source(self) -> None:
        x64 = windows_common.CATALOG["windows_11_26h2_x64"]
        arm64 = windows_common.CATALOG["windows_11_26h2_arm64"]
        server_2025 = windows_common.CATALOG["windows_server_2025_x64"]

        self.assertEqual(x64.version, "26H2")
        self.assertEqual(arm64.arch, "arm64")
        self.assertIn(
            ("windows-11-26h2-from-microsoft", r"^X64/Windows11_Client_x64_en-us_.*\.iso$"),
            x64.sources,
        )
        self.assertIn(
            ("windows-11-26h2-from-microsoft", r"^Windows11_Client_arm64_en-us_.*\.iso$"),
            arm64.sources,
        )
        self.assertEqual(
            server_2025.sources[0][0],
            "en-us_windows_server_2025_updated_march_2026_x64_dvd_8e06425a",
        )

    def test_windows_11_21h2_uses_archived_iso_without_uup_lookup(self) -> None:
        spec = windows_common.CATALOG["windows_11_21h2_x64"]
        context = FakeContext(
            [{"name": "Windows 11/RTM/Win11_English_x64.iso", "sha1": SHA1}]
        )

        candidates = windows_common.discover_spec(context, spec)

        self.assertTrue(candidates)
        self.assertTrue(
            any(candidate.url.endswith("/Win11_English_x64.iso") for candidate in candidates)
        )
        self.assertFalse(
            any(url.startswith("https://api.uupdump.net/listid.php?") for url in context.urls)
        )

    def test_future_uup_plugins_return_latest_build_per_release_and_architecture(self) -> None:
        context = FakeContext([], UUP_FUTURE_PAYLOAD)
        x64_spec = windows_common.CATALOG["windows_11_latest_x64"]
        arm64_spec = windows_common.CATALOG["windows_11_latest_arm64"]

        x64 = windows_common.discover_uup_candidates(context, x64_spec)
        arm64 = windows_common.discover_uup_candidates(context, arm64_spec)

        self.assertEqual([candidate.version for candidate in x64], ["27000.100", "26300.200"])
        self.assertEqual([candidate.version for candidate in arm64], ["26300.200"])
        self.assertTrue(all(not candidate.metadata["downloadable"] for candidate in x64 + arm64))
        self.assertEqual(x64[0].metadata["release_version"], "27H1")

    def test_legacy_media_specs_discover_all_related_disk_files(self) -> None:
        files = [
            {"name": "MS DOS 6.0/Microsoft DOS 6.0 (3.5)/Disk1.img", "sha1": SHA1},
            {"name": "MS DOS 6.0/Microsoft DOS 6.0 (3.5)/Disk2.img", "sha1": SHA1},
            {"name": "MS DOS 6.0/Microsoft DOS 6.0 (3.5)/Disk3.img", "sha1": SHA1},
            {
                "name": "Windows 1.0/Microsoft Windows 1.01 (5.25)/DISK1-SETUP.IMG",
                "sha1": SHA1,
            },
            {
                "name": "Windows 3.0/Microsoft Windows 3.0 (3.5)/DISK1.IMG",
                "sha1": SHA1,
            },
            {
                "name": "Windows NT 4.0/NT 4.0 Enterprise Server (4.00.1381.1)/winnt40_x86en_entsrv.d1.iso",
                "sha1": SHA1,
            },
            {
                "name": "Windows NT 4.0/NT 4.0 Enterprise Server (4.00.1381.1)/winnt40_x86en_entsrv.d2.iso",
                "sha1": SHA1,
            },
            {
                "name": "en_win_srv_2003_r2_enterprise_x64_cd1.iso",
                "sha1": SHA1,
            },
            {
                "name": "en_win_srv_2003_r2_enterprise_x64_cd2.iso",
                "sha1": SHA1,
            },
        ]
        context = FakeContext(files)
        slugs = (
            "windows_dos_6_0_x86",
            "windows_1_3_floppy_sets_x86",
            "windows_nt_4_0_enterprise_x86",
            "windows_server_2003_r2_enterprise_x64",
        )
        expected_counts = (3, 2, 2, 2)

        for slug, expected_count in zip(slugs, expected_counts, strict=True):
            spec = windows_common.CATALOG[slug]
            candidates = windows_common.discover_spec(context, spec)
            self.assertTrue(spec.batch_download, slug)
            self.assertEqual(len(candidates), expected_count, slug)
            filenames = {candidate.filename for candidate in candidates}
            self.assertEqual(len(filenames), expected_count, slug)
            self.assertTrue(
                all(
                    candidate.metadata["preserve_related_artifacts"]
                    for candidate in candidates
                )
            )

    def test_batch_download_processes_all_related_candidates(self) -> None:
        candidates = [
            windows_common.Candidate(
                url=f"https://archive.org/download/set/disk{index}.img",
                filename=f"disk{index}.img",
                metadata={"preserve_related_artifacts": True},
            )
            for index in (1, 2)
        ]
        plugin = PluginSpec(
            slug="windows_dos_6_0_x86",
            name="MS-DOS 6.0 floppy set",
            module=types.SimpleNamespace(discover=lambda _context: candidates),
            batch_download=True,
        )
        discovery = DiscoverySelection(
            plugin=plugin,
            ranked=candidates,
            selected=candidates[0],
        )
        hunter = object.__new__(DistroHunter)
        hunter.state = Mock()
        hunter.state.prioritize_mirror_candidates.side_effect = lambda values: values
        hunter.downloads = Mock()
        hunter.journal = Mock()

        def process(_slug: str, candidate, **_kwargs):
            path = Path("downloads") / candidate.filename
            return DownloadResult(
                plugin_slug=plugin.slug,
                candidate=candidate,
                path=path,
                downloaded=True,
                artifact_paths=[path],
            )

        hunter.downloads.process.side_effect = process

        result = DistroHunter.download_one(hunter, discovery)

        self.assertEqual(hunter.downloads.process.call_count, 2)
        self.assertEqual(
            result.artifact_paths,
            [Path("downloads/disk1.img"), Path("downloads/disk2.img")],
        )
        hunter.state.remember_download.assert_called_once_with(result)

    def test_batch_download_reports_partial_member_failure(self) -> None:
        candidates = [
            windows_common.Candidate(
                url=f"https://archive.org/download/set/disk{index}.img",
                filename=f"disk{index}.img",
                metadata={"preserve_related_artifacts": True},
            )
            for index in (1, 2)
        ]
        plugin = PluginSpec(
            slug="windows_dos_6_0_x86",
            name="MS-DOS 6.0 floppy set",
            module=types.SimpleNamespace(discover=lambda _context: candidates),
            batch_download=True,
        )
        discovery = DiscoverySelection(
            plugin=plugin,
            ranked=candidates,
            selected=candidates[0],
        )
        hunter = object.__new__(DistroHunter)
        hunter.state = Mock()
        hunter.state.prioritize_mirror_candidates.side_effect = lambda values: values
        hunter.downloads = Mock()
        hunter.downloads.process.side_effect = [
            DownloadResult(
                plugin_slug=plugin.slug,
                candidate=candidates[0],
                path=Path("downloads/disk1.img"),
                downloaded=True,
                artifact_paths=[Path("downloads/disk1.img")],
            ),
            OSError("disk2 unavailable"),
        ]
        hunter.journal = Mock()

        result = DistroHunter.download_one(hunter, discovery)

        self.assertEqual(result.artifact_paths, [Path("downloads/disk1.img")])
        self.assertIn("disk2.img", result.skipped_reason)
        hunter.state.remember_download.assert_called_once_with(result)

    def test_discovery_rows_show_uup_build_link_and_platform_details(self) -> None:
        plugin = PluginSpec(
            slug="windows_11_24h2_x64",
            name="Windows 11 24H2 (x64)",
            module=types.SimpleNamespace(discover=lambda _context: []),
            metadata=metadata_from_fields(
                family="windows",
                architecture="x86_64",
                edition_type="11-24h2",
                source_kind="archive-org",
            ),
        )
        uup_candidate = windows_common.Candidate(
            url=f"https://uupdump.net/selectlang.php?id={UUP_UUID}",
            filename="Windows 11, version 24H2 (26100.200)",
            version="26100.200",
            arch="x86_64",
            metadata={"downloadable": False, "source_kind": "UUP Dump"},
        )
        discovery = DiscoverySelection(plugin=plugin, ranked=[uup_candidate], selected=None)

        rows = discovery_rows([discovery])

        self.assertEqual(len(rows), 1)
        self.assertIn("UUP Dump", rows[0])
        self.assertIn("edition=", rows[0])
        self.assertIn("arch=x86_64", rows[0])
        self.assertIn(uup_candidate.url, rows[0])

    def test_uup_link_is_never_selected_for_download(self) -> None:
        uup_candidate = windows_common.discover_uup_candidates(
            FakeContext([], UUP_24H2_PAYLOAD),
            windows_common.CATALOG["windows_11_24h2_x64"],
        )[0]
        archive_candidate = windows_common.Candidate(
            url="https://archive.org/download/item/windows.iso",
            filename="windows.iso",
            arch="x86_64",
        )
        plugin = PluginSpec(
            slug="windows_11_24h2_x64",
            name="Windows 11 24H2 (x64)",
            module=types.SimpleNamespace(
                discover=lambda _context: [uup_candidate, archive_candidate]
            ),
        )

        discovery = DistroHunter._discover_plugin(
            object.__new__(DistroHunter),
            plugin,
            FakeContext([]),
        )

        self.assertIs(discovery.selected, archive_candidate)
        self.assertIn(uup_candidate, discovery.ranked)


if __name__ == "__main__":
    unittest.main()
