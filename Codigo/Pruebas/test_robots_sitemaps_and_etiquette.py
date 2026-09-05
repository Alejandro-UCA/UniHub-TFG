import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from core.robots_policy import RobotsPolicy
from core.downloader import WebDownloader


class _DummyRobotsResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": "text/plain"}

    def close(self):
        pass


class TestRobotsSitemapsAndEtiquette(unittest.TestCase):
    def setUp(self):
        RobotsPolicy.clear_cache()
        WebDownloader._GLOBAL_DOMAIN_DELAYS.clear()

    def test_robots_sitemap_extraction(self):
        robots_content = """
        User-agent: *
        Disallow: /admin/
        Crawl-delay: 5

        Sitemap: https://portal.univ.es/sitemap_index.xml
        Sitemap: https://portal.univ.es/sitemap_grados.xml
        """
        policy = RobotsPolicy()
        with patch("requests.get", return_value=_DummyRobotsResponse(robots_content)):
            sitemaps = policy.get_sitemaps("https://portal.univ.es/estudios")
            self.assertEqual(len(sitemaps), 2)
            self.assertIn("https://portal.univ.es/sitemap_index.xml", sitemaps)
            self.assertIn("https://portal.univ.es/sitemap_grados.xml", sitemaps)

    def test_crawl_delay_capped(self):
        # Excesivo crawl delay en robots.txt debe ser acotado a 60s max
        robots_content = """
        User-agent: *
        Crawl-delay: 9999
        Disallow:
        """
        policy = RobotsPolicy()
        with patch("requests.get", return_value=_DummyRobotsResponse(robots_content)):
            allowed, delay = policy.check("https://slow.univ.es/index.html")
            self.assertTrue(allowed)
            self.assertEqual(delay, 60.0)

    def test_downloader_etiquette_headers(self):
        downloader = WebDownloader(respect_robots=False)
        self.assertEqual(downloader.session.headers.get("From"), "contacto@unihub.es")
        self.assertIn("gzip", downloader.session.headers.get("Accept-Encoding", ""))
        self.assertIn("br", downloader.session.headers.get("Accept-Encoding", ""))

    def test_proactive_ratelimit_header_backoff(self):
        downloader = WebDownloader(respect_robots=False, delay=1.0, enable_http2=False)
        target_url = "https://api.univ.es/catalog"

        dummy_resp = MagicMock()
        dummy_resp.status_code = 200
        dummy_resp.url = target_url
        dummy_resp.headers = {"X-RateLimit-Remaining": "1"}
        dummy_resp.text = "OK"
        dummy_resp.content = b"OK"
        dummy_resp._unihub_cached = False

        with patch.object(downloader.session, "get", return_value=dummy_resp):
            resp = downloader._request_with_retry(target_url)
            self.assertEqual(resp.status_code, 200)

            # El auto-freno de cortesía debió aumentar el delay del dominio api.univ.es
            adjusted_delay = WebDownloader._GLOBAL_DOMAIN_DELAYS.get("api.univ.es")
            self.assertIsNotNone(adjusted_delay)
            self.assertGreater(adjusted_delay, 1.0)


if __name__ == "__main__":
    unittest.main()
