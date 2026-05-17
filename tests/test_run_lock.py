import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from distro_hunter import cli
from distro_hunter.run_lock import RunLockError, default_lock_path, run_lock


class RunLockTests(unittest.TestCase):
    def test_run_lock_creates_and_removes_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "distro_hunter.lock"

            with run_lock(lock_path, "run"):
                self.assertTrue(lock_path.exists())
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["command"], "run")
                self.assertIsInstance(payload["pid"], int)

            self.assertFalse(lock_path.exists())

    def test_run_lock_cleans_up_stale_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "distro_hunter.lock"
            lock_path.write_text(
                json.dumps({"pid": 999999, "command": "run", "created_at": "2026-03-30T18:00:00+00:00"}),
                encoding="utf-8",
            )

            with patch("distro_hunter.run_lock.is_process_running", return_value=False):
                with run_lock(lock_path, "doctor"):
                    payload = json.loads(lock_path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["command"], "doctor")

            self.assertFalse(lock_path.exists())

    def test_run_lock_raises_when_active_process_holds_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "distro_hunter.lock"
            lock_path.write_text(
                json.dumps({"pid": 1234, "command": "run", "created_at": "2026-03-30T18:00:00+00:00"}),
                encoding="utf-8",
            )

            with patch("distro_hunter.run_lock.is_process_running", return_value=True):
                with self.assertRaises(RunLockError) as context:
                    with run_lock(lock_path, "doctor"):
                        pass

            self.assertIn("Another Distro Hunter process is already running.", str(context.exception))
            self.assertIn("PID: 1234", str(context.exception))
            self.assertIn("Command: run", str(context.exception))

    def test_cli_returns_nonzero_when_lock_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            state_dir = config_dir / "state"
            state_dir.mkdir()
            config_path = config_dir / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "state_file": "state/distro_hunter_state.json",
                        "plugins": {"builtin": []},
                        "ventoy": {"enabled": False},
                        "logging": {
                            "run_log_file": "logs/distro_hunter.log",
                            "mirror_failures_file": "logs/mirror_failures.log",
                        },
                    }
                ),
                encoding="utf-8",
            )

            lock_path = default_lock_path(state_dir / "distro_hunter_state.json")
            lock_path.write_text(
                json.dumps({"pid": 1234, "command": "run", "created_at": "2026-03-30T18:00:00+00:00"}),
                encoding="utf-8",
            )

            output = io.StringIO()
            with patch("distro_hunter.run_lock.is_process_running", return_value=True):
                with redirect_stdout(output):
                    exit_code = cli.main(["--config", str(config_path), "doctor"])

            self.assertEqual(exit_code, 1)
            self.assertIn("already running", output.getvalue())


if __name__ == "__main__":
    unittest.main()
