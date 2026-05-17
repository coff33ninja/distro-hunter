from __future__ import annotations

from distro_hunter.plugins.common import build_ubuntu_thank_you_discover


NAME = "Ubuntu Server Latest"
PAGE_URL = "https://ubuntu.com/download/server"
THANK_YOU_REGEX = r"thank-you\?version=([\d.]+).*?architecture=amd64"
ISO_REGEX = r"ubuntu-([\d.]+)-live-server-amd64\.iso$"


discover = build_ubuntu_thank_you_discover(
    page_url=PAGE_URL,
    thank_you_regex=THANK_YOU_REGEX,
    iso_regex=ISO_REGEX,
    arch="amd64",
    priority=6,
    include_lts=False,
    torrent_suffix=".torrent",
)
