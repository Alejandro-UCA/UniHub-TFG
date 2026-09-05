import unittest

from bs4 import BeautifulSoup

from parsers.boe_pdf import extract_degree_core_keywords
from pipelines.parte2_web_crawler import is_html_page_matching_degree


class MultilingualIdentityTests(unittest.TestCase):
    def test_replacement_character_does_not_turn_master_into_subject_keyword(self):
        keywords = extract_degree_core_keywords(
            "M�ster Universitario en Estudios Literarios",
            "Universidad de Prueba",
        )

        self.assertNotIn("mster", keywords)
        self.assertNotIn("master", keywords)
        self.assertIn("literarios", keywords)

    def test_spanish_catalog_title_matches_catalan_official_page(self):
        soup = BeautifulSoup(
            "<html><head><title>Màster Universitari en Estudis Literaris</title></head>"
            "<body><h1>Pla d'estudis</h1></body></html>",
            "html.parser",
        )

        self.assertTrue(
            is_html_page_matching_degree(
                soup,
                "M�ster Universitario en Estudios Literarios",
                "Universidad de Prueba",
                "https://example.edu/masteres/estudios-literarios/plan-de-estudios.html",
                allow_curriculum_url_identity=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
