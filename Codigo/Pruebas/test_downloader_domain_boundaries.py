import os
import sys
import unittest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from downloader import RUCTDownloader, is_same_or_subdomain
from fase1_parte2_web_crawler import is_same_or_subdomain as web_crawler_is_same_or_subdomain


class TestDownloaderDomainBoundaries(unittest.TestCase):
    def test_different_top_level_domains_are_not_equivalent(self):
        self.assertFalse(is_same_or_subdomain("https://universidad.com/path", "https://universidad.es/origen"))
        self.assertFalse(web_crawler_is_same_or_subdomain("https://universidad.com/path", "https://universidad.es/origen"))

    def test_legitimate_sibling_subdomains_are_allowed(self):
        self.assertTrue(is_same_or_subdomain("https://quimicas.ub.edu/plan", "https://web.ub.edu/grados"))
        self.assertTrue(is_same_or_subdomain("https://campus.ucm.edu.es/plan", "https://www.ucm.edu.es/grados"))

    def test_request_variants_prioritize_www_without_losing_root_fallback(self):
        self.assertEqual(
            RUCTDownloader._request_url_variants("https://uniovi.es/estudios/plan"),
            [
                "https://www.uniovi.es/estudios/plan",
                "https://uniovi.es/estudios/plan",
            ],
        )
        self.assertEqual(
            RUCTDownloader._request_url_variants("https://www.upv.es/estudios/plan"),
            ["https://www.upv.es/estudios/plan"],
        )
        self.assertEqual(
            RUCTDownloader._request_url_variants("http://127.0.0.1:8000/plan"),
            ["http://127.0.0.1:8000/plan"],
        )


if __name__ == "__main__":
    unittest.main()
