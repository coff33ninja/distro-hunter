from __future__ import annotations

import json

from distro_hunter.models import Candidate


NAME = "Pop!_OS NVIDIA"
PAGE_URL = "https://system76.com/pop/download/"
API_URL = "https://api.pop-os.org/builds/24.04/nvidia?arch=amd64"


def discover(context) -> list[Candidate]:
    data = json.loads(context.fetch_text(API_URL))
    if data.get("errors"):
        return []
    url = data["url"]
    return [
        Candidate(
            url=url,
            filename=url.rsplit("/", 1)[-1],
            version=data.get("version"),
            arch="amd64",
            source_page=PAGE_URL,
            notes="NVIDIA image",
            priority=6,
        )
    ]
