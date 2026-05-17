from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


ARCH_ALIASES = {
    "arm": "arm64",
    "x64": "x86_64",
    "x86-64": "x86_64",
}
ARCH_SUFFIXES = {"aarch64", "amd64", "arm64", "x86_64", *ARCH_ALIASES}
FAMILY_RULES = [
    ("pop_os", "pop-os"),
    ("linuxmint", "linuxmint"),
    ("opensuse", "opensuse"),
]
DESKTOP_DEFAULT_FAMILIES = {"edubuntu", "kubuntu", "lubuntu", "xubuntu"}


@dataclass(slots=True, frozen=True)
class PluginMetadata:
    family: str
    architecture: str | None = None
    edition_type: str | None = None
    source_kind: str | None = None


def _normalize_segment(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.lower().replace("_", "-")).strip("-")
    return cleaned or None


def _normalize_architecture(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower().replace("-", "_")
    lowered = ARCH_ALIASES.get(lowered, lowered)
    cleaned = re.sub(r"[^a-z0-9_]+", "_", lowered).strip("_")
    return cleaned or None


def metadata_from_fields(
    *,
    family: str | None,
    architecture: str | None = None,
    edition_type: str | None = None,
    source_kind: str | None = None,
) -> PluginMetadata:
    return PluginMetadata(
        family=_normalize_segment(family) or "general",
        architecture=_normalize_architecture(architecture),
        edition_type=_normalize_segment(edition_type),
        source_kind=_normalize_segment(source_kind),
    )


def _explicit_metadata(module: ModuleType | None) -> dict[str, object]:
    if module is None:
        return {}
    metadata = getattr(module, "METADATA", {})
    return metadata if isinstance(metadata, dict) else {}


def _slug_family_and_tokens(plugin_slug: str) -> tuple[str, list[str]]:
    slug = plugin_slug.casefold()
    for prefix, family_name in FAMILY_RULES:
        if slug == prefix or slug.startswith(prefix + "_"):
            remainder = slug[len(prefix) :].lstrip("_")
            return family_name, [token for token in remainder.split("_") if token]

    parts = slug.split("_", 1)
    family = _normalize_segment(parts[0]) or "general"
    remainder = parts[1] if len(parts) > 1 else ""
    return family, [token for token in remainder.split("_") if token]


def _infer_architecture(tokens: list[str]) -> str | None:
    for token in reversed(tokens):
        normalized = _normalize_architecture(token)
        if normalized in {"aarch64", "amd64", "arm64", "x86_64"}:
            return normalized
    return None


def _infer_edition_type(family: str, tokens: list[str]) -> str | None:
    filtered = [token for token in tokens if _normalize_architecture(token) not in {"aarch64", "amd64", "arm64", "x86_64"}]
    if filtered and filtered[-1] in {"latest", "lts"}:
        filtered = filtered[:-1]

    if family == "ubuntu":
        if not filtered:
            filtered = ["desktop"]
        elif filtered[0] == "server":
            filtered = ["server"]
    elif family in DESKTOP_DEFAULT_FAMILIES and not filtered:
        filtered = ["desktop"]
    elif family == "debian":
        if filtered[:1] == ["live"]:
            filtered = ["live"]
        elif filtered[:1] == ["netinst"]:
            filtered = ["installer"]
    elif family == "steamos" and not filtered:
        filtered = ["recovery"]

    if not filtered:
        return None
    return _normalize_segment("-".join(filtered))


def _infer_source_kind(module: ModuleType | None) -> str | None:
    if module is None:
        return None
    explicit = _normalize_segment(getattr(module, "SOURCE_KIND", None))
    if explicit:
        return explicit

    for attr in ("API_URL",):
        value = getattr(module, attr, None)
        if isinstance(value, str) and value:
            return "api"

    for attr in ("CATEGORY_URL",):
        value = getattr(module, attr, None)
        if isinstance(value, str) and value:
            return "api" if value.lower().endswith(".json") else "html"

    for attr in ("PAGE_URL", "BASE_URL", "DOWNLOAD_PAGE_URL"):
        value = getattr(module, attr, None)
        if isinstance(value, str) and value:
            return "html"

    for attr in ("DOWNLOAD_URL",):
        value = getattr(module, attr, None)
        if isinstance(value, str) and value:
            return "direct"
    return None


def infer_plugin_metadata(plugin_slug: str, module: ModuleType | None = None) -> PluginMetadata:
    explicit = _explicit_metadata(module)
    family, tokens = _slug_family_and_tokens(plugin_slug)
    return metadata_from_fields(
        family=explicit.get("family") or getattr(module, "FAMILY", None) or family,
        architecture=explicit.get("architecture") or getattr(module, "ARCHITECTURE", None) or _infer_architecture(tokens),
        edition_type=explicit.get("edition_type") or getattr(module, "EDITION_TYPE", None) or _infer_edition_type(family, tokens),
        source_kind=explicit.get("source_kind") or getattr(module, "SOURCE_KIND", None) or _infer_source_kind(module),
    )


def metadata_subdir(metadata: PluginMetadata) -> Path:
    family = _normalize_segment(metadata.family) or "general"
    edition_type = _normalize_segment(metadata.edition_type)
    if edition_type:
        return Path(family, edition_type)
    return Path(family)
