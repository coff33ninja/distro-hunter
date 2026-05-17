from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from distro_hunter.utils import slugify


PLUGIN_PROFILES: dict[str, list[str]] = {
    "desktop": [
        "ubuntu_lts",
        "ubuntu_latest",
        "fedora_workstation",
        "fedora_kde",
        "fedora_xfce",
        "fedora_cinnamon",
        "linuxmint_cinnamon",
        "linuxmint_mate",
        "linuxmint_xfce",
        "kubuntu_lts",
        "lubuntu_lts",
        "xubuntu_lts",
        "ubuntu_mate_lts",
        "ubuntu_budgie_lts",
        "ubuntu_cinnamon_lts",
        "ubuntu_studio_lts",
        "zorin_core",
        "zorin_education",
        "zorin_lite",
        "manjaro_gnome",
        "manjaro_kde",
        "manjaro_xfce",
        "nixos_graphical",
        "opensuse_tumbleweed_gnome",
        "opensuse_tumbleweed_kde",
        "opensuse_tumbleweed_xfce",
        "nobara_official",
        "nobara_kde",
        "fydeos_pc_modern",
        "fydeos_pc_slim",
        "fydeos_pc_amd",
    ],
    "server": [
        "debian_netinst",
        "ubuntu_server_lts",
        "ubuntu_server_latest",
        "rocky_minimal",
        "rocky_boot",
        "rocky_dvd",
        "opensuse_tumbleweed_net",
        "opensuse_microos",
        "nixos_minimal",
        "archlinux",
        "alpine_standard",
    ],
    "arm": [
        "fedora_i3_aarch64",
        "fedora_kde_aarch64",
        "fedora_lxqt_aarch64",
        "fedora_workstation_aarch64",
        "fedora_xfce_aarch64",
        "pop_os_arm",
        "pop_os_arm_nvidia",
    ],
    "gaming": [
        "chimeraos",
        "steamos_recovery",
        "garuda_dr460nized",
        "garuda_dr460nized_gaming",
        "nobara_steam_handheld",
        "nobara_steam_htpc",
        "nobara_official",
        "nobara_kde",
    ],
    "minimal": [
        "archlinux",
        "alpine_standard",
        "debian_netinst",
        "kali_netinst",
        "nixos_minimal",
        "opensuse_tumbleweed_net",
        "opensuse_microos",
        "rocky_minimal",
        "systemrescue",
        "rocky_boot",
        "ubuntu_server_lts",
        "ubuntu_server_latest",
    ],
}


@dataclass(slots=True)
class PluginOverrideSettings:
    disabled_hosts: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    forced_urls: list[str] = field(default_factory=list)
    priority_boost: int = 0


