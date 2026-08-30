import os
import sqlite3
import sys
import tempfile
import unittest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from cache_recovery import inspect_sqlite_database, quarantine_corrupt_sqlite


class TestCacheRecovery(unittest.TestCase):
    def test_inspection_is_read_only_for_corrupt_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cache.sqlite3")
            original = b"not a sqlite database"
            with open(path, "wb") as handle:
                handle.write(original)

            diagnosis = inspect_sqlite_database(path)

            self.assertTrue(diagnosis["exists"])
            self.assertFalse(diagnosis["readable"])
            self.assertTrue(any(marker in diagnosis["error"] for marker in ("malformed", "not a database")))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), original)

    def test_quarantine_preserves_corrupt_files_and_recreates_valid_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cache.sqlite3")
            with open(path, "wb") as handle:
                handle.write(b"not a sqlite database")
            with open(path + "-wal", "wb") as handle:
                handle.write(b"wal-content")
            with open(path + "-shm", "wb") as handle:
                handle.write(b"shm-content")

            result = quarantine_corrupt_sqlite(path)

            self.assertTrue(result["recreated"])
            self.assertEqual(len(result["moved_files"]), 3)
            self.assertEqual(inspect_sqlite_database(path)["integrity"], "ok")
            self.assertTrue(all(os.path.exists(item) for item in result["moved_files"]))
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE smoke (value TEXT)")
            connection.commit()
            connection.close()

    def test_integral_database_is_never_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cache.sqlite3")
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE smoke (value TEXT)")
            connection.commit()
            connection.close()

            with self.assertRaises(ValueError):
                quarantine_corrupt_sqlite(path)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
