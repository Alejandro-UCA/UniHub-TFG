import os
import sys
import unittest
from unittest.mock import MagicMock, patch


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

    def test_browser_launch_and_page_operations_share_render_timeout(self):
        crawler = spa_crawler.SPALayoutCrawler(timeout=7)
        browser = MagicMock()
        browser.is_connected.return_value = True
        context = MagicMock()
        page = MagicMock()
        page.content.return_value = "<html></html>"
        context.new_page.return_value = page
        browser.new_context.return_value = context

        with patch.object(spa_crawler, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(crawler, "_ensure_browser", return_value=browser), \
             patch.object(crawler._robots_policy, "check", return_value=(True, None)):
            crawler.render_spa_page("https://universidad.example/plan")

        expected_timeout = 7_000
        context.set_default_timeout.assert_called_once_with(expected_timeout)
        context.set_default_navigation_timeout.assert_called_once_with(expected_timeout)
        page.set_default_timeout.assert_called_once_with(expected_timeout)
        page.set_default_navigation_timeout.assert_called_once_with(expected_timeout)

    def test_browser_launch_receives_render_timeout(self):
        crawler = spa_crawler.SPALayoutCrawler(timeout=7)
        playwright = MagicMock()
        playwright.chromium.launch.return_value = MagicMock()
        with patch.object(spa_crawler, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(spa_crawler, "sync_playwright") as sync:
            sync.return_value.start.return_value = playwright
            crawler._ensure_browser()

        self.assertEqual(playwright.chromium.launch.call_args.kwargs["timeout"], 7_000)


if __name__ == "__main__":
    unittest.main()
