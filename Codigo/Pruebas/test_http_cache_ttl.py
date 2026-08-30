import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import requests

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import downloader as downloader_module
from crawl_ledger import CrawlLedger
from downloader import RUCTDownloader


class TestHttpCacheTtl(unittest.TestCase):
    def test_repeated_content_request_is_served_from_bounded_run_memo(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(os.path.join(directory, "ledger.sqlite3"))
            metrics = MagicMock()
            downloader = RUCTDownloader(
                ledger=ledger,
                metrics_tracker=metrics,
                respect_robots=False,
                delay=0,
                max_retries=1,
                enable_http2=False,
            )
            url = "https://example.test/repeated.txt"
            response = requests.Response()
            response.status_code = 200
            response.url = url
            response.headers["Content-Type"] = "text/plain"
            response._content = b"same body"
            response._content_consumed = True
            response.encoding = "utf-8"
            with patch.object(downloader_module, "HTTP_CACHE_DIR", directory), \
                 patch.object(downloader_module, "HTTP_RUN_MEMO_MAX_BYTES", 1024):
                downloader.session.get = MagicMock(return_value=response)
                self.assertEqual(downloader.fetch_content(url), b"same body")
                self.assertEqual(downloader.fetch_content(url), b"same body")
                self.assertEqual(downloader.session.get.call_count, 1)
                metrics.record_request_memo_hit.assert_called_once()
            downloader.close()
            ledger.close()

    def test_fresh_cache_sends_validators_and_expired_cache_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = CrawlLedger(os.path.join(directory, "ledger.sqlite3"))
            try:
                url = "https://example.test/guide.pdf"
                ledger.record_attempt(url, phase="test")
                downloader = RUCTDownloader(
                    ledger=ledger,
                    respect_robots=False,
                    delay=0,
                    max_retries=1,
                    enable_http2=False,
                )
                with patch.object(downloader_module, "HTTP_CACHE_DIR", directory), \
                     patch.object(downloader_module, "HTTP_CACHE_TTL_SECONDS", 3600):
                    stored = MagicMock(status_code=200, headers={"ETag": '"v1"'})
                    stored._unihub_cached = False
                    downloader.store_response_content(url, stored, b"%PDF fresh")
                    downloader._run_response_memo.clear()
                    downloader._run_response_memo_bytes = 0

                    fresh_response = MagicMock(status_code=200, headers={}, url=url)
                    fresh_response.raise_for_status.return_value = None
                    downloader.session.get = MagicMock(return_value=fresh_response)
                    downloader._request_with_retry(url)
                    fresh_headers = downloader.session.get.call_args.kwargs["headers"]
                    self.assertEqual(fresh_headers["If-None-Match"], '"v1"')

                    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
                    conn = ledger._connection()
                    conn.execute(
                        "UPDATE crawl_ledger SET cache_updated_at = ? WHERE url = ?",
                        (old, url),
                    )
                    conn.commit()

                    stale_response = MagicMock(status_code=200, headers={}, url=url)
                    stale_response.raise_for_status.return_value = None
                    downloader.session.get = MagicMock(return_value=stale_response)
                    downloader._request_with_retry(url)
                    stale_headers = downloader.session.get.call_args.kwargs["headers"] or {}
                    self.assertNotIn("If-None-Match", stale_headers)
                downloader.close()
            finally:
                ledger.close()


if __name__ == "__main__":
    unittest.main()