@dataclass(slots=True)
class PluginSettings:
    builtin: list[str] = field(
        default_factory=lambda: [
            "archlinux",
            "almalinux_gnome",
            "alpine_standard",
            "chimeraos",
            "debian_live_cinnamon",
            "debian_live_debian_junior",
            "debian_live_gnome",
            "debian_live_kde",
            "debian_live_lxde",
            "debian_live_lxqt",
            "debian_live_mate",
            "debian_live_standard",
            "debian_live_xfce",
            "debian_netinst",
            "edubuntu_lts",
            "endeavouros",
            "fedora_budgie",
            "fedora_cinnamon",
            "fedora_i3",
            "fedora_i3_aarch64",
            "fedora_kde",
            "fedora_kde_aarch64",
            "fedora_lxqt",
            "fedora_lxqt_aarch64",
            "fedora_mate_compiz",
            "fedora_sway",
            "fedora_workstation",
            "fedora_workstation_aarch64",
            "fedora_xfce",
            "fedora_xfce_aarch64",
            "fydeos_pc_amd",
            "fydeos_pc_modern",
            "fydeos_pc_slim",
            "garuda_cinnamon",
            "garuda_dr460nized",
            "garuda_dr460nized_gaming",
            "garuda_gnome",
            "garuda_hyprland",
            "garuda_i3",
            "garuda_kde_lite",
            "garuda_mokka",
            "garuda_sway",
            "garuda_xfce",
            "kali_installer",
            "kali_netinst",
            "kali_purple_installer",
            "kali_weekly_installer",
            "kubuntu_lts",
            "linuxmint_cinnamon",
            "linuxmint_edge",
            "linuxmint_mate",
            "linuxmint_xfce",
            "lubuntu_lts",
            "lmde_cinnamon",
            "manjaro_gnome",
            "manjaro_kde",
            "manjaro_xfce",
            "nixos_minimal",
            "nixos_graphical",
            "nobara_kde",
            "nobara_official",
            "nobara_steam_handheld",
            "nobara_steam_htpc",
            "opensuse_microos",
            "opensuse_tumbleweed_dvd",
            "opensuse_tumbleweed_gnome",
            "opensuse_tumbleweed_kde",
            "opensuse_tumbleweed_net",
            "opensuse_tumbleweed_rescue",
            "opensuse_tumbleweed_xfce",
            "rocky_boot",
            "rocky_dvd",
            "rocky_minimal",
            "pop_os",
            "pop_os_arm",
            "pop_os_arm_nvidia",
            "pop_os_nvidia",
            "steamos_recovery",
            "systemrescue",
            "ubuntu_budgie_lts",
            "ubuntu_cinnamon_lts",
            "ubuntu_latest",
            "ubuntu_lts",
            "ubuntu_mate_lts",
            "ubuntu_server_latest",
            "ubuntu_server_lts",
            "ubuntu_studio_lts",
            "xubuntu_lts",
            "zorin_core",
            "zorin_education",
            "zorin_lite",
        ]
    )
    profiles: list[str] = field(default_factory=list)
    directories: list[Path] = field(default_factory=lambda: [Path("user_plugins")])
    overrides: dict[str, PluginOverrideSettings] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadSettings:
    download_dir: Path = Path("downloads")
    page_cache_dir: Path = Path("cache/pages")
    page_cache_ttl_seconds: int = 3600
    discovery_workers: int = 8
    verify_checksums: bool = True
    require_checksums: bool = False
    aria2_path: Path | None = None
    prefer_aria2: bool = True
    prefer_torrent: bool = False
    protect_filename_collisions: bool = True
    retention_keep_latest: int = 0
    decompress_bz2: bool = True
    connections_per_server: int = 8
    split: int = 8
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    mirror_backoff_base_seconds: int = 1800
    mirror_backoff_cap_seconds: int = 21600
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )


@dataclass(slots=True)
class VentoySettings:
    enabled: bool = True
    volume_labels: list[str] = field(default_factory=lambda: ["Ventoy"])
    marker_paths: list[str] = field(default_factory=lambda: ["ventoy"])
    destination_subdir: str = "ISO/Linux"
    copy_extensions: list[str] = field(default_factory=lambda: [".iso", ".img"])
    organize_by_plugin: bool = True
    manual_subdir: str = "manual"
    manual_sources: list["ManualSourceRule"] = field(default_factory=list)
    prune_removed: bool = False


@dataclass(slots=True)
class ManualSourceRule:
    pattern: str
    subdir: str | None = None
    family: str | None = None
    architecture: str | None = None
    edition_type: str | None = None
    source_kind: str | None = "manual"


@dataclass(slots=True)
class GeneratorSettings:
    output_dir: Path = Path("user_plugins")
    test_output_dir: Path = Path("tests/generated")


@dataclass(slots=True)
class LoggingSettings:
    run_log_file: Path | None = Path("logs/distro_hunter.log")
    mirror_failures_file: Path | None = Path("logs/mirror_failures.log")
    jsonl_log_file: Path | None = Path("logs/distro_hunter.jsonl")


@dataclass(slots=True)
class Settings:
    config_path: Path
    state_file: Path
    plugins: PluginSettings
    download: DownloadSettings
    ventoy: VentoySettings
    generator: GeneratorSettings
    logging: LoggingSettings


