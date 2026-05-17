from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace


@dataclass(frozen=True)
class ExpectedCandidate:
    url: str
    filename: str | None
    version: str | None
    arch: str | None
    source_page: str | None
    priority: int
    torrent_url: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class PluginDiscoveryCase:
    label: str
    module_name: str
    link_pages: dict[str, list[str]] = field(default_factory=dict)
    text_pages: dict[str, str] = field(default_factory=dict)
    final_urls: dict[str, str] = field(default_factory=dict)
    expected: tuple[ExpectedCandidate, ...] = ()


class FixtureContext:
    def __init__(
        self,
        *,
        link_pages: dict[str, list[str]] | None = None,
        text_pages: dict[str, str] | None = None,
        final_urls: dict[str, str] | None = None,
    ) -> None:
        self._link_pages = link_pages or {}
        self._text_pages = text_pages or {}
        self.web = SimpleNamespace(inspect_remote_file=self._inspect_remote_file)
        self._final_urls = final_urls or {}

    def fetch_links(self, url: str) -> list[str]:
        return list(self._link_pages.get(url, []))

    def fetch_text(self, url: str) -> str:
        return self._text_pages[url]

    def normalize_url(self, base_url: str, link: str) -> str:
        return base_url.rstrip("/") + "/" + link.lstrip("/")

    def _inspect_remote_file(self, url: str):
        return {}, self._final_urls.get(url, url)


def _candidate(
    *,
    url: str,
    filename: str | None,
    version: str | None,
    arch: str | None,
    source_page: str | None,
    priority: int,
    torrent_url: str | None = None,
    notes: str | None = None,
) -> ExpectedCandidate:
    return ExpectedCandidate(
        url=url,
        filename=filename,
        version=version,
        arch=arch,
        source_page=source_page,
        priority=priority,
        torrent_url=torrent_url,
        notes=notes,
    )


def _mint_case(
    *,
    label: str,
    module_name: str,
    page_url: str,
    filename: str,
    version: str,
    priority: int,
) -> PluginDiscoveryCase:
    link_pages = {
        page_url: [
            f"ftp://pub.linuxmint.io/{filename}",
            f"https://other.example/downloads/{filename}",
            f"https://www.mirrorservice.org/sites/linuxmint/{filename}",
            f"https://mirrors.kernel.org/linuxmint/{filename}",
            f"https://pub.linuxmint.io/{filename}",
            f"https://pub.linuxmint.io/{filename}.sig",
        ]
    }
    torrent_url = f"https://www.linuxmint.com/torrents/{filename}.torrent"
    expected = (
        _candidate(
            url=f"https://pub.linuxmint.io/{filename}",
            filename=filename,
            version=version,
            arch="amd64",
            source_page=page_url,
            torrent_url=torrent_url,
            priority=priority,
        ),
        _candidate(
            url=f"https://mirrors.kernel.org/linuxmint/{filename}",
            filename=filename,
            version=version,
            arch="amd64",
            source_page=page_url,
            torrent_url=torrent_url,
            priority=priority,
        ),
        _candidate(
            url=f"https://www.mirrorservice.org/sites/linuxmint/{filename}",
            filename=filename,
            version=version,
            arch="amd64",
            source_page=page_url,
            torrent_url=torrent_url,
            priority=priority,
        ),
    )
    return PluginDiscoveryCase(
        label=label,
        module_name=module_name,
        link_pages=link_pages,
        expected=expected,
    )


def _fedora_case(
    *,
    label: str,
    module_name: str,
    page_url: str,
    links: list[str],
    expected: ExpectedCandidate,
) -> PluginDiscoveryCase:
    return PluginDiscoveryCase(
        label=label,
        module_name=module_name,
        link_pages={page_url: links},
        expected=(expected,),
    )


def _ubuntu_regex_case(
    *,
    label: str,
    module_name: str,
    page_url: str,
    iso_url: str,
    version: str,
    priority: int,
) -> PluginDiscoveryCase:
    filename = iso_url.rsplit("/", 1)[-1]
    return PluginDiscoveryCase(
        label=label,
        module_name=module_name,
        link_pages={page_url: [iso_url, iso_url + ".torrent", iso_url + ".zsync"]},
        expected=(
            _candidate(
                url=iso_url,
                filename=filename,
                version=version,
                arch="amd64",
                source_page=page_url,
                priority=priority,
                torrent_url=iso_url + ".torrent",
            ),
        ),
    )


