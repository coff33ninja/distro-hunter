from __future__ import annotations

from distro_hunter.plugins.garuda_common import discover_garuda_flavor


NAME = "Garuda Sway"


def discover(context):
    return discover_garuda_flavor(
        context,
        flavor="sway",
        arch="x86_64",
        priority=4,
    )
