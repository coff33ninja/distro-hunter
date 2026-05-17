import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from distro_hunter.backup import create_source_backup


class BackupTests(unittest.TestCase):
    def test_create_source_backup_skips_caches_and_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "distro_hunter").mkdir()
            (root / "downloads").mkdir()
            (root / "__pycache__").mkdir()
            (root / "distro_hunter" / "app.py").write_text("print('ok')", encoding="utf-8")
            (root / "downloads" / "large.iso.part").write_text("x", encoding="utf-8")
            (root / "__pycache__" / "app.pyc").write_bytes(b"cache")

            backup_path = create_source_backup(root)

            self.assertTrue(backup_path.exists())
            with ZipFile(backup_path) as archive:
                names = set(archive.namelist())

            self.assertIn("distro_hunter/app.py", names)
            self.assertNotIn("downloads/large.iso.part", names)
            self.assertNotIn("__pycache__/app.pyc", names)


if __name__ == "__main__":
    unittest.main()