def _ubuntu_thank_you_case(
    *,
    label: str,
    module_name: str,
    page_url: str,
    page_links: list[str],
    thank_you_pages: dict[str, list[str]],
    expected: tuple[ExpectedCandidate, ...],
) -> PluginDiscoveryCase:
    link_pages = {page_url: page_links, **thank_you_pages}
    return PluginDiscoveryCase(
        label=label,
        module_name=module_name,
        link_pages=link_pages,
        expected=expected,
    )


def _garuda_case(
    *,
    label: str,
    module_name: str,
    flavor: str,
    final_filename: str,
    priority: int,
) -> PluginDiscoveryCase:
    category_url = "https://forum.garudalinux.org/c/announcements/iso-releases/l/latest.json"
    topic_url = "https://forum.garudalinux.org/t/iso-release-2026-04-28/12345.json"
    latest_url = f"https://iso.builds.garudalinux.org/iso/latest/garuda/{flavor}/latest.iso?r2=1"
    final_url = f"https://iso.builds.garudalinux.org/iso/2026/04/{final_filename}"
    text_pages = {
        category_url: json.dumps(
            {
                "topic_list": {
                    "topics": [
                        {
                            "title": "ISO Release: 2026.04.28",
                            "slug": "iso-release-2026-04-28",
                            "id": 12345,
                        }
                    ]
                }
            }
        ),
        topic_url: json.dumps(
            {
                "post_stream": {
                    "posts": [
                        {
                            "cooked": f'<a href="{latest_url}">Download</a>',
                        }
                    ]
                }
            }
        ),
    }
    expected = (
        _candidate(
            url=latest_url,
            filename=final_filename,
            version="2026.04.28",
            arch="x86_64",
            source_page=topic_url,
            priority=priority,
        ),
    )
    return PluginDiscoveryCase(
        label=label,
        module_name=module_name,
        text_pages=text_pages,
        final_urls={latest_url: final_url},
        expected=expected,
    )


def _pop_case(
    *,
    label: str,
    module_name: str,
    api_url: str,
    iso_url: str,
    version: str,
    arch: str,
    priority: int,
    notes: str | None = None,
) -> PluginDiscoveryCase:
    page_url = "https://system76.com/pop/download/"
    filename = iso_url.rsplit("/", 1)[-1]
    return PluginDiscoveryCase(
        label=label,
        module_name=module_name,
        text_pages={
            api_url: json.dumps(
                {
                    "url": iso_url,
                    "version": version,
                }
            )
        },
        expected=(
            _candidate(
                url=iso_url,
                filename=filename,
                version=version,
                arch=arch,
                source_page=page_url,
                priority=priority,
                notes=notes,
            ),
        ),
    )


FEDORA_CASES = (
    _fedora_case(
        label="Fedora Workstation x86_64",
        module_name="distro_hunter.plugins.fedora_workstation",
        page_url="https://fedoraproject.org/en/workstation/download/",
        links=[
            "https://download.example.org/Fedora-Workstation-Live-43-1.6.aarch64.iso",
            "https://download.example.org/Fedora-Workstation-Live-43-1.6.x86_64.iso",
        ],
        expected=_candidate(
            url="https://download.example.org/Fedora-Workstation-Live-43-1.6.x86_64.iso",
            filename="Fedora-Workstation-Live-43-1.6.x86_64.iso",
            version="43-1.6",
            arch="x86_64",
            source_page="https://fedoraproject.org/en/workstation/download/",
            priority=5,
        ),
    ),
    _fedora_case(
        label="Fedora KDE ARM64",
        module_name="distro_hunter.plugins.fedora_kde_aarch64",
        page_url="https://fedoraproject.org/en/kde/download/",
        links=[
            "https://download.example.org/Fedora-KDE-Desktop-Live-43-1.6.x86_64.iso",
            "https://download.example.org/Fedora-KDE-Desktop-Live-43-1.6.aarch64.iso",
        ],
        expected=_candidate(
            url="https://download.example.org/Fedora-KDE-Desktop-Live-43-1.6.aarch64.iso",
            filename="Fedora-KDE-Desktop-Live-43-1.6.aarch64.iso",
            version="43-1.6",
            arch="aarch64",
            source_page="https://fedoraproject.org/en/kde/download/",
            priority=4,
        ),
    ),
    _fedora_case(
        label="Fedora Xfce x86_64",
        module_name="distro_hunter.plugins.fedora_xfce",
        page_url="https://fedoraproject.org/en/spins/xfce/download/",
        links=[
            "https://download.example.org/Fedora-Xfce-Live-43-1.6.x86_64.iso",
            "https://download.example.org/Fedora-Xfce-Live-43-1.6.aarch64.iso",
        ],
        expected=_candidate(
            url="https://download.example.org/Fedora-Xfce-Live-43-1.6.x86_64.iso",
            filename="Fedora-Xfce-Live-43-1.6.x86_64.iso",
            version="43-1.6",
            arch="x86_64",
            source_page="https://fedoraproject.org/en/spins/xfce/download/",
            priority=5,
        ),
    ),
)

