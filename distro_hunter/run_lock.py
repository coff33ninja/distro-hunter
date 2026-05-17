from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from distro_hunter.exceptions import RunLockError
from distro_hunter.utils import ensure_directory


def default_lock_path(state_file: Path) -> Path:
    return state_file.with_name("distro_hunter.lock")


def _lock_payload(command: str) -> dict[str, str | int]:
    return {
        "pid": os.getpid(),
        "command": command,
        "created_at": datetime.now(UTC).isoformat(),
    }


def read_lock_info(path: Path) -> dict[str, str | int] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_process_running(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259

        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _acquire(path: Path, command: str) -> None:
    ensure_directory(path.parent)
    payload = json.dumps(_lock_payload(command), indent=2)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(str(path), flags)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


@contextmanager
def run_lock(path: Path, command: str) -> Iterator[None]:
    try:
        _acquire(path, command)
    except FileExistsError:
        info = read_lock_info(path) or {}
        pid = info.get("pid")
        if isinstance(pid, int) and not is_process_running(pid):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            _acquire(path, command)
        else:
            details: list[str] = [f"Lock file: {path}"]
            if isinstance(pid, int):
                details.append(f"PID: {pid}")
            active_command = info.get("command")
            if isinstance(active_command, str) and active_command:
                details.append(f"Command: {active_command}")
            raise RunLockError(
                "Another Distro Hunter process is already running. " + " | ".join(details)
            ) from None

    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
