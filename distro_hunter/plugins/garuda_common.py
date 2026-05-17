from __future__ import annotations

import json
import re

from distro_hunter.models import Candidate
from distro_hunter.utils import extract_filename


CATEGORY_URL = "https://forum.garudalinux.org/c/announcements/iso-releases/l/latest.json"
TOPIC_URL_TEMPLATE = "https://forum.garudalinux.org/t/{slug}/{id}.json"


def discover_garuda_flavor(
    context,
    *,
    flavor: str,
    arch: str,
    priority: int,
    notes: str | None = None,
) -> list[Candidate]:
    category = json.loads(context.fetch_text(CATEGORY_URL))
    topics = category.get("topic_list", {}).get("topics", [])
    topic = next((item for item in topics if item.get("title", "").startswith("ISO Release:")), None)
    if not topic:
        return []

    version = topic["title"].split(":", 1)[1].strip()
    topic_url = TOPIC_URL_TEMPLATE.format(slug=topic["slug"], id=topic["id"])
    topic_data = json.loads(context.fetch_text(topic_url))
    cooked = topic_data["post_stream"]["posts"][0]["cooked"]
    regex = re.compile(
        rf"https://iso\.builds\.garudalinux\.org/iso/latest/garuda/{re.escape(flavor)}/latest\.iso\?r2=1",
        re.IGNORECASE,
    )
    match = regex.search(cooked)
    if not match:
        return []

    url = match.group(0)
    filename = None
    try:
        _, final_url = context.web.inspect_remote_file(url)
        filename = extract_filename(final_url)
    except Exception:
        filename = None

    return [
        Candidate(
            url=url,
            filename=filename,
            version=version,
            arch=arch,
            source_page=topic_url,
            notes=notes,
            priority=priority,
        )
    ]
