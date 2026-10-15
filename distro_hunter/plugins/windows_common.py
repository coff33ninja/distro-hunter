"""Windows ISO plugins backed by archive.org item metadata.

Every windows_* plugin module is a stub calling build(__name__); the CATALOG below
is the single source of truth. Candidates carry the sha1 archive.org publishes, so
the downloader verifies them. Regenerate stubs + config with
scripts/gen_windows_plugins.py after editing the catalog.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from requests.exceptions import RequestException

from distro_hunter.models import Candidate

ARCHIVE = "https://archive.org"
# Two items that carry the same folder tree; the first one wins on priority.
TREE_ITEMS = ("windows-iso-collection-flutter", "english_windows_collection")
VINTAGE = "vintage-versions-of-windows-1980s-1990s"
CACHE_TTL_SECONDS = 300.0

_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class Spec:
    name: str
    version: str
    arch: str
    edition: str
    sources: tuple[tuple[str, str], ...]  # (archive.org identifier, regex on file path)
    uup_query: str | None = None
    slug: str = ""
    batch_download: bool = False


CATALOG: dict[str, Spec] = {}
UUP_QUERIES = {
    "windows_11_25h2_x64": "Windows 11, version 25H2",
    "windows_11_latest_x64": "Windows 11",
    "windows_11_latest_arm64": "Windows 11",
    "windows_11_24h2_x64": "Windows 11, version 24H2",
    "windows_11_24h2_arm64": "Windows 11, version 24H2",
    "windows_11_23h2_x64": "Windows 11, version 23H2",
    "windows_11_22h2_x64": "Windows 11, version 22H2",
    "windows_10_21h2_x64": "Windows 10, version 21H2",
    "windows_10_21h2_x86": "Windows 10, version 21H2",
    "windows_10_22h2_x64": "Windows 10, version 22H2",
    "windows_10_22h2_x86": "Windows 10, version 22H2",
}


def _tree(pattern: str) -> tuple[tuple[str, str], ...]:
    return tuple((item, pattern) for item in TREE_ITEMS)


def _add(
    slug: str,
    name: str,
    version: str,
    arch: str,
    edition: str,
    sources: tuple[tuple[str, str], ...],
    *,
    batch_download: bool = False,
) -> None:
    CATALOG[slug] = Spec(
        name,
        version,
        arch,
        edition,
        sources,
        UUP_QUERIES.get(slug),
        slug,
        batch_download,
    )


# --- Windows 11 -------------------------------------------------------------
_add("windows_11_25h2_x64", "Windows 11 25H2 (x64, Media Creation Tool)", "25H2", "x86_64", "11-25h2",
     (("win1125H2_official", r"^MCT_Win11_25H2_English_x64\.iso$"),))
_add("windows_11_26h2_x64", "Windows 11 26H2 (x64)", "26H2", "x86_64", "11-26h2",
     (("windows-11-26h2-from-microsoft", r"^X64/Windows11_Client_x64_en-us_.*\.iso$"),))
_add("windows_11_26h2_arm64", "Windows 11 26H2 (ARM64)", "26H2", "arm64", "11-26h2",
     (("windows-11-26h2-from-microsoft", r"^Windows11_Client_arm64_en-us_.*\.iso$"),))
_add("windows_11_latest_x64", "Windows 11 latest UUP builds (x64)", "latest", "x86_64", "11-latest", ())
_add("windows_11_latest_arm64", "Windows 11 latest UUP builds (ARM64)", "latest", "arm64", "11-latest", ())
_add("windows_11_24h2_x64", "Windows 11 24H2 (x64)", "24H2", "x86_64", "11-24h2",
     (("WIN11_24H2", r"^Win11_24H2_English_x64\.iso$"),
      ("win11-24h2-english-x64-arm_202501", r"^Win11_24H2_English_x64\.iso$"),
      ("windows-11-24h2-x64", r"\.iso$")))
_add("windows_11_24h2_arm64", "Windows 11 24H2 (ARM64)", "24H2", "arm64", "11-24h2",
     (("win11-24h2-english-x64-arm_202501", r"^Win11_24H2_English_Arm64\.iso$"),))
_add("windows_11_23h2_x64", "Windows 11 23H2 (x64)", "23H2", "x86_64", "11-23h2",
     _tree(r"^Windows 11/23H2/.*\.iso$") + (("win-11-23h2", r"\.iso$"),))
_add("windows_11_22h2_x64", "Windows 11 22H2 (x64)", "22H2", "x86_64", "11-22h2",
     _tree(r"^Windows 11/22H2/.*\.iso$") + (("windows-11-version-22h2", r"\.iso$"),))
_add("windows_11_21h2_x64", "Windows 11 21H2 RTM (x64)", "21H2", "x86_64", "11-21h2",
     _tree(r"^Windows 11/RTM/.*\.iso$")
     + (("win11-en-fr", r"^en-us_windows_11_consumer_editions_x64_dvd_bd3cf8df\.iso$"),))

# --- Windows 10 (every release, x64 + x86) ----------------------------------
_W10 = {
    "1507": "1507 ", "1511": "1511 ", "1607": "1607 ", "1703": "1703 ", "1709": "1709 ",
    "1803": "1803 ", "1809": "1809 ", "1903": "1903 ", "1909": "1909 ", "2004": "2004 ",
    "20h2": "20H2/", "21h1": "21H1/", "21h2": "21H2/", "22h2": "22H2/",
}
for _ver, _folder in _W10.items():
    for _label, _arch, _suffix in (("x64", "x86_64", "x64"), ("x86", "x86", "x32")):
        _add(f"windows_10_{_ver}_{_label}", f"Windows 10 {_ver.upper()} ({_label})", _ver.upper(), _arch,
             f"10-{_ver}", _tree(rf"^Windows 10/{_folder}.*_{_suffix}\.iso$"))

# --- Windows 8 / 7 / Vista / XP ---------------------------------------------
_add("windows_8_1_x64", "Windows 8.1 Update 1 (x64)", "8.1", "x86_64", "8-1",
     _tree(r"^Windows 8\.1/Update 1/.*x64.*\.iso$"))
_add("windows_8_1_x86", "Windows 8.1 Update 1 (x86)", "8.1", "x86", "8-1",
     _tree(r"^Windows 8\.1/Update 1/.*(x86|x32).*\.iso$"))
_add("windows_8_x64", "Windows 8 Pro (x64)", "8", "x86_64", "8",
     (("english_windows_collection", r"^Windows 8/Windows 8 Pro 64-Bit\.iso$"),))
_add("windows_8_x86", "Windows 8 Pro (x86)", "8", "x86", "8",
     (("english_windows_collection", r"^Windows 8/Windows 8 Pro 32-Bit\.iso$"),))
_add("windows_7_sp1_x64", "Windows 7 SP1 (x64)", "7", "x86_64", "7-sp1", _tree(r"^Windows 7/SP1/.*x64.*\.iso$"))
_add("windows_7_sp1_x86", "Windows 7 SP1 (x86)", "7", "x86", "7-sp1", _tree(r"^Windows 7/SP1/.*(x86|x32).*\.iso$"))
_add("windows_vista_sp2_x64", "Windows Vista SP2 (x64)", "6.0", "x86_64", "vista-sp2",
     _tree(r"^Windows Vista/SP2/.*x64.*\.iso$"))
_add("windows_vista_sp2_x86", "Windows Vista SP2 (x86)", "6.0", "x86", "vista-sp2",
     _tree(r"^Windows Vista/SP2/.*x86.*\.iso$"))
_add("windows_xp_pro_sp3_x86", "Windows XP Professional SP3", "5.1", "x86", "xp-pro-sp3",
     _tree(r"^Windows XP/PRO/SP3/.*\.iso$"))
_add("windows_xp_pro_x64", "Windows XP Professional x64", "5.2", "x86_64", "xp-pro-x64",
     _tree(r"^Windows XP/PRO X64/Windows_XP_Pro_x64_(EN|English)\.iso$"))
_add("windows_xp_home_sp3_x86", "Windows XP Home SP3", "5.1", "x86", "xp-home-sp3",
     _tree(r"^Windows XP/Home Edition/SP3/.*\.iso$"))
_add("windows_xp_mce_2005_x86", "Windows XP Media Center 2005 SP3", "5.1", "x86", "xp-mce",
     _tree(r"^Windows XP/Media Center Edition/.*\.iso$"))

# --- 9x / 2000 / NT / Neptune -----------------------------------------------
_add("windows_2000_pro_sp4_x86", "Windows 2000 Professional SP4", "5.0", "x86", "2000-pro-sp4",
     _tree(r"^Windows 2000/SP4/.*\.iso$"))
_add("windows_me_x86", "Windows Me (OEM)", "4.90", "x86", "me", _tree(r"^Windows ME/Windows Me OEM/.*\.iso$"))
_add("windows_98_se_x86", "Windows 98 Second Edition (bootable)", "4.10", "x86", "98-se",
     _tree(r"^Windows 98/Second Edition X86 Bootable/.*\.iso$"))
_add("windows_98_fe_x86", "Windows 98 First Edition (upgrade)", "4.10", "x86", "98-fe",
     _tree(r"^Windows 98/First Edition Upgrade CD/.*\.iso$"))
_add("windows_95_rtm_x86", "Windows 95 RTM (OEM)", "4.00", "x86", "95-rtm",
     _tree(r"^Windows 95/Microsoft Windows 95 \(OEM\) 4\.00\.950 \(RTM\)/.*\.iso$"))
_add("windows_95_osr1_x86", "Windows 95 OSR1 (OEM)", "4.00", "x86", "95-osr1",
     _tree(r"^Windows 95/Microsoft Windows 95A .*\.iso$"))
_add("windows_95_osr2_x86", "Windows 95 OSR2", "4.00", "x86", "95-osr2",
     _tree(r"^Windows 95/Microsoft Windows 95B \(4\.00\.1111\) \(OSR2\)/.*\.iso$"))
_add("windows_95_osr2_5_x86", "Windows 95 OSR2.5", "4.03", "x86", "95-osr2-5",
     _tree(r"^Windows 95/Microsoft Windows 95C .*\.iso$"))
_add("windows_nt_4_0_server_x86", "Windows NT 4.0 Server SP1", "4.0", "x86", "nt-4-0-server",
     _tree(r"^Windows NT 4\.0/NT 4\.0 Server .*\.iso$"))
_add("windows_neptune_5111_x86", "Windows Neptune build 5111", "5111", "x86", "neptune",
     _tree(r"^Windows Neptune Build 5111/.*\.iso$"))

# --- Related legacy media sets ----------------------------------------------
_add("windows_dos_6_0_x86", "MS-DOS 6.0 floppy set", "6.0", "x86", "dos-6-0",
     _tree(r"^MS DOS 6\.0/.*\.(img|ima|iso)$"), batch_download=True)
_add("windows_1_3_floppy_sets_x86", "Windows 1.x–3.x floppy sets", "1.x-3.x", "x86", "windows-1-3",
     _tree(r"^Windows [123](\.\d+)?/.*\.(img|ima|iso)$"), batch_download=True)
_add("windows_nt_4_0_enterprise_x86", "Windows NT 4.0 Enterprise split media", "4.0", "x86", "nt-4-0-enterprise",
     _tree(r"^Windows NT 4\.0/NT 4\.0 Enterprise Server .*\.(iso|img)$"), batch_download=True)
_add("windows_server_2003_r2_enterprise_x64", "Windows Server 2003 R2 Enterprise (x64)", "2003R2", "x86_64",
     "server-2003-r2-enterprise",
     (("en_win_srv_2003_r2_enterprise_x64_cd1_cd2",
       r"^en_win_srv_2003_r2_enterprise_x64_cd[12]\.iso$"),),
     batch_download=True)

# --- Pre-9x archives; .7z members are extracted to image files ---------------
_add("windows_1_04_x86", "Windows 1.04", "1.04", "x86", "1-04",
     ((VINTAGE, r"^Microsoft Windows 1\.04 \(5\.25\)\.7z$"),))
_add("windows_2_03_x86", "Windows 2.03", "2.03", "x86", "2-03",
     ((VINTAGE, r"^Microsoft Windows 2\.03 \(3\.5-720k\)\.7z$"),))
_add("windows_3_0a_x86", "Windows 3.0a", "3.0", "x86", "3-0a",
     ((VINTAGE, r"^Microsoft Windows 3\.0a \(3\.5 720K\)\.7z$"),))
_add("windows_nt_3_1_advanced_server_x86", "Windows NT 3.1 Advanced Server", "3.1", "x86", "nt-3-1-advanced-server",
     ((VINTAGE, r"^Microsoft Windows NT 3\.1 Advanced Server .*\.7z$"),))
_add("windows_nt_3_5_server_x86", "Windows NT 3.5 Server", "3.5", "x86", "nt-3-5-server",
     ((VINTAGE, r"^Microsoft Windows NT 3\.5 Server .*\.7z$"),))
_add("windows_nt_3_51_workstation_x86", "Windows NT 3.51 Workstation", "3.51", "x86", "nt-3-51-workstation",
     ((VINTAGE, r"^Microsoft Windows NT 3\.51 Workstation .*\.7z$"),))

# --- Windows Server ---------------------------------------------------------
_add("windows_server_2000_advanced_sp4_x86", "Windows 2000 Advanced Server SP4", "5.0", "x86", "server-2000",
     _tree(r"^Windows Server/Windows Server 2000/Windows 2000 Advanced Server SP4\.iso$"))
_add("windows_server_2008_sp2_x64", "Windows Server 2008 SP2 (x64)", "2008", "x86_64", "server-2008",
     _tree(r"^Windows Server/Windows Server 2008/en_windows_server_2008_with_sp2_x64_dvd_.*\.iso$"))
_add("windows_server_2008_sp2_x86", "Windows Server 2008 SP2 (x86)", "2008", "x86", "server-2008",
     _tree(r"^Windows Server/Windows Server 2008/en_windows_server_2008_with_sp2_x86_dvd_.*\.iso$"))
_add("windows_server_2008_r2_x64", "Windows Server 2008 R2 SP1 (x64)", "2008", "x86_64", "server-2008-r2",
     _tree(r"^Windows Server/Windows Server 2008 R2/.*\.iso$"))
_add("windows_server_2012_x64", "Windows Server 2012 (x64)", "2012", "x86_64", "server-2012",
     _tree(r"^Windows Server/Windows Server 2012/en_windows_server_2012_x64_dvd_.*\.iso$"))
_add("windows_server_2012_r2_x64", "Windows Server 2012 R2 Evaluation (x64)", "2012", "x86_64", "server-2012-r2",
     _tree(r"^Windows Server/Windows Server 2012 R2/.*\.iso$"))
_add("windows_server_2016_x64", "Windows Server 2016 Evaluation (x64)", "2016", "x86_64", "server-2016",
     _tree(r"^Windows Server/Windows Server 2016/.*\.iso$"))
_add("windows_server_2019_x64", "Windows Server 2019 Evaluation (x64)", "2019", "x86_64", "server-2019",
     _tree(r"^Windows Server/Windows Server 2019/.*\.iso$"))
_add("windows_server_2022_x64", "Windows Server 2022 Evaluation (x64)", "2022", "x86_64", "server-2022",
     _tree(r"^Windows Server/Windows Server 2022/.*\.iso$"))
_add("windows_server_2025_x64", "Windows Server 2025 (x64)", "2025", "x86_64", "server-2025",
     (("en-us_windows_server_2025_updated_march_2026_x64_dvd_8e06425a",
       r"^en-us_windows_server_2025_updated_march_2026_x64_dvd_.*\.iso$"),))


def _item_files(context, identifier: str) -> list[dict]:
    with _lock:
        hit = _cache.get(identifier)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
        payload = json.loads(context.fetch_text(f"{ARCHIVE}/metadata/{identifier}"))
        files = payload.get("files", [])
        _cache[identifier] = (time.monotonic(), files)
        return files


def discover_spec(context, spec: Spec) -> list[Candidate]:
    candidates: list[Candidate] = []
    errors: list[Exception] = []
    for rank, (identifier, pattern) in enumerate(spec.sources):
        try:
            files = _item_files(context, identifier)
        except (RequestException, ValueError) as exc:
            errors.append(exc)
            continue
        matcher = re.compile(pattern, re.IGNORECASE)
        for entry in files:
            name = entry.get("name", "")
            if not matcher.search(name):
                continue
            metadata: dict[str, object] = {}
            sha1 = str(entry.get("sha1", "")).lower()
            if re.fullmatch(r"[a-f0-9]{40}", sha1):
                metadata = {
                    "checksum_algorithm": "sha1",
                    "checksum_expected": sha1,
                    "checksum_source": f"{ARCHIVE}/metadata/{identifier}",
                }
            candidates.append(
                Candidate(
                    url=f"{ARCHIVE}/download/{identifier}/{quote(name)}",
                    filename=_download_name(spec, name),
                    version=spec.version,
                    arch=spec.arch,
                    source_page=f"{ARCHIVE}/details/{identifier}",
                    notes=f"archive.org/{identifier}",
                    priority=10 - rank,
                    metadata={
                        **metadata,
                        "source_kind": "archive-org",
                        "archive_member": name,
                        "edition_type": spec.edition,
                        **(
                            {"preserve_related_artifacts": True}
                            if spec.batch_download or name.lower().endswith(".7z")
                            else {}
                        ),
                    },
                )
            )
    if spec.batch_download:
        unique_candidates: dict[str, Candidate] = {}
        for candidate in candidates:
            member = str(candidate.metadata.get("archive_member", candidate.url))
            unique_candidates.setdefault(member, candidate)
        candidates = list(unique_candidates.values())
    candidates.extend(discover_uup_candidates(context, spec))
    if not candidates and errors:
        raise errors[0]
    return candidates


def _uup_candidate(build_entry: dict, spec: Spec) -> tuple[int, Candidate] | None:
    title = build_entry.get("title")
    build_arch = build_entry.get("arch")
    build_uuid = build_entry.get("uuid")
    build_number = build_entry.get("build")
    expected_arch = {
        "x86_64": {"amd64", "x64", "x86_64"},
        "x86": {"x86", "x86_32"},
        "arm64": {"arm64", "aarch64"},
    }.get(spec.arch, {spec.arch.casefold()})
    release_version = None
    if spec.version == "latest":
        match = (
            re.fullmatch(
                r"Windows 11, version (?P<release>\d{2}H[12]) "
                r"\((?P<build>\d+(?:\.\d+)*)\)",
                title,
                re.IGNORECASE,
            )
            if isinstance(title, str)
            else None
        )
        if match is None:
            return None
        release_version = match.group("release").upper()
    elif not isinstance(title, str) or spec.uup_query.casefold() not in title.casefold():
        return None
    if not isinstance(build_arch, str) or build_arch.casefold() not in expected_arch:
        return None
    if not isinstance(build_uuid, str) or not re.fullmatch(
        r"[a-f0-9-]{36}", build_uuid, re.IGNORECASE
    ):
        return None

    try:
        created = int(build_entry.get("created", 0))
    except (TypeError, ValueError):
        created = 0
    page_url = f"https://uupdump.net/selectlang.php?id={build_uuid}"
    candidate = Candidate(
        url=page_url,
        filename=title,
        version=str(build_number) if build_number is not None else spec.version,
        arch=spec.arch,
        source_page=page_url,
        notes="Choose a language and edition on UUP Dump to assemble the ISO.",
        priority=1,
        metadata={
            "downloadable": False,
            "source_kind": "UUP Dump",
            "edition_type": spec.edition,
            "build_uuid": build_uuid,
            **(
                {"release_version": release_version}
                if release_version is not None
                else {}
            ),
        },
    )
    return created, candidate


def discover_uup_candidates(context, spec: Spec) -> list[Candidate]:
    """Find matching UUP builds as build-page links, never as ISO downloads."""
    if spec.uup_query is None:
        return []

    query = urlencode({"search": spec.uup_query, "sortByDate": "1"})
    payload = json.loads(
        context.fetch_text(f"https://api.uupdump.net/listid.php?{query}")
    )
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected UUP Dump response for query {spec.uup_query!r}")
    response = payload.get("response")
    builds = response.get("builds") if isinstance(response, dict) else None
    if not isinstance(builds, dict):
        raise TypeError(f"Unexpected UUP Dump response for query {spec.uup_query!r}")

    results = [
        candidate
        for entry in builds.values()
        if isinstance(entry, dict)
        if (candidate := _uup_candidate(entry, spec)) is not None
    ]
    results.sort(key=lambda item: item[0], reverse=True)
    if spec.version == "latest":
        latest_by_release: dict[str, tuple[int, Candidate]] = {}
        for created, candidate in results:
            release = candidate.metadata["release_version"]
            latest_by_release.setdefault(str(release), (created, candidate))
        results = sorted(
            latest_by_release.values(),
            key=lambda item: item[0],
            reverse=True,
        )
    return [candidate for _created, candidate in results]


def build(module_name: str):
    """Return (NAME, METADATA, discover) for a windows_* plugin stub."""
    spec = CATALOG[module_name.rsplit(".", 1)[-1]]
    metadata = {
        "family": "windows",
        "architecture": spec.arch,
        "edition_type": spec.edition,
        "source_kind": "archive-org",
    }

    def discover(context) -> list[Candidate]:
        return discover_spec(context, spec)

    return spec.name, metadata, discover


def batch_download(module_name: str) -> bool:
    return CATALOG[module_name.rsplit(".", 1)[-1]].batch_download


# --- Library layout + naming (mirrors H:\ISO\Windows\README.md sections 1-2) --
# Sorted straight into: <product>/official/<arch>/Windows_<Ver>_<Release>_<Build>_<Arch>_<Lang>[_<Edition>].iso
_ARCH_FOLDER = {"x86_64": "x64", "x86": "x86", "arm64": "arm64"}
_WIN10_BUILDS = {
    "1507": "10240", "1511": "10586", "1607": "14393", "1703": "15063", "1709": "16299",
    "1803": "17134", "1809": "17763", "1903": "18362", "1909": "18363", "2004": "19041",
    "20h2": "19042", "21h1": "19043", "21h2": "19044", "22h2": "19045",
}
_WIN11_BUILDS = {
    "21h2": "22000",
    "22h2": "22621",
    "23h2": "22631",
    "24h2": "26100",
    "25h2": "26200",
    "26h2": "26300",
    "latest": "latest",
}
# edition -> (folder, version token, release, build, edition token); version None = keep the original file name
_OTHER = {
    "dos-6-0": ("MS-DOS 6.0", None, None, None, None),
    "windows-1-3": ("Windows 1.x-3.x", None, None, None, None),
    "nt-4-0-enterprise": ("Windows NT 4.0", None, None, None, None),
    "8": ("Windows 8", "8", "RTM", "9200", None),
    "8-1": ("Windows 8.1", "8.1", "Update1", "9600", None),
    "7-sp1": ("Windows 7", "7", "SP1", "7601", None),
    "vista-sp2": ("Windows Vista", "Vista", "SP2", "6002", None),
    "xp-pro-sp3": ("Windows XP", "XP", "SP3", "2600", "Pro"),
    "xp-home-sp3": ("Windows XP", "XP", "SP3", "2600", "Home"),
    "xp-mce": ("Windows XP", "XP", "SP3", "2600", "MediaCenter"),
    "xp-pro-x64": ("Windows XP", "XP", None, "3790", "Pro"),
    "2000-pro-sp4": ("Windows 2000", "2000", "SP4", "2195", "Pro"),
    "me": ("Windows Me", "Me", "RTM", "3000", None),
    "98-se": ("Windows 98", "98", "SE", "2222", None),
    "98-fe": ("Windows 98", "98", "FE", "1998", "Upgrade"),
    "95-rtm": ("Windows 95", "95", "RTM", "950", None),
    "95-osr1": ("Windows 95", "95", "OSR1", "950", None),
    "95-osr2": ("Windows 95", "95", "OSR2", "1111", None),
    "95-osr2-5": ("Windows 95", "95", "OSR2.5", "1216", None),
    "nt-4-0-server": ("Windows NT 4.0", "NT_4.0", "SP1", "1381", "Server"),
    "neptune": ("Windows Neptune", "Neptune", None, "5111", None),
    "nt-3-1-advanced-server": ("Windows NT 3.1", None, None, None, None),
    "nt-3-5-server": ("Windows NT 3.5", None, None, None, None),
    "nt-3-51-workstation": ("Windows NT 3.51", None, None, None, None),
    "1-04": ("Windows 1.0", None, None, None, None),
    "2-03": ("Windows 2.0", None, None, None, None),
    "3-0a": ("Windows 3.0", None, None, None, None),
}
# edition -> (release folder/token, service pack, build, edition token)
_SERVER = {
    "server-2003-r2-enterprise": ("2003R2", "R2", "3790", "Enterprise"),
    "server-2000": ("2000", "SP4", "2195", "Advanced"),
    "server-2008": ("2008", "SP2", "6002", None),
    "server-2008-r2": ("2008R2", "SP1", "7601", None),
    "server-2012": ("2012", None, "9200", None),
    "server-2012-r2": ("2012R2", None, "9600", "Eval"),
    "server-2016": ("2016", None, "14393", "Eval"),
    "server-2019": ("2019", None, "17763", "Eval"),
    "server-2022": ("2022", None, "20348", "Eval"),
    "server-2025": ("2025", None, "26100", None),
}


def _library_entry(spec: Spec) -> tuple[str, list[str | None] | None]:
    """Return (folder, filename parts without arch/lang) for a catalog entry."""
    edition = spec.edition
    if edition in _SERVER:
        release, service_pack, build, edition_token = _SERVER[edition]
        return f"Windows Server/{release}", ["Windows_Server", release, service_pack, build, "{arch}", "en-US", edition_token]
    product, _, release = edition.partition("-")
    if product in ("10", "11"):
        builds = _WIN10_BUILDS if product == "10" else _WIN11_BUILDS
        return f"Windows {product}", ["Windows", product, release.upper(), builds[release], "{arch}", "en-US"]
    folder, version, release_token, build, edition_token = _OTHER[edition]
    if version is None:
        return folder, None
    return folder, ["Windows", version, release_token, build, "{arch}", "en-US", edition_token]


def library_subdir(spec: Spec) -> str:
    folder, _parts = _library_entry(spec)
    return f"{folder}/official/{_ARCH_FOLDER[spec.arch]}"


def library_filename(spec: Spec) -> str | None:
    _folder, parts = _library_entry(spec)
    if parts is None:
        return None
    arch = _ARCH_FOLDER[spec.arch]
    return "_".join(part.format(arch=arch) for part in parts if part) + ".iso"


def _download_name(spec: Spec, original_path: str) -> str:
    original = original_path.rsplit("/", 1)[-1]
    if original.lower().endswith(".iso") and not spec.batch_download:
        return library_filename(spec) or original
    return original


def ventoy_subdir(module_name: str) -> str:
    """Folder under the Ventoy `ISO/Windows` root, e.g. `Windows 11/official/x64`."""
    return library_subdir(CATALOG[module_name.rsplit(".", 1)[-1]])
