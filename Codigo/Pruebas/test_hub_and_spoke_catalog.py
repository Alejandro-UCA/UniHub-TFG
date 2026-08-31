import unittest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup
import sys

sys.path.append('d:/Proyecto/Codigo/Crawler')
from univ_web_crawler import UniversityWebCrawler

class TestHubAndSpokeCatalog(unittest.TestCase):
    def setUp(self):
        self.crawler = UniversityWebCrawler()

    def test_hub_and_spoke_indexing_and_depth_bound(self):
        """Verifica que el indexador Hub-and-Spoke extraiga enlaces de catálogos y respete la cota de profundidad <= 6."""
        mock_downloader = MagicMock()

        # HTML de la portada principal con enlace al catálogo de másteres
        home_html = """
        <html>
            <body>
                <a href="/estudios/masteres">Catálogo de Másteres Universitarios</a>
                <a href="/grados">Oferta de Grados</a>
            </body>
        </html>
        """

        # HTML del catálogo de másteres con enlaces a fichas de titulaciones
        catalog_master_html = """
        <html>
            <body>
                <h1>Oferta de Másteres</h1>
                <a href="/estudios/masteres/master-en-psicologia-juridica-y-forense">Máster en Psicología Jurídica y Forense</a>
                <a href="/estudios/masteres/master-en-ciberseguridad-e-ia">Máster en Ciberseguridad e Inteligencia Artificial</a>
                <a href="/nivel1/nivel2/nivel3/nivel4/nivel5/nivel6/nivel7/titulo-profundo">Título Excesivamente Profundo (Depth 7)</a>
            </body>
        </html>
        """

        def mock_fetch(url):
            if "masteres" in url:
                return catalog_master_html
            return home_html

        mock_downloader.fetch_text.side_effect = mock_fetch

        catalog_map = self.crawler._build_academic_catalog_map(mock_downloader, "https://www.ugr.es", max_depth=6)

        # 1. Comprobar que indexó las titulaciones del catálogo
        self.assertIn("psicología", catalog_map)
        self.assertIn("forense", catalog_map)
        self.assertIn("ciberseguridad", catalog_map)

        # 2. Comprobar que la URL contiene el enlace correcto a la ficha
        urls_psico = [u for u, _ in catalog_map["psicología"]]
        self.assertTrue(any("psicologia-juridica-y-forense" in u for u in urls_psico))

        # 3. Comprobar que la URL con profundidad > 6 fue DESCARTADA
        self.assertNotIn("profundo", catalog_map)

    def test_part2_publishes_sitemap_and_catalog_evidence(self):
        fake_ledger = MagicMock()
        self.crawler.ledger = fake_ledger
        downloader = MagicMock()
        self.crawler.extract_sitemap_candidate_urls = MagicMock(
            return_value={"https://www.ugr.es/estudios/algebra"}
        )
        self.crawler._build_academic_catalog_map = MagicMock(
            return_value={
                "algebra": [("https://www.ugr.es/grado/algebra", "Grado en Álgebra")],
            }
        )

        self.crawler._crawl_university_degrees(
            downloader,
            "999",
            "Universidad de Prueba",
            "https://www.ugr.es",
            [],
            {},
        )

        self.assertEqual(fake_ledger.record_discovery_evidence.call_count, 2)
        sitemap_records = fake_ledger.record_discovery_evidence.call_args_list[0].args[0]
        catalog_records = fake_ledger.record_discovery_evidence.call_args_list[1].args[0]
        self.assertEqual(sitemap_records[0]["source_kind"], "sitemap")
        self.assertEqual(catalog_records[0]["source_kind"], "hub_catalog")
        self.assertEqual(catalog_records[0]["anchor_text"], "Grado en Álgebra")

if __name__ == "__main__":
    unittest.main()