def _resolve_path(base_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _resolve_aria2_path(base_dir: Path, value: str | None) -> Path | None:
    text = _optional_text(value)
    if text:
        raw_path = Path(text)
        looks_like_command = raw_path.parent == Path(".") and not raw_path.drive and "\\" not in text and "/" not in text
        if looks_like_command:
            command_path = shutil.which(text)
            if command_path:
                return Path(command_path).resolve()
        else:
            configured_path = _resolve_path(base_dir, text)
            if configured_path and configured_path.exists():
                return configured_path.resolve()

    discovered_command = shutil.which("aria2c")
    if discovered_command:
        return Path(discovered_command).resolve()

    candidate_paths: list[Path] = [
        (base_dir / "tools" / "aria2" / "aria2c.exe").resolve(),
        (base_dir / "tools" / "aria2c.exe").resolve(),
        Path(r"C:\Tools\aria2\aria2c.exe"),
    ]

    program_files = _optional_text(os.environ.get("ProgramFiles"))
    if program_files:
        candidate_paths.append(Path(program_files) / "aria2" / "aria2c.exe")

    program_files_x86 = _optional_text(os.environ.get("ProgramFiles(x86)"))
    if program_files_x86:
        candidate_paths.append(Path(program_files_x86) / "aria2" / "aria2c.exe")

    local_app_data = _optional_text(os.environ.get("LOCALAPPDATA"))
    if local_app_data:
        candidate_paths.append(Path(local_app_data) / "Programs" / "aria2" / "aria2c.exe")

    for candidate in candidate_paths:
        if candidate.exists():
            return candidate.resolve()

    from distro_hunter.bootstrap_aria2 import bootstrap_aria2

    bootstrapped = bootstrap_aria2(base_dir)
    if bootstrapped:
        return bootstrapped.resolve()
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _expand_plugin_profiles(builtin: list[str], profiles: list[str]) -> list[str]:
    expanded = list(builtin)
    for profile in profiles:
        normalized = slugify(profile)
        members = PLUGIN_PROFILES.get(normalized)
        if members is None:
            raise ValueError(f"Unknown plugin profile: {profile}")
        expanded.extend(members)
    return _dedupe_preserving_order(expanded)


def load_settings(config_path: str | Path) -> Settings:
    config_file = Path(config_path).resolve()
    base_dir = config_file.parent

    data = json.loads(config_file.read_text(encoding="utf-8"))

    plugin_data = data.get("plugins", {})
    download_data = data.get("download", {})
    ventoy_data = data.get("ventoy", {})
    generator_data = data.get("generator", {})
    logging_data = data.get("logging", {})

    requested_profiles = [slugify(entry) for entry in plugin_data.get("profiles", [])]
    builtin_plugins = plugin_data.get("builtin")
    if builtin_plugins is None:
        builtin_plugins = [] if requested_profiles else PluginSettings().builtin

    raw_overrides = plugin_data.get("overrides", {})
    overrides: dict[str, PluginOverrideSettings] = {}
    for plugin_slug, override in raw_overrides.items():
        if not isinstance(override, dict):
            continue
        overrides[slugify(plugin_slug)] = PluginOverrideSettings(
            disabled_hosts=[str(entry).lower() for entry in override.get("disabled_hosts", [])],
            include=[str(entry).lower() for entry in override.get("include", [])],
            exclude=[str(entry).lower() for entry in override.get("exclude", [])],
            forced_urls=[str(entry) for entry in override.get("forced_urls", [])],
            priority_boost=int(override.get("priority_boost", 0)),
        )

    plugins = PluginSettings(
        builtin=_expand_plugin_profiles(list(builtin_plugins), requested_profiles),
        profiles=requested_profiles,
        directories=[
            _resolve_path(base_dir, entry) or Path(entry)
            for entry in plugin_data.get("directories", ["user_plugins"])
        ],
        overrides=overrides,
    )

    manual_sources: list[ManualSourceRule] = []
    for entry in ventoy_data.get("manual_sources", []):
        if not isinstance(entry, dict):
            continue
        pattern = _optional_text(entry.get("pattern"))
        if not pattern:
            continue
        manual_sources.append(
            ManualSourceRule(
                pattern=pattern,
                subdir=_optional_text(entry.get("subdir")),
                family=_optional_text(entry.get("family")),
                architecture=_optional_text(entry.get("architecture")),
                edition_type=_optional_text(entry.get("edition_type")),
                source_kind=_optional_text(entry.get("source_kind")) or "manual",
            )
        )

    download = DownloadSettings(
        download_dir=_resolve_path(base_dir, download_data.get("download_dir")) or (base_dir / "downloads"),
        page_cache_dir=_resolve_path(base_dir, download_data.get("page_cache_dir")) or (base_dir / "cache" / "pages"),
        page_cache_ttl_seconds=download_data.get("page_cache_ttl_seconds", 3600),
        discovery_workers=download_data.get("discovery_workers", 8),
        verify_checksums=download_data.get("verify_checksums", True),
        require_checksums=download_data.get("require_checksums", False),
        aria2_path=_resolve_aria2_path(base_dir, download_data.get("aria2_path")),
        prefer_aria2=download_data.get("prefer_aria2", True),
        prefer_torrent=download_data.get("prefer_torrent", False),
        protect_filename_collisions=download_data.get("protect_filename_collisions", True),
        retention_keep_latest=download_data.get("retention_keep_latest", 0),
        decompress_bz2=download_data.get("decompress_bz2", True),
        connections_per_server=download_data.get("connections_per_server", 8),
        split=download_data.get("split", 8),
        timeout_seconds=download_data.get("timeout_seconds", 30),
        retry_attempts=download_data.get("retry_attempts", 3),
        retry_backoff_seconds=download_data.get("retry_backoff_seconds", 1.0),
        mirror_backoff_base_seconds=download_data.get("mirror_backoff_base_seconds", 1800),
        mirror_backoff_cap_seconds=download_data.get("mirror_backoff_cap_seconds", 21600),
        user_agent=download_data.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ),
    )

    ventoy = VentoySettings(
        enabled=ventoy_data.get("enabled", True),
        volume_labels=ventoy_data.get("volume_labels", ["Ventoy"]),
        marker_paths=ventoy_data.get("marker_paths", ["ventoy"]),
        destination_subdir=ventoy_data.get("destination_subdir", "ISO/Linux"),
        copy_extensions=ventoy_data.get("copy_extensions", [".iso", ".img"]),
        organize_by_plugin=ventoy_data.get("organize_by_plugin", True),
        manual_subdir=ventoy_data.get("manual_subdir", "manual"),
        manual_sources=manual_sources,
        prune_removed=ventoy_data.get("prune_removed", False),
    )

    generator = GeneratorSettings(
        output_dir=_resolve_path(base_dir, generator_data.get("output_dir")) or (base_dir / "user_plugins"),
        test_output_dir=_resolve_path(base_dir, generator_data.get("test_output_dir")) or (base_dir / "tests" / "generated"),
    )

    logging = LoggingSettings(
        run_log_file=_resolve_path(base_dir, logging_data.get("run_log_file")) or (base_dir / "logs" / "distro_hunter.log"),
        mirror_failures_file=_resolve_path(base_dir, logging_data.get("mirror_failures_file"))
        or (base_dir / "logs" / "mirror_failures.log"),
        jsonl_log_file=_resolve_path(base_dir, logging_data.get("jsonl_log_file")) or (base_dir / "logs" / "distro_hunter.jsonl"),
    )

    return Settings(
        config_path=config_file,
        state_file=_resolve_path(base_dir, data.get("state_file")) or (base_dir / "state" / "distro_hunter_state.json"),
        plugins=plugins,
        download=download,
        ventoy=ventoy,
        generator=generator,
        logging=logging,
    )
