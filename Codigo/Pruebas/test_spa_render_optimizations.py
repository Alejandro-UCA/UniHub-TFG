import os
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
import spa_crawler


class TestSpaRenderOptimizations(unittest.TestCase):
    def setUp(self):
        spa_crawler.SPALayoutCrawler.clear_render_cache()

    def tearDown(self):
        spa_crawler.SPALayoutCrawler.clear_render_cache()

    def test_static_fallback_is_cached_for_repeated_url(self):
        crawler = spa_crawler.SPALayoutCrawler()
        fallback_result = spa_crawler.RenderResult("<html><body>plan</body></html>")
        with patch.object(spa_crawler, "PLAYWRIGHT_AVAILABLE", False), \
             patch.object(crawler, "_static_fallback_render", return_value=fallback_result) as fallback:
            first = crawler.render_spa_page("https://universidad.example/plan")
            second = crawler.render_spa_page("https://universidad.example/plan")

        self.assertEqual(first, second)
        self.assertIs(first, second)
        fallback.assert_called_once_with("https://universidad.example/plan")

    def test_empty_render_is_not_cached(self):
        crawler = spa_crawler.SPALayoutCrawler()
        with patch.object(spa_crawler, "PLAYWRIGHT_AVAILABLE", False), \
             patch.object(crawler, "_static_fallback_render", return_value=spa_crawler.RenderResult("")) as fallback:
            crawler.render_spa_page("https://universidad.example/empty")
            crawler.render_spa_page("https://universidad.example/empty")

        self.assertEqual(fallback.call_count, 2)


if __name__ == "__main__":
    unittest.main()