UBUNTU_CASES = (
    _ubuntu_thank_you_case(
        label="Ubuntu Desktop LTS",
        module_name="distro_hunter.plugins.ubuntu_lts",
        page_url="https://ubuntu.com/download/desktop",
        page_links=[
            "https://ubuntu.com/download/desktop/thank-you?version=25.10&architecture=amd64",
            "https://ubuntu.com/download/desktop/thank-you?version=24.04.4&architecture=amd64&lts=true",
        ],
        thank_you_pages={
            "https://ubuntu.com/download/desktop/thank-you?version=25.10&architecture=amd64": [
                "https://releases.ubuntu.com/25.10/ubuntu-25.10-desktop-amd64.iso"
            ],
            "https://ubuntu.com/download/desktop/thank-you?version=24.04.4&architecture=amd64&lts=true": [
                "https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-desktop-amd64.iso"
            ],
        },
        expected=(
            _candidate(
                url="https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-desktop-amd64.iso",
                filename="ubuntu-24.04.4-desktop-amd64.iso",
                version="24.04.4",
                arch="amd64",
                source_page="https://ubuntu.com/download/desktop/thank-you?version=24.04.4&architecture=amd64&lts=true",
                priority=7,
            ),
        ),
    ),
    _ubuntu_thank_you_case(
        label="Ubuntu Desktop Latest",
        module_name="distro_hunter.plugins.ubuntu_latest",
        page_url="https://ubuntu.com/download/desktop",
        page_links=[
            "https://ubuntu.com/download/desktop/thank-you?version=25.10&architecture=amd64",
            "https://ubuntu.com/download/desktop/thank-you?version=24.04.4&architecture=amd64&lts=true",
        ],
        thank_you_pages={
            "https://ubuntu.com/download/desktop/thank-you?version=25.10&architecture=amd64": [
                "https://releases.ubuntu.com/25.10/ubuntu-25.10-desktop-amd64.iso"
            ],
            "https://ubuntu.com/download/desktop/thank-you?version=24.04.4&architecture=amd64&lts=true": [
                "https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-desktop-amd64.iso"
            ],
        },
        expected=(
            _candidate(
                url="https://releases.ubuntu.com/25.10/ubuntu-25.10-desktop-amd64.iso",
                filename="ubuntu-25.10-desktop-amd64.iso",
                version="25.10",
                arch="amd64",
                source_page="https://ubuntu.com/download/desktop/thank-you?version=25.10&architecture=amd64",
                priority=6,
            ),
            _candidate(
                url="https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-desktop-amd64.iso",
                filename="ubuntu-24.04.4-desktop-amd64.iso",
                version="24.04.4",
                arch="amd64",
                source_page="https://ubuntu.com/download/desktop/thank-you?version=24.04.4&architecture=amd64&lts=true",
                priority=4,
            ),
        ),
    ),
    _ubuntu_thank_you_case(
        label="Ubuntu Server LTS",
        module_name="distro_hunter.plugins.ubuntu_server_lts",
        page_url="https://ubuntu.com/download/server",
        page_links=[
            "https://ubuntu.com/download/server/thank-you?version=25.10&architecture=amd64",
            "https://ubuntu.com/download/server/thank-you?version=24.04.4&architecture=amd64&lts=true",
        ],
        thank_you_pages={
            "https://ubuntu.com/download/server/thank-you?version=25.10&architecture=amd64": [
                "https://releases.ubuntu.com/25.10/ubuntu-25.10-live-server-amd64.iso"
            ],
            "https://ubuntu.com/download/server/thank-you?version=24.04.4&architecture=amd64&lts=true": [
                "https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-live-server-amd64.iso"
            ],
        },
        expected=(
            _candidate(
                url="https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-live-server-amd64.iso",
                filename="ubuntu-24.04.4-live-server-amd64.iso",
                version="24.04.4",
                arch="amd64",
                source_page="https://ubuntu.com/download/server/thank-you?version=24.04.4&architecture=amd64&lts=true",
                priority=7,
                torrent_url="https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-live-server-amd64.iso.torrent",
            ),
        ),
    ),
    _ubuntu_regex_case(
        label="Kubuntu LTS",
        module_name="distro_hunter.plugins.kubuntu_lts",
        page_url="https://cdimage.ubuntu.com/kubuntu/releases/24.04/release/",
        iso_url="https://cdimage.ubuntu.com/kubuntu/releases/24.04/release/kubuntu-24.04.4-desktop-amd64.iso",
        version="24.04.4",
        priority=5,
    ),
    _ubuntu_regex_case(
        label="Ubuntu Studio LTS",
        module_name="distro_hunter.plugins.ubuntu_studio_lts",
        page_url="https://cdimage.ubuntu.com/ubuntustudio/releases/24.04/release/",
        iso_url="https://cdimage.ubuntu.com/ubuntustudio/releases/24.04/release/ubuntustudio-24.04.4-dvd-amd64.iso",
        version="24.04.4",
        priority=5,
    ),
)

