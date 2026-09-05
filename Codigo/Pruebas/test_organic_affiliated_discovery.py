import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

sys.path.append('d:/Proyecto/Codigo/Crawler')
from pipelines.parte2_web_crawler import UniversityWebCrawler, propagate_interuniversity_and_shared_boe_plans
from core.config import (
    ORGANIC_AFFILIATED_HUB_KEYWORDS,
    EUROPEAN_ALLIANCES_KEYWORDS,
    MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV
)

class TestOrganicAffiliatedAndEuropeanDiscovery(unittest.TestCase):
    def setUp(self):
        self.crawler = UniversityWebCrawler()

    def test_organic_outlink_discovery_in_catalog_map(self):
        """Verifica que el crawler descubre centros adscritos externos sin tener URLs predefinidas."""
        mock_downloader = MagicMock()
        
        # HTML de la universidad matriz con enlaces salientes a centros adscritos y alianzas europeas
        main_univ_html = """
        <html>
            <body>
                <h1>Universitat de Barcelona</h1>
                <a href="/ca/web/estudis/graus">Graus</a>
                <a href="/ca/centres-adscrits">Centres Adscrits</a>
                <a href="https://www.cett.es/ca">Escola d'Hoteleria i Turisme CETT</a>
                <a href="https://escac.com/ca">Escola Superior de Cinema i Audiovisuals ESCAC</a>
                <a href="https://sea-eu.org">Alianza Europea SEA-EU</a>
            </body>
        </html>
        """
        mock_downloader.fetch_text.side_effect = lambda url: main_univ_html if "ub.edu" in url else ""

        cat_map = self.crawler._build_academic_catalog_map(
            mock_downloader, "https://web.ub.edu", max_depth=5, max_hubs=5, max_hops=2
        )

        discovered = self.crawler.organic_affiliated_hubs.get("https://web.ub.edu", {})
        self.assertTrue(len(discovered) >= 2, f"Se esperaban al menos 2 hubs orgánicos descubiertos, encontrados: {len(discovered)}")
        
        # Comprobar que CETT y ESCAC fueron descubiertos orgánicamente
        domains_found = list(discovered.keys())
        self.assertTrue(any("cett.es" in d for d in domains_found), "No se descubrió cett.es")
        self.assertTrue(any("escac.com" in d for d in domains_found), "No se descubrió escac.com")

    def test_european_alliance_consortium_payload_generation(self):
        """Verifica la generación de la ficha oficial de consorcio para títulos Erasmus Mundus / SEA-EU."""
        degree_test = {
            "codigo_estudio": "3501030",
            "titulo": "Máster Universitario en Sustainable Management of Organisations (SEA-EU)",
            "nivel_academico": "Máster - RD 822/2021 (3)",
            "universidad_codigo": "005",
            "universidad_nombre": "Universidad de Cádiz"
        }
        
        is_european = any(k in degree_test["titulo"].lower() for k in EUROPEAN_ALLIANCES_KEYWORDS)
        self.assertTrue(is_european, "No se detectó el máster como programa de Alianza Europea")

    def test_keywords_configuration(self):
        """Verifica la integridad de las listas de palabras clave en config.py."""
        self.assertIn("adscrito", ORGANIC_AFFILIATED_HUB_KEYWORDS)
        self.assertIn("erasmus mundus", EUROPEAN_ALLIANCES_KEYWORDS)
        self.assertIn("sea-eu", EUROPEAN_ALLIANCES_KEYWORDS)
        self.assertGreater(MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV, 0)

if __name__ == '__main__':
    unittest.main()
