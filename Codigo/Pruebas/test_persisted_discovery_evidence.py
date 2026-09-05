import unittest

from pipelines.parte2_web_crawler import merge_persisted_discovery_evidence


class PersistedDiscoveryEvidenceTests(unittest.TestCase):
    def test_merges_generic_evidence_and_prioritizes_it(self):
        catalog = {"plan": [("https://example.edu/general", "Oferta académica")]}
        evidence = [{
            "url": "https://example.edu/masteres/plan-de-estudios/energia",
            "title": "Plan de estudios de Energía",
            "anchor_text": "Plan de estudios",
        }]

        added = merge_persisted_discovery_evidence(catalog, evidence)

        self.assertEqual(added, 1)
        self.assertEqual(catalog["plan"][0][0], evidence[0]["url"])
        self.assertIn("energia", catalog)

    def test_deduplicates_and_enforces_global_and_token_caps(self):
        catalog = {}
        evidence = [
            {"url": f"https://example.edu/plan-{index}", "title": "Plan estudios"}
            for index in range(5)
        ]

        added = merge_persisted_discovery_evidence(
            catalog,
            evidence + [evidence[0]],
            max_indexed_urls=3,
            max_links_per_token=2,
        )

        self.assertEqual(added, 3)
        self.assertLessEqual(len({entry[0] for entry in catalog["plan"]}), 2)

    def test_rejects_invalid_and_historical_urls(self):
        catalog = {}
        evidence = [
            {"url": "mailto:info@example.edu", "title": "Plan estudios"},
            {"url": "https://example.edu/historico/plan-estudios", "title": "Plan estudios"},
        ]

        self.assertEqual(merge_persisted_discovery_evidence(catalog, evidence), 0)
        self.assertEqual(catalog, {})


if __name__ == "__main__":
    unittest.main()
