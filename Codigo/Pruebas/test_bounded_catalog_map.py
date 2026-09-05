import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from pipelines.parte2_web_crawler import merge_bounded_catalog_map


class TestBoundedCatalogMap(unittest.TestCase):
    def test_global_url_cap_applies_across_multiple_origins(self):
        target = {}
        first = {"alpha": [("https://one.example/1", "A"), ("https://one.example/2", "B")]}
        second = {"beta": [("https://two.example/1", "C"), ("https://two.example/2", "D")]}

        self.assertEqual(merge_bounded_catalog_map(target, first, max_indexed_urls=3), 2)
        self.assertEqual(merge_bounded_catalog_map(target, second, max_indexed_urls=3), 1)
        urls = {
            str(item[0])
            for entries in target.values()
            for item in entries
        }
        self.assertEqual(urls, {
            "https://one.example/1",
            "https://one.example/2",
            "https://two.example/1",
        })

    def test_deduplicates_urls_per_token_and_keeps_existing_priority(self):
        target = {"plan": [("https://official.example/plan", "official")]}
        incoming = {
            "plan": [
                ("https://official.example/plan/", "duplicate"),
                ("https://other.example/plan", "later"),
            ]
        }

        added = merge_bounded_catalog_map(target, incoming, max_indexed_urls=5, max_links_per_token=2)

        self.assertEqual(added, 1)
        self.assertEqual(
            [item[0] for item in target["plan"]],
            ["https://official.example/plan", "https://other.example/plan"],
        )

    def test_token_cap_does_not_create_unbounded_lists(self):
        target = {}
        incoming = {
            "same": [(f"https://example.test/{index}", str(index)) for index in range(10)]
        }

        merge_bounded_catalog_map(target, incoming, max_indexed_urls=10, max_links_per_token=3)

        self.assertEqual(len(target["same"]), 3)


if __name__ == "__main__":
    unittest.main()
