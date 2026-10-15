"""Regenerate windows_* plugin stubs and config.windows.json from windows_common.CATALOG."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from distro_hunter.plugins.windows_common import CATALOG  # noqa: E402

STUB = (
    "from __future__ import annotations\n\n"
    "from distro_hunter.plugins.windows_common import build, ventoy_subdir\n\n"
    "NAME, METADATA, discover = build(__name__)\n"
    "VENTOY_SUBDIR = ventoy_subdir(__name__)\n"
)

for slug, spec in CATALOG.items():
    plugin_stub = STUB
    if spec.batch_download:
        plugin_stub += "\nBATCH_DOWNLOAD = True\n"
    plugin_path = ROOT / "distro_hunter" / "plugins" / f"{slug}.py"
    if not plugin_path.exists() or plugin_path.read_text(encoding="utf-8") != plugin_stub:
        plugin_path.write_text(plugin_stub, encoding="utf-8")

config_path = ROOT / "config.windows.json"
config = json.loads(config_path.read_text(encoding="utf-8"))
if config["plugins"]["builtin"] != list(CATALOG):
    config["plugins"]["builtin"] = list(CATALOG)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
print(f"{len(CATALOG)} windows plugins written")
