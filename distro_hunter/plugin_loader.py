from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from distro_hunter.config import Settings
from distro_hunter.models import Candidate
from distro_hunter.plugin_metadata import PluginMetadata, infer_plugin_metadata
from distro_hunter.utils import slugify
from distro_hunter.web import WebClient, normalize_link


class DiscoveryContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.web = WebClient(
            user_agent=settings.download.user_agent,
            timeout_seconds=settings.download.timeout_seconds,
            retry_attempts=settings.download.retry_attempts,
            retry_backoff_seconds=settings.download.retry_backoff_seconds,
            page_cache_dir=settings.download.page_cache_dir,
            page_cache_ttl_seconds=settings.download.page_cache_ttl_seconds,
        )

    def fetch_text(self, url: str) -> str:
        return self.web.fetch_text(url)

    def fetch_links(self, url: str) -> list[str]:
        return self.web.fetch_links(url)

    def normalize_url(self, base_url: str, link: str) -> str:
        return normalize_link(base_url, link)

    def make_candidate(self, **kwargs: object) -> Candidate:
        return Candidate(**kwargs)


@dataclass(slots=True)
class PluginSpec:
    slug: str
    name: str
    module: ModuleType
    ventoy_subdir: str | None = None
    metadata: PluginMetadata | None = None

    def discover(self, context: DiscoveryContext) -> list[Candidate]:
        candidates = self.module.discover(context)
        if not isinstance(candidates, list):
            raise TypeError(f"Plugin {self.slug} returned {type(candidates)!r}, expected list")
        return candidates

    def resolved_metadata(self) -> PluginMetadata:
        return self.metadata or infer_plugin_metadata(self.slug, self.module)


def _load_builtin(name: str) -> ModuleType:
    return importlib.import_module(f"distro_hunter.plugins.{name}")


def _load_external_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load plugin file: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_spec(module: ModuleType, fallback_slug: str) -> PluginSpec:
    name = getattr(module, "NAME", fallback_slug.replace("_", " ").title())
    slug = slugify(getattr(module, "SLUG", fallback_slug))
    if not hasattr(module, "discover"):
        raise AttributeError(f"Plugin {slug} is missing a discover(context) function")
    return PluginSpec(
        slug=slug,
        name=name,
        module=module,
        ventoy_subdir=getattr(module, "VENTOY_SUBDIR", None),
        metadata=infer_plugin_metadata(slug, module),
    )


def load_plugins(settings: Settings) -> list[PluginSpec]:
    plugins: list[PluginSpec] = []
    for builtin in settings.plugins.builtin:
        module = _load_builtin(builtin)
        plugins.append(_build_spec(module, builtin))

    for directory in settings.plugins.directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module = _load_external_module(path)
            plugins.append(_build_spec(module, path.stem))
    return plugins
