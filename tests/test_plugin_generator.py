import tempfile
import unittest
from pathlib import Path

from distro_hunter.models import Candidate
from distro_hunter.plugin_generator import (
    GeneratedPluginPreview,
    build_generated_plugin,
    choose_pattern,
    normalize_pattern,
    pattern_to_regex,
    review_generated_plugin,
    validate_generated_plugin,
    write_generated_plugin,
    write_generated_test,
)


class FakeContext:
    def __init__(self, links: list[str]) -> None:
        self.links = links

    def fetch_links(self, url: str) -> list[str]:
        return list(self.links)


class PluginGeneratorTests(unittest.TestCase):
    def test_normalize_pattern_collapses_versions(self) -> None:
        url = "https://example.org/releases/ubuntu-24.04.4-desktop-amd64.iso"
        self.assertEqual(
            normalize_pattern(url),
            "https://example.org/releases/ubuntu-VER-desktop-amd64.iso",
        )

    def test_choose_pattern_prefers_iso_family(self) -> None:
        pattern, examples = choose_pattern(
            [
                "https://example.org/a.sha256",
                "https://example.org/releases/Fedora-Workstation-Live-43-1.6.x86_64.iso",
                "https://example.org/releases/Fedora-Workstation-Live-42-1.1.x86_64.iso",
            ]
        )
        self.assertIn(".iso", pattern)
        self.assertEqual(len(examples), 2)

    def test_pattern_to_regex_restores_tokens(self) -> None:
        regex = pattern_to_regex("https://example.org/archlinux-DATE-x86_64.iso")
        self.assertIn(r"\d{4}\.\d{2}\.\d{2}", regex)

    def test_build_generated_plugin_returns_preview_with_examples(self) -> None:
        context = FakeContext(
            [
                "https://example.org/releases/test-1.0.iso",
                "https://example.org/releases/test-1.1.iso",
                "https://example.org/releases/test-1.1.iso.sig",
            ]
        )

        preview = build_generated_plugin(
            context=context,
            name="Example Distro",
            page_url="https://example.org/releases/",
        )

        self.assertEqual(preview.slug, "example_distro")
        self.assertEqual(len(preview.examples), 2)
        self.assertIn("test-VER.iso", preview.pattern)

    def test_validate_generated_plugin_returns_candidates(self) -> None:
        context = FakeContext(
            [
                "https://example.org/releases/test-1.0.iso",
                "https://example.org/releases/test-1.1.iso",
                "https://example.org/releases/test-1.1.iso.log",
            ]
        )
        preview = build_generated_plugin(
            context=context,
            name="Example Distro",
            page_url="https://example.org/releases/",
        )

        candidates = validate_generated_plugin(preview, context)

        self.assertEqual(
            [candidate.url for candidate in candidates],
            [
                "https://example.org/releases/test-1.0.iso",
                "https://example.org/releases/test-1.1.iso",
            ],
        )
        self.assertTrue(all(isinstance(candidate, Candidate) for candidate in candidates))

    def test_review_generated_plugin_warns_about_multiple_architectures(self) -> None:
        preview = GeneratedPluginPreview(
            name="Example Distro",
            slug="example_distro",
            page_url="https://example.org/releases/",
            include=[],
            exclude=["torrent", ".sig"],
            pattern="https://example.org/releases/example-VER.iso",
            regex=r"https://example\.org/releases/example-\d+(?:\.\d+)+\.iso",
            examples=["https://example.org/releases/example-1.0-x86_64.iso"],
            source="",
        )

        review = review_generated_plugin(
            preview,
            [
                Candidate(url="https://example.org/releases/example-1.0-x86_64.iso"),
                Candidate(url="https://example.org/releases/example-1.0-aarch64.iso"),
            ],
        )

        self.assertTrue(any("multiple architectures" in warning for warning in review.warnings))

    def test_review_generated_plugin_suggests_validation_and_review_tightening(self) -> None:
        preview = GeneratedPluginPreview(
            name="Example Distro",
            slug="example_distro",
            page_url="https://example.org/releases/",
            include=[],
            exclude=["torrent", ".sig"],
            pattern="https://example.org/releases/example-VER.iso",
            regex=r"https://example\.org/releases/example-\d+(?:\.\d+)+\.iso",
            examples=[
                "https://mirror-one.example.org/releases/example-1.0.iso",
                "https://mirror-two.example.org/releases/example-1.0.iso",
            ],
            source="",
        )

        review = review_generated_plugin(preview)

        self.assertTrue(any("--validate" in suggestion for suggestion in review.suggestions))
        self.assertTrue(any("Hosts observed" in note for note in review.notes))

    def test_write_generated_plugin_and_test_create_files(self) -> None:
        context = FakeContext(
            [
                "https://example.org/releases/test-1.0.iso",
                "https://example.org/releases/test-1.1.iso",
            ]
        )
        preview = build_generated_plugin(
            context=context,
            name="Example Distro",
            page_url="https://example.org/releases/",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugin_path = write_generated_plugin(preview, root / "plugins")
            test_path = write_generated_test(preview, plugin_path, root / "tests")

            self.assertTrue(plugin_path.exists())
            self.assertTrue(test_path.exists())
            self.assertIn("Example Distro", plugin_path.read_text(encoding="utf-8"))
            self.assertIn("GeneratedPluginTests", test_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
