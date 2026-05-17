from __future__ import annotations

from distro_hunter.plugins.common import discover_exact_filename_candidates


NAME = "Linux Mint Xfce"
PAGE_URL = "https://linuxmint.com/edition.php?id=327"
FILENAME = "linuxmint-22.3-xfce-64bit.iso"
TORRENT_URL = "https://www.linuxmint.com/torrents/linuxmint-22.3-xfce-64bit.iso.torrent"
PREFERRED_HOSTS = ("pub.linuxmint.io", "mirrors.kernel.org", "www.mirrorservice.org")


def discover(context):
    return discover_exact_filename_candidates(
        context,
        page_url=PAGE_URL,
        filename=FILENAME,
        version="22.3",
        arch="amd64",
        priority=5,
        preferred_hosts=PREFERRED_HOSTS,
        torrent_url=TORRENT_URL,
        max_candidates=3,
    )
