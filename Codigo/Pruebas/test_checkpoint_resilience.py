import json
import os
import sys
import tempfile
import unittest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from checkpoint import CheckpointManager


class TestCheckpointResilience(unittest.TestCase):
    def test_corrupt_database_falls_back_to_json_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "corrupt.sqlite3")
            json_path = os.path.join(directory, "checkpoint.json")
            with open(db_path, "wb") as handle:
                handle.write(b"not a sqlite database")

            manager = CheckpointManager(filepath=json_path, db_path=db_path)
            try:
                manager.mark_universities_downloaded()
                manager.mark_university_processed("001")
                manager.update_degree_record("D-1", "https://boe.example/D-1", "2026-01-01", "2026-08-29")
                manager.mark_robots_denied_university("001", "https://uni.example")
                manager.flush()
            finally:
                manager.close()

            self.assertFalse(manager._sqlite_disabled)
            self.assertTrue(manager.sqlite_recovered_corrupt_path)
            self.assertTrue(os.path.exists(manager.sqlite_recovered_corrupt_path))
            self.assertTrue(os.path.exists(db_path))

            with open(json_path, encoding="utf-8") as handle:
                state = json.load(handle)
            self.assertTrue(state["universities_downloaded"])
            self.assertIn("001", state["processed_universities"])
            self.assertIn("D-1", state["processed_degrees"])
            self.assertIn("001", state["robots_denied_universities"])
            with open(manager.sqlite_recovered_corrupt_path, "rb") as handle:
                self.assertEqual(handle.read(), b"not a sqlite database")

    def test_instances_do_not_share_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "checkpoint.sqlite3")
            json_a = os.path.join(directory, "a.json")
            json_b = os.path.join(directory, "b.json")
            manager_a = CheckpointManager(filepath=json_a, db_path=db_path)
            manager_b = CheckpointManager(filepath=json_b, db_path=db_path)
            try:
                manager_a.mark_university_processed("001")
                manager_b.close()
                manager_a.mark_university_processed("002")
                self.assertTrue(manager_a.is_university_processed("001"))
                self.assertTrue(manager_a.is_university_processed("002"))
            finally:
                manager_a.close()

    def test_unusable_parent_disables_sqlite_but_keeps_json_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = os.path.join(directory, "not_a_directory")
            with open(blocked_parent, "wb") as handle:
                handle.write(b"blocker")
            manager = CheckpointManager(
                filepath=os.path.join(directory, "checkpoint.json"),
                db_path=os.path.join(blocked_parent, "checkpoint.sqlite3"),
            )
            try:
                manager.mark_university_processed("003")
                manager.flush()
                self.assertTrue(manager._sqlite_disabled)
                self.assertTrue(manager.is_university_processed("003"))
            finally:
                manager.close()


if __name__ == "__main__":
    unittest.main()
