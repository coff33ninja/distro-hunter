import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from distro_hunter import cli
from distro_hunter.core import DistroHunter


class ReportTests(unittest.TestCase):
    def test_report_records_flatten_state(self) -> None:
        hunter = object.__new__(DistroHunter)
        hunter.plugin_map = {}
        hunter.state = type(
            "State",
            (),
            {
                "data": {
                    "plugins": {
                        "ubuntu_lts": {
                            "selection": {
                                "version": "24.04.4",
                                "filename": "ubuntu-24.04.4.iso",
                                "url": "https://example.org/ubuntu-24.04.4.iso",
                            },
                            "download": {
                                "path": "ubuntu-24.04.4.iso",
                                "filename": "ubuntu-24.04.4.iso",
                                "downloaded": False,
                                "remote": {
                                    "final_url": "https://mirror.example.org/ubuntu-24.04.4.iso",
                                    "size": 123,
                                },
                            },
                            "health": {
                                "healthy": True,
                                "last_status": "ok",
                                "failure_count": 0,
                            },
                        }
                    }
                }
            },
        )()

        records = DistroHunter.report_records(hunter)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["plugin_slug"], "ubuntu_lts")
        self.assertEqual(records[0]["plugin_family"], "ubuntu")
        self.assertEqual(records[0]["plugin_edition_type"], "desktop")
        self.assertEqual(records[0]["selection_version"], "24.04.4")
        self.assertEqual(records[0]["download_path"], "ubuntu-24.04.4.iso")
        self.assertTrue(records[0]["health_healthy"])

    def test_cli_report_outputs_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_dir = root / "state"
            state_dir.mkdir()
            config_path = root / "config.json"
            state_path = state_dir / "distro_hunter_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "state_version": 3,
                        "plugins": {
                            "ubuntu_lts": {
                                "selection": {
                                    "version": "24.04.4",
                                    "filename": "ubuntu-24.04.4.iso",
                                    "url": "https://example.org/ubuntu-24.04.4.iso",
                                },
                                "download": {
                                    "path": "ubuntu-24.04.4.iso",
                                    "filename": "ubuntu-24.04.4.iso",
                                    "downloaded": False,
                                    "remote": {
                                        "final_url": "https://mirror.example.org/ubuntu-24.04.4.iso",
                                        "size": 123,
                                    },
                                },
                                "health": {
                                    "healthy": True,
                                    "last_status": "ok",
                                    "failure_count": 0,
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
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

            json_output = io.StringIO()
            with redirect_stdout(json_output):
                json_exit = cli.main(["--config", str(config_path), "report"])

            csv_output = io.StringIO()
            with redirect_stdout(csv_output):
                csv_exit = cli.main(["--config", str(config_path), "report", "--format", "csv"])

            self.assertEqual(json_exit, 0)
            self.assertEqual(csv_exit, 0)
            self.assertIn('"plugin_slug": "ubuntu_lts"', json_output.getvalue())
            self.assertIn("plugin_slug,plugin_name,plugin_family", csv_output.getvalue())
            self.assertIn("ubuntu_lts", csv_output.getvalue())


if __name__ == "__main__":
    unittest.main()
