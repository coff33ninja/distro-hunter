from __future__ import annotations

from distro_hunter.plugins.windows_common import build, ventoy_subdir

NAME, METADATA, discover = build(__name__)
VENTOY_SUBDIR = ventoy_subdir(__name__)
