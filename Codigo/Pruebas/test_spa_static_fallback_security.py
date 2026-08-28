import os
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
import spa_crawler


class _Response:
    def __init__(self, *, status_code=200, headers=None, chunks=(), encoding="utf-8"):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks
        self.encoding = encoding
        self.closed = False

    @property
    def is_redirect(self):
        return self.status_code in {301, 302, 303, 307, 308}

    @property
    def is_permanent_redirect(self):
        return self.status_code in {301, 308}

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True


class TestSpaStaticFallbackSecurity(unittest.TestCase):
    def test_redirect_outside_institution_is_rejected_before_fetching_it(self):
        redirect = _Response(status_code=302, headers={"Location": "https://example.invalid/payload"})
        crawler = spa_crawler.SPALayoutCrawler()
        with patch.object(spa_crawler, "RESPECT_ROBOTS", False), patch.object(spa_crawler.requests, "get", return_value=redirect) as get:
            result = crawler._static_fallback_render("https://www.universidad.es/plan")

        self.assertEqual(str(result), "")
        self.assertEqual(get.call_count, 1)
        self.assertTrue(redirect.closed)

    def test_oversized_stream_is_rejected(self):
        response = _Response(headers={"Content-Type": "text/html"}, chunks=[b"x" * 11])
        crawler = spa_crawler.SPALayoutCrawler()
        with patch.object(spa_crawler, "RESPECT_ROBOTS", False), \
             patch.object(spa_crawler, "MAX_TEXT_RESPONSE_SIZE_BYTES", 10), \
             patch.object(spa_crawler.requests, "get", return_value=response):
            result = crawler._static_fallback_render("https://www.universidad.es/plan")

        self.assertEqual(str(result), "")


if __name__ == "__main__":
    unittest.main()
