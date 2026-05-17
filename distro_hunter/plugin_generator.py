from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from distro_hunter.models import Candidate
from distro_hunter.plugin_loader import DiscoveryContext
from distro_hunter.utils import ensure_directory, slugify
from distro_hunter.web import filter_links


TOKEN_PATTERNS = [
    (re.compile(r"\d{4}\.\d{2}\.\d{2}"), "DATE"),
    (re.compile(r"\d+\.\d+\.\d+"), "VER"),
    (re.compile(r"\d+\.\d+"), "VER"),
    (re.compile(r"\d+"), "NUM"),
]
ARCH_HINTS = (
    ("x86_64", "x86_64"),
    ("amd64", "amd64"),
    ("aarch64", "aarch64"),
    ("arm64", "arm64"),
)
RECOMMENDED_ARTIFACT_EXTENSIONS = {".iso", ".img", ".img.bz2"}


@dataclass(slots=True)
class GeneratedPluginPreview:
    name: str
    slug: str
    page_url: str
    include: list[str]
    exclude: list[str]
    pattern: str
    regex: str
    examples: list[str]
    source: str


@dataclass(slots=True)
class GeneratedPluginReview:
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def normalize_pattern(url: str) -> str:
    output = (
        url.replace("x86_64", "ARCH_X64_TOKEN")
        .replace("amd64", "ARCH_AMD_TOKEN")
        .replace("aarch64", "ARCH_AARCH_TOKEN")
    )
    for pattern, token in TOKEN_PATTERNS:
        output = pattern.sub(token, output)
    output = (
        output.replace("ARCH_X64_TOKEN", "x86_64")
        .replace("ARCH_AMD_TOKEN", "amd64")
        .replace("ARCH_AARCH_TOKEN", "aarch64")
    )
    return output


def pattern_score(pattern: str, count: int) -> int:
    score = count
    lowered = pattern.lower()
    if ".iso" in lowered:
        score += 10
    if "x86_64" in lowered or "amd64" in lowered:
        score += 6
    if "desktop" in lowered or "workstation" in lowered or "netinst" in lowered:
        score += 3
    if "torrent" in lowered or ".sig" in lowered:
        score -= 8
    return score


def choose_pattern(links: list[str]) -> tuple[str, list[str]]:
    counts = Counter(normalize_pattern(link) for link in links)
    ranked = sorted(counts.items(), key=lambda item: (pattern_score(item[0], item[1]), item[1]), reverse=True)
    if not ranked:
        raise ValueError("No patterns could be extracted from the page")
    best = ranked[0][0]
    examples = [link for link in links if normalize_pattern(link) == best][:3]
    return best, examples


def pattern_to_regex(pattern: str) -> str:
    escaped = re.escape(pattern)
    escaped = escaped.replace("DATE", r"\d{4}\.\d{2}\.\d{2}")
    escaped = escaped.replace("VER", r"\d+(?:\.\d+)+")
    escaped = escaped.replace("NUM", r"\d+")
    return escaped


def render_plugin(name: str, page_url: str, regex: str, include: list[str], exclude: list[str]) -> str:
    include_repr = repr(include)
    exclude_repr = repr(exclude)
    return f'''from __future__ import annotations

import re

from distro_hunter.models import Candidate

NAME = "{name}"
PAGE_URL = "{page_url}"
LINK_REGEX = re.compile(r"{regex}", re.IGNORECASE)
INCLUDE = {include_repr}
EXCLUDE = {exclude_repr}


def discover(context) -> list[Candidate]:
    candidates: list[Candidate] = []
    for link in context.fetch_links(PAGE_URL):
        lowered = link.lower()
        if INCLUDE and not all(term.lower() in lowered for term in INCLUDE):
            continue
        if any(term.lower() in lowered for term in EXCLUDE):
            continue
        if LINK_REGEX.fullmatch(link):
            candidates.append(Candidate(url=link, source_page=PAGE_URL))
    return candidates
'''


def render_generated_test(plugin_path: Path, preview: GeneratedPluginPreview) -> str:
    examples_repr = repr(preview.examples)
    return f'''from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


PLUGIN_PATH = Path(r"{plugin_path}")
EXAMPLE_LINKS = {examples_repr}


class GeneratedPluginTests(unittest.TestCase):
    def test_discover_matches_example_links(self) -> None:
        spec = importlib.util.spec_from_file_location("{preview.slug}", PLUGIN_PATH)
        if spec is None or spec.loader is None:
            self.fail(f"Unable to load generated plugin: {{PLUGIN_PATH}}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class FakeContext:
            def fetch_links(self, url: str) -> list[str]:
                self_url = url
                return list(EXAMPLE_LINKS)

        candidates = module.discover(FakeContext())
        self.assertGreaterEqual(len(candidates), 1)


if __name__ == "__main__":
    unittest.main()
'''


