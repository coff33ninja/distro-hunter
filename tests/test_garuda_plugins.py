import json
import unittest

from distro_hunter.plugins.garuda_common import CATEGORY_URL, TOPIC_URL_TEMPLATE, discover_garuda_flavor


class StubWeb:
    def inspect_remote_file(self, url: str):
        return {}, "https://r2.garudalinux.org/iso/garuda/dr460nized/260309/garuda-dr460nized-linux-zen-260309.iso?r2request"


class StubContext:
    def __init__(self) -> None:
        self.web = StubWeb()
        self.payloads = {
            CATEGORY_URL: json.dumps(
                {
                    "topic_list": {
                        "topics": [
                            {"id": 1, "slug": "about-the-iso-releases-category", "title": "About the ISO Releases category"},
                            {"id": 47557, "slug": "iso-release-260309", "title": "ISO Release: 260309"},
                        ]
                    }
                }
            ),
            TOPIC_URL_TEMPLATE.format(slug="iso-release-260309", id=47557): json.dumps(
                {
                    "post_stream": {
                        "posts": [
                            {
                                "cooked": '<p><a href="https://iso.builds.garudalinux.org/iso/latest/garuda/dr460nized/latest.iso?r2=1">Dr460nized</a></p>'
                            }
                        ]
                    }
                }
            ),
        }

    def fetch_text(self, url: str) -> str:
        return self.payloads[url]


class GarudaPluginTests(unittest.TestCase):
    def test_discover_garuda_flavor_uses_latest_release_topic(self) -> None:
        candidates = discover_garuda_flavor(
            StubContext(),
            flavor="dr460nized",
            arch="x86_64",
            priority=6,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].version, "260309")
        self.assertEqual(candidates[0].filename, "garuda-dr460nized-linux-zen-260309.iso")
        self.assertEqual(
            candidates[0].url,
            "https://iso.builds.garudalinux.org/iso/latest/garuda/dr460nized/latest.iso?r2=1",
        )


if __name__ == "__main__":
    unittest.main()