MINT_CASES = (
    _mint_case(
        label="Linux Mint Cinnamon",
        module_name="distro_hunter.plugins.linuxmint_cinnamon",
        page_url="https://linuxmint.com/edition.php?id=326",
        filename="linuxmint-22.3-cinnamon-64bit.iso",
        version="22.3",
        priority=5,
    ),
    _mint_case(
        label="Linux Mint MATE",
        module_name="distro_hunter.plugins.linuxmint_mate",
        page_url="https://linuxmint.com/edition.php?id=328",
        filename="linuxmint-22.3-mate-64bit.iso",
        version="22.3",
        priority=5,
    ),
    _mint_case(
        label="Linux Mint Xfce",
        module_name="distro_hunter.plugins.linuxmint_xfce",
        page_url="https://linuxmint.com/edition.php?id=327",
        filename="linuxmint-22.3-xfce-64bit.iso",
        version="22.3",
        priority=5,
    ),
    _mint_case(
        label="LMDE Cinnamon",
        module_name="distro_hunter.plugins.lmde_cinnamon",
        page_url="https://linuxmint.com/edition.php?id=325",
        filename="lmde-7-cinnamon-64bit.iso",
        version="7",
        priority=5,
    ),
    _mint_case(
        label="Linux Mint Edge",
        module_name="distro_hunter.plugins.linuxmint_edge",
        page_url="https://linuxmint.com/edition.php?id=314",
        filename="linuxmint-21.3-cinnamon-64bit-edge.iso",
        version="21.3-edge",
        priority=4,
    ),
)

GARUDA_CASES = (
    _garuda_case(
        label="Garuda Dr460nized",
        module_name="distro_hunter.plugins.garuda_dr460nized",
        flavor="dr460nized",
        final_filename="garuda-dr460nized-linux-zen-260428.iso",
        priority=6,
    ),
    _garuda_case(
        label="Garuda Dr460nized Gaming",
        module_name="distro_hunter.plugins.garuda_dr460nized_gaming",
        flavor="dr460nized-gaming",
        final_filename="garuda-dr460nized-gaming-linux-zen-260428.iso",
        priority=6,
    ),
    _garuda_case(
        label="Garuda GNOME",
        module_name="distro_hunter.plugins.garuda_gnome",
        flavor="gnome",
        final_filename="garuda-gnome-linux-zen-260428.iso",
        priority=5,
    ),
    _garuda_case(
        label="Garuda i3",
        module_name="distro_hunter.plugins.garuda_i3",
        flavor="i3",
        final_filename="garuda-i3-linux-zen-260428.iso",
        priority=4,
    ),
)

API_CASES = (
    _pop_case(
        label="Pop!_OS generic amd64",
        module_name="distro_hunter.plugins.pop_os",
        api_url="https://api.pop-os.org/builds/24.04/generic?arch=amd64",
        iso_url="https://iso.pop-os.org/24.04/amd64/intel/39/pop-os_24.04_amd64_intel_39.iso",
        version="24.04-39",
        arch="amd64",
        priority=6,
    ),
    _pop_case(
        label="Pop!_OS NVIDIA amd64",
        module_name="distro_hunter.plugins.pop_os_nvidia",
        api_url="https://api.pop-os.org/builds/24.04/nvidia?arch=amd64",
        iso_url="https://iso.pop-os.org/24.04/amd64/nvidia/39/pop-os_24.04_amd64_nvidia_39.iso",
        version="24.04-39",
        arch="amd64",
        priority=6,
        notes="NVIDIA image",
    ),
    _pop_case(
        label="Pop!_OS generic arm64",
        module_name="distro_hunter.plugins.pop_os_arm",
        api_url="https://api.pop-os.org/builds/24.04/generic?arch=arm64",
        iso_url="https://iso.pop-os.org/24.04/arm64/generic/39/pop-os_24.04_arm64_generic_39.iso",
        version="24.04-39",
        arch="arm64",
        priority=4,
    ),
    _pop_case(
        label="Pop!_OS NVIDIA arm64",
        module_name="distro_hunter.plugins.pop_os_arm_nvidia",
        api_url="https://api.pop-os.org/builds/24.04/nvidia?arch=arm64",
        iso_url="https://iso.pop-os.org/24.04/arm64/nvidia/39/pop-os_24.04_arm64_nvidia_39.iso",
        version="24.04-39",
        arch="arm64",
        priority=4,
        notes="ARM64 NVIDIA image",
    ),
)