def build_generated_plugin(
    *,
    context: DiscoveryContext,
    name: str,
    page_url: str,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> GeneratedPluginPreview:
    include = include or []
    exclude = exclude or ["torrent", ".sig", "sha256", "sha512"]
    links = filter_links(context.fetch_links(page_url), include=include, exclude=exclude)
    best_pattern, examples = choose_pattern(links)
    regex = pattern_to_regex(best_pattern)
    return GeneratedPluginPreview(
        name=name,
        slug=slugify(name),
        page_url=page_url,
        include=include,
        exclude=exclude,
        pattern=best_pattern,
        regex=regex,
        examples=examples,
        source=render_plugin(name, page_url, regex, include, exclude),
    )


def _filename_from_url(url: str) -> str:
    return Path(urlsplit(url).path).name


def _artifact_extension(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".img.bz2"):
        return ".img.bz2"
    return Path(lowered).suffix


def review_generated_plugin(
    preview: GeneratedPluginPreview,
    validated_candidates: list[Candidate] | None = None,
) -> GeneratedPluginReview:
    review = GeneratedPluginReview()
    urls = [candidate.url for candidate in validated_candidates] if validated_candidates is not None else list(preview.examples)
    filenames = [_filename_from_url(url) for url in urls]
    unique_filenames = sorted({name for name in filenames if name})
    hosts = sorted({urlsplit(url).netloc.lower() for url in urls if urlsplit(url).netloc})
    architectures = sorted(
        {
            label
            for url in urls
            for token, label in ARCH_HINTS
            if token in url.lower()
        }
    )
    extensions = sorted({_artifact_extension(name) for name in unique_filenames if name})

    if validated_candidates is None:
        review.suggestions.append("Run again with --validate to confirm the generated plugin still returns live candidates.")
    else:
        review.notes.append(f"Validation matched {len(validated_candidates)} candidate(s).")

    review.notes.append(f"Review sample size: {len(urls)} URL(s).")
    if hosts:
        review.notes.append(f"Hosts observed: {', '.join(hosts)}")
    if unique_filenames:
        review.notes.append(f"Unique filenames observed: {len(unique_filenames)}")

    if len(unique_filenames) > 3:
        review.warnings.append(
            f"Pattern currently matches {len(unique_filenames)} different filenames, so it may be broader than intended."
        )
    if len(architectures) > 1:
        review.warnings.append(
            f"Matches span multiple architectures ({', '.join(architectures)}); add include or exclude filters before enabling it."
        )
    unexpected_extensions = [extension for extension in extensions if extension not in RECOMMENDED_ARTIFACT_EXTENSIONS]
    if unexpected_extensions:
        review.warnings.append(
            f"Matches include non-image artifact types ({', '.join(unexpected_extensions)}); tighten the exclude list."
        )
    if len(hosts) > 1:
        review.suggestions.append(
            "If you only want one mirror family, add include filters or narrow the page URL before enabling the plugin."
        )
    if not preview.include:
        review.suggestions.append(
            "Consider adding one or two --include terms if the source page contains multiple editions or architectures."
        )
    if validated_candidates is not None and len(validated_candidates) > len(unique_filenames) and unique_filenames:
        review.notes.append(
            f"Validation looks mirror-heavy: {len(validated_candidates)} matches collapse to {len(unique_filenames)} unique filename(s)."
        )
    return review


def validate_generated_plugin(preview: GeneratedPluginPreview, context: DiscoveryContext) -> list[Candidate]:
    namespace: dict[str, object] = {}
    exec(preview.source, namespace)
    module = SimpleNamespace(**namespace)
    candidates = module.discover(context)
    if not candidates:
        raise ValueError("Generated plugin validation returned no candidates")
    return candidates


def write_generated_plugin(preview: GeneratedPluginPreview, output_dir: Path) -> Path:
    output = ensure_directory(output_dir) / f"{preview.slug}.py"
    output.write_text(preview.source, encoding="utf-8")
    return output


def write_generated_test(preview: GeneratedPluginPreview, plugin_path: Path, test_output_dir: Path) -> Path:
    output = ensure_directory(test_output_dir) / f"test_{preview.slug}.py"
    output.write_text(render_generated_test(plugin_path, preview), encoding="utf-8")
    return output


def generate_plugin(
    *,
    context: DiscoveryContext,
    name: str,
    page_url: str,
    output_dir: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Path:
    preview = build_generated_plugin(
        context=context,
        name=name,
        page_url=page_url,
        include=include,
        exclude=exclude,
    )
    return write_generated_plugin(preview, output_dir)
