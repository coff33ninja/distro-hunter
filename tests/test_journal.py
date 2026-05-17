import json
import tempfile
import unittest
from pathlib import Path

from distro_hunter.config import LoggingSettings
from distro_hunter.journal import RunJournal


class JournalTests(unittest.TestCase):
    def test_journal_writes_text_and_jsonl_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = LoggingSettings(
                run_log_file=root / "run.log",
                mirror_failures_file=root / "mirror.log",
                jsonl_log_file=root / "run.jsonl",
            )
            journal = RunJournal(settings)

            journal.info("hello")
            journal.mirror_failure("ubuntu_lts", "https://mirror.example/ubuntu.iso", "403 Forbidden")

            text_log = settings.run_log_file.read_text(encoding="utf-8")
            self.assertIn("[INFO] hello", text_log)
            self.assertIn("[WARN] ubuntu_lts: https://mirror.example/ubuntu.iso -> 403 Forbidden", text_log)

            json_records = [
                json.loads(line)
                for line in settings.jsonl_log_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(json_records[0]["level"], "INFO")
            self.assertEqual(json_records[0]["message"], "hello")
            self.assertEqual(json_records[1]["event"], "mirror_failure")
            self.assertEqual(json_records[1]["plugin_slug"], "ubuntu_lts")
            self.assertEqual(json_records[1]["url"], "https://mirror.example/ubuntu.iso")
            self.assertEqual(json_records[1]["error"], "403 Forbidden")


if __name__ == "__main__":
    unittest.main()
