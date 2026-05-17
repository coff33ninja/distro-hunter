from __future__ import annotations

from distro_hunter.plugins.common import build_regex_discover


NAME = "Ubuntu Cinnamon LTS"
PAGE_URL = "https://cdimage.ubuntu.com/ubuntucinnamon/releases/24.04/release/"
REGEX = r"ubuntucinnamon-(24\.04\.\d+)-desktop-amd64\.iso$"


discover = build_regex_discover(
    page_url=PAGE_URL,
    regex=REGEX,
    priority=5,
    arch="amd64",
    torrent_suffix=".torrent",
)
