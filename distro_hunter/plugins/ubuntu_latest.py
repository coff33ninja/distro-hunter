from __future__ import annotations

from distro_hunter.plugins.common import build_ubuntu_thank_you_discover


NAME = "Ubuntu Desktop Latest"
PAGE_URL = "https://ubuntu.com/download/desktop"
THANK_YOU_REGEX = r"thank-you\?version=([\d.]+).*?architecture=amd64"
ISO_REGEX = r"ubuntu-([\d.]+)-desktop-amd64\.iso$"


def _latest_priority(thank_you: str, version: str | None, default_priority: int) -> int:
    if "lts=true" in thank_you.lower():
        return default_priority
    return default_priority + 2


discover = build_ubuntu_thank_you_discover(
    page_url=PAGE_URL,
    thank_you_regex=THANK_YOU_REGEX,
    iso_regex=ISO_REGEX,
    arch="amd64",
    priority=4,
    include_lts=None,
    priority_builder=_latest_priority,
)