FYDEOS_CASES = (
    PluginDiscoveryCase(
        label="FydeOS Intel Modern",
        module_name="distro_hunter.plugins.fydeos_pc_modern",
        link_pages={
            "https://fydeos.io/download/pc/intel-iris/": [
                "https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip",
                "https://drive.google.com/file/d/example/view",
            ]
        },
        text_pages={
            "https://fydeos.io/download/pc/intel-iris/": (
                '<h3>SHA-256 (FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip)</h3>'
                '<code id="hash">c69b8129113cecef93df276378eb9d06908207eb76f62f5910cc4a7431eeafb9</code>'
            )
        },
        expected=(
            _candidate(
                url="https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip",
                filename="FydeOS_for_PC_iris_v22.0-SP1-io.bin.zip",
                version="22.0-SP1",
                arch="x86_64",
                source_page="https://fydeos.io/download/pc/intel-iris/",
                priority=5,
                notes="Downloads the official FydeOS raw disk archive; Distro Hunter extracts the .bin.zip payload to a Ventoy-friendly .img",
            ),
        ),
    ),
    PluginDiscoveryCase(
        label="FydeOS Intel Slim",
        module_name="distro_hunter.plugins.fydeos_pc_slim",
        link_pages={
            "https://fydeos.io/download/pc/intel-slim/": [
                "https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_slim_v22.0-SP1-io.bin.zip",
                "https://www.icloud.com/example",
            ]
        },
        text_pages={
            "https://fydeos.io/download/pc/intel-slim/": (
                '<h3>SHA-256 (FydeOS_for_PC_slim_v22.0-SP1-io.bin.zip)</h3>'
                '<code id="hash">bfda79ff3bf7553f4d6d13b05abf484fef5ca25cb0a2b8b1be28d15927caeb0f</code>'
            )
        },
        expected=(
            _candidate(
                url="https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_slim_v22.0-SP1-io.bin.zip",
                filename="FydeOS_for_PC_slim_v22.0-SP1-io.bin.zip",
                version="22.0-SP1",
                arch="x86_64",
                source_page="https://fydeos.io/download/pc/intel-slim/",
                priority=4,
                notes="Downloads the official FydeOS raw disk archive; Distro Hunter extracts the .bin.zip payload to a Ventoy-friendly .img",
            ),
        ),
    ),
    PluginDiscoveryCase(
        label="FydeOS AMD Graphics",
        module_name="distro_hunter.plugins.fydeos_pc_amd",
        link_pages={
            "https://fydeos.io/download/pc/apu/": [
                "https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_apu_v22.0-SP1-io.bin.zip",
                "https://drive.google.com/file/d/example/view",
            ]
        },
        text_pages={
            "https://fydeos.io/download/pc/apu/": (
                '<h3>SHA-256 (FydeOS_for_PC_apu_v22.0-SP1-io.bin.zip)</h3>'
                '<code id="hash">8f50a42a8a1e55ce3e4d6c48d5b22bc495b84fb9244680730cff15f4d9b93869</code>'
            )
        },
        expected=(
            _candidate(
                url="https://download.fydeos.io/v22.0-SP1/FydeOS_for_PC_apu_v22.0-SP1-io.bin.zip",
                filename="FydeOS_for_PC_apu_v22.0-SP1-io.bin.zip",
                version="22.0-SP1",
                arch="x86_64",
                source_page="https://fydeos.io/download/pc/apu/",
                priority=5,
                notes="Downloads the official FydeOS raw disk archive; Distro Hunter extracts the .bin.zip payload to a Ventoy-friendly .img",
            ),
        ),
    ),
)
