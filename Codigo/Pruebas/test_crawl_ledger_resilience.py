import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
import core.crawl_ledger as ledger_module
from core.crawl_ledger import CrawlLedger


class TestCrawlLedgerResilience(unittest.TestCase):
    def test_default_ledger_storage_is_separate_from_checkpoint_storage(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("config.CACHE_DB_PATH", os.path.join(directory, "checkpoint.sqlite3")), \
             patch.dict(os.environ, {"CRAWLER_LEDGER_DB_PATH": ""}, clear=False):
            ledger = CrawlLedger()
            try:
                self.assertNotEqual(
                    os.path.abspath(ledger.db_path),
                    os.path.abspath(os.path.join(directory, "checkpoint.sqlite3")),
                )
                self.assertTrue(ledger.db_path.endswith("crawl_ledger.sqlite3"))
            finally:
                ledger.close()

    def test_corrupt_database_is_quarantined_and_recreated(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "corrupt.sqlite3")
            with open(db_path, "wb") as handle:
                handle.write(b"not a sqlite database")

            ledger = CrawlLedger(db_path=db_path)
            try:
                ledger.record_attempt("https://www.uca.es/estudios", phase="test")

                self.assertFalse(ledger._disabled)
                self.assertTrue(ledger.recovered_corrupt_path)
                self.assertTrue(os.path.exists(ledger.recovered_corrupt_path))
                self.assertEqual(
                    ledger.pending(phase="test")[0]["url"],
                    "https://www.uca.es/estudios",
                )
                with open(ledger.recovered_corrupt_path, "rb") as handle:
                    self.assertEqual(handle.read(), b"not a sqlite database")
            finally:
                ledger.close()

    def test_unusable_parent_directory_disables_the_ledger_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = os.path.join(directory, "not_a_directory")
            with open(blocked_parent, "wb") as handle:
                handle.write(b"blocker")

            ledger = CrawlLedger(db_path=os.path.join(blocked_parent, "ledger.sqlite3"))

            self.assertTrue(ledger._disabled)
            self.assertEqual(ledger.pending(), [])

    def test_writes_are_committed_in_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(db_path=os.path.join(directory, "ledger.sqlite3"))
            try:
                conn = ledger._connection()
                commits = []
                conn.set_trace_callback(lambda statement: commits.append(statement) if statement == "COMMIT" else None)
                with patch.object(ledger_module, "LEDGER_WRITE_BATCH_SIZE", 3):
                    for index in range(3):
                        ledger.record_attempt(f"https://example.test/{index}", phase="test")
                    self.assertEqual(commits.count("COMMIT"), 1)
            finally:
                ledger.close()

    def test_robots_denial_is_terminal_and_not_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(db_path=os.path.join(directory, "ledger.sqlite3"))
            try:
                url = "https://robots.example/blocked.pdf"
                ledger.record_attempt(url, phase="fase1_parte1")
                ledger.mark_robots_denied(url, "denegado_por_reglas")
                row = ledger._connection().execute(
                    "SELECT status, robots_allowed, next_retry, error FROM crawl_ledger WHERE url=?", (url,)
                ).fetchone()
                self.assertEqual(row, ("robots_denied", 0, None, "denegado_por_reglas"))
                self.assertEqual(ledger.pending(phase="fase1_parte1"), [])
            finally:
                ledger.close()

    def test_reconcile_processing_closes_orphaned_attempts_by_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(db_path=os.path.join(directory, "ledger.sqlite3"))
            try:
                ledger.record_attempt("https://example.test/part1", phase="fase1_parte1")
                ledger.record_attempt("https://example.test/part2", phase="fase1_parte2_web")
                ledger.record_attempt("https://example.test/other", phase="fase2")
                closed = ledger.reconcile_processing(
                    phase_prefix="fase1_parte2",
                    reason="worker interrumpido",
                )
                self.assertEqual(closed, 1)
                rows = ledger._connection().execute(
                    "SELECT url, status, next_retry, error FROM crawl_ledger ORDER BY url"
                ).fetchall()
                rows_by_url = {row[0]: row[1:] for row in rows}
                self.assertEqual(
                    rows_by_url["https://example.test/part2"],
                    ("cancelled", None, "worker interrumpido"),
                )
                self.assertEqual(ledger.pending(phase="fase1_parte2_web"), [])
                self.assertEqual(ledger.pending(phase="fase1_parte1")[0]["url"], "https://example.test/part1")
            finally:
                ledger.close()

    def test_shared_ledger_flushes_thread_connections_without_cross_thread_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(db_path=os.path.join(directory, "ledger.sqlite3"))
            errors = []

            def worker(index):
                try:
                    ledger.record_attempt(f"https://parallel.example/{index}", phase="test")
                    ledger.record_response(
                        f"https://parallel.example/{index}",
                        status="success",
                    )

                    # Fuerza el camino que antes intentaba confirmar conexiones
                    # creadas por otros hilos.
                    ledger.pending(phase="test", limit=100)
                except Exception as error:
                    errors.append(error)

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            try:
                self.assertEqual(errors, [])
                self.assertEqual(ledger.pending(phase="test", limit=100), [])
            finally:
                ledger.close()

    def test_discovery_evidence_is_idempotent_and_preserves_richer_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(db_path=os.path.join(directory, "ledger.sqlite3"))
            try:
                url = "https://uni.example/guia/algebra-1.pdf"
                first = ledger.record_discovery_evidence(
                    [{"url": url, "source_kind": "sitemap", "source_url": "https://uni.example/sitemap.xml"}],
                    university_code="999",
                    phase="fase1_parte2_web",
                )
                second = ledger.record_discovery_evidence(
                    [{"url": url, "source_kind": "catalog", "anchor_text": "Álgebra I", "lastmod": "2026-08-31"}],
                    university_code="999",
                    phase="fase1_parte2_web",
                )

                records = ledger.get_discovery_evidence("999")

                self.assertEqual(first, 1)
                self.assertEqual(second, 1)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["anchor_text"], "Álgebra I")
                self.assertEqual(records[0]["source_url"], "https://uni.example/sitemap.xml")
                self.assertEqual(records[0]["lastmod"], "2026-08-31")
            finally:
                ledger.close()


if __name__ == "__main__":
    unittest.main()
