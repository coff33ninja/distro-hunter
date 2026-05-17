from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from distro_hunter.utils import ensure_directory
from distro_hunter.web import WebClient

GITHUB_API = "https://api.github.com/repos/aria2/aria2/releases/latest"
WIN64_PATTERN = "win-64bit-build1.zip"
TOOLS_SUBDIR = Path("tools") / "aria2"


def _latest_release_url(client: WebClient) -> str:
    body, _, _ = client._request(GITHUB_API, method="GET", headers={"Accept": "application/vnd.github+json", "User-Agent": "distro-hunter"})
    data = json.loads(body.decode("utf-8"))
    for asset in data.get("assets", []):
        url = asset.get("browser_download_url", "")
        if WIN64_PATTERN in url.lower():
            return url
    raise RuntimeError(f"No Windows 64-bit aria2 release asset found matching '{WIN64_PATTERN}'")


def bootstrap_aria2(base_dir: Path) -> Path | None:
    target_dir = (base_dir / TOOLS_SUBDIR).resolve()
    target_path = target_dir / "aria2c.exe"
    if target_path.exists():
        return target_path

    ensure_directory(target_dir)
    client = WebClient(user_agent="distro-hunter/1.0", timeout_seconds=30, retry_attempts=2)

    try:
        download_url = _latest_release_url(client)
    except Exception:
        return None

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / "aria2.zip"

        try:
            client.download(download_url, str(archive_path))
        except Exception:
            return None

        if not archive_path.exists():
            return None

        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(tmp_path)

        extracted = list(tmp_path.rglob("aria2c.exe"))
        if not extracted:
            return None

        shutil.copy2(extracted[0], target_path)

    if target_path.exists():
        return target_path
    return None
