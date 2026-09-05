import hashlib
import tempfile
import unittest
from pathlib import Path

from in_memory_web_snapshot import (
    InMemoryWebSnapshot,
    SnapshotEntry,
    SnapshotMiss,
    SnapshotDownloader,
    assert_snapshot_only,
)


class TestInMemoryWebSnapshot(unittest.TestCase):

    def test_round_trip_is_hash_verified_and_network_free(self):
        body = b"<html><table><tr><td>source</td></tr></table></html>"
        entry = SnapshotEntry(
            url="https://example.test/plan",
            final_url="https://example.test/plan",
            status_code=200,
            content_type="text/html",
            sha256=hashlib.sha256(body).hexdigest(),
            byte_length=len(body),
            relative_path="bodies/example.html",
        )
        with tempfile.TemporaryDirectory() as directory:
            snapshot = InMemoryWebSnapshot()
            snapshot.add(entry, body)
            snapshot.save_directory(directory)
            loaded = InMemoryWebSnapshot().load_directory(directory)
            self.assertEqual(loaded.content(entry.url), body)
            self.assertEqual(loaded.network_calls, 0)
            assert_snapshot_only(loaded)

    def test_missing_url_is_explicit_and_does_not_fallback_to_network(self):
        snapshot = InMemoryWebSnapshot()
        with self.assertRaises(SnapshotMiss):
            snapshot.get("https://not-in-corpus.test/plan")
        self.assertEqual(snapshot.network_calls, 0)

    def test_snapshot_downloader_implements_crawler_surface_without_network(self):
        body = b"<html>snapshot</html>"
        entry = SnapshotEntry(
            url="https://example.test/page",
            final_url="https://example.test/page",
            status_code=200,
            content_type="text/html",
            sha256=hashlib.sha256(body).hexdigest(),
            byte_length=len(body),
            relative_path="bodies/page.html",
        )
        snapshot = InMemoryWebSnapshot()
        snapshot.add(entry, body)
        downloader = SnapshotDownloader(snapshot)
        self.assertEqual(downloader.fetch_text(entry.url), "<html>snapshot</html>")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "page.html"
            downloader.download_file(entry.url, str(target))
            self.assertEqual(target.read_bytes(), body)
        with self.assertRaises(SnapshotMiss):
            downloader.fetch_text("https://example.test/missing")
        self.assertEqual(snapshot.network_calls, 0)


if __name__ == "__main__":
    unittest.main()
