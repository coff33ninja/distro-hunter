from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Xubuntu LTS"
PAGE_URL = "https://cdimage.ubuntu.com/xubuntu/releases/24.04/release/"
REGEX = r"xubuntu-(24\.04\.\d+)-desktop-amd64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=5,
    arch="amd64",
    torrent_suffix=".torrent",
)
