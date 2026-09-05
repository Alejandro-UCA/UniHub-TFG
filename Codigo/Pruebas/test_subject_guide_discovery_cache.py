import os
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import extractors.subject_guides as discovery


class _Robots:
    def check(self, _url):
        return True, None


class _Downloader:
    def __init__(self):
        self.robots_policy = _Robots()
        self.fetches = []

    def fetch_content(self, url, max_size_bytes=None):
        self.fetches.append((url, max_size_bytes))
        if url.endswith("robots.txt"):
            return b"Sitemap: https://uni.example/sitemap.xml\n"
        return b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://uni.example/guias/algebra-1234</loc></url>
        </urlset>"""


class TestSubjectGuideDiscoveryCache(unittest.TestCase):
    def test_discovery_index_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            first_downloader = _Downloader()
            second_downloader = _Downloader()
            patches = [
                patch.object(discovery, "SUBJECT_GUIDE_DISCOVERY_CACHE_DIR", directory),
                patch.object(discovery, "SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS", 3600),
            ]
            for item in patches:
                item.start()
            try:
                first = discovery.build_subject_guide_discovery_index(
                    first_downloader,
                    "https://uni.example",
                    max_roots=1,
                    max_files=3,
                    max_urls=10,
                )
                second = discovery.build_subject_guide_discovery_index(
                    second_downloader,
                    "https://uni.example",
                    max_roots=1,
                    max_files=3,
                    max_urls=10,
                )
            finally:
                for item in reversed(patches):
                    item.stop()

            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertGreater(len(first_downloader.fetches), 0)
            self.assertEqual(second_downloader.fetches, [])
            self.assertEqual(second["urls"], first["urls"])


if __name__ == "__main__":
    unittest.main()
