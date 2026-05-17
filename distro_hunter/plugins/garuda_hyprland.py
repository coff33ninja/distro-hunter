from __future__ import annotations

from distro_hunter.plugins.garuda_common import discover_garuda_flavor


NAME = "Garuda Hyprland"


def discover(context):
    return discover_garuda_flavor(
        context,
        flavor="hyprland",
        arch="x86_64",
        priority=5,
    )
