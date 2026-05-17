from __future__ import annotations

from distro_hunter.plugins.garuda_common import discover_garuda_flavor


NAME = "Garuda Mokka"


def discover(context):
    return discover_garuda_flavor(
        context,
        flavor="mokka",
        arch="x86_64",
        priority=5,
    )
