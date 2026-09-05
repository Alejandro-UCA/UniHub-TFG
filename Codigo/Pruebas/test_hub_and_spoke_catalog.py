import unittest
import json
import os
import tempfile
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
import sys

sys.path.append('d:/Proyecto/Codigo/Crawler')
import fase1_parte2_web_crawler as part2
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

    def test_direct_complete_source_skips_expensive_discovery_index(self):
        """La evidencia curricular directa debe evaluarse antes de abrir hubs."""
        rows = "".join(
            f"<tr><td>Asignatura {index}</td><td>6 ECTS</td></tr>"
            for index in range(40)
        )
        source_url = "https://catalog.example.edu/grados/ciencias-datos"
        html = f"<h1>Grado en Ciencias de Datos</h1><table><tr><th>Asignatura</th><th>ECTS</th></tr>{rows}</table>"
        downloader = MagicMock()
        downloader.fetch_text.return_value = html
        self.crawler._build_academic_catalog_map = MagicMock(return_value={})
        self.crawler.extract_sitemap_candidate_urls = MagicMock(return_value=set())
        degree = {
            "codigo_estudio": "TEST-DIRECT",
            "titulo": "Grado en Ciencias de Datos",
            "nivel_academico": "Grado",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "degree.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                json.dump({**degree, "web_fuente_directa_url": source_url}, handle)
            with patch("fase1_parte2_web_crawler.find_plan_filepath", return_value=plan_path), \
                 patch("fase1_parte2_web_crawler.is_html_page_matching_degree", return_value=True):
                self.crawler._crawl_university_degrees(
                    downloader,
                    "999",
                    "Universidad de Prueba",
                    "https://catalog.example.edu",
                    [degree],
                    {"resolved_degrees_count": 0},
                )
        self.crawler._build_academic_catalog_map.assert_not_called()

    def test_direct_spa_source_renders_before_expensive_discovery(self):
        """Una ficha directa SPA se resuelve antes de abrir índices generales."""
        source_url = "https://catalog.example.edu/grados/ciencias-datos"
        static_html = "<h1>Grado en Ciencias de Datos</h1><div id='app'></div>"
        rows = "".join(
            f"<tr><td>Asignatura {index}</td><td>6 ECTS</td></tr>"
            for index in range(40)
        )
        rendered_html = (
            "<h1>Grado en Ciencias de Datos</h1><table>"
            "<tr><th>Asignatura</th><th>ECTS</th></tr>"
            f"{rows}</table>"
        )
        downloader = MagicMock()
        downloader.fetch_text.return_value = static_html
        self.crawler._build_academic_catalog_map = MagicMock(return_value={})
        self.crawler.extract_sitemap_candidate_urls = MagicMock(return_value=set())
        degree = {
            "codigo_estudio": "TEST-DIRECT-SPA",
            "titulo": "Grado en Ciencias de Datos",
            "nivel_academico": "Grado",
        }
        spa_instance = MagicMock()
        spa_instance.render_spa_page.return_value = rendered_html
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "degree.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                json.dump({**degree, "web_fuente_directa_url": source_url}, handle)
            with patch("fase1_parte2_web_crawler.find_plan_filepath", return_value=plan_path), \
                 patch("fase1_parte2_web_crawler.is_html_page_matching_degree", return_value=True), \
                 patch("spa_crawler.SPALayoutCrawler.get_shared_instance", return_value=spa_instance):
                self.crawler._crawl_university_degrees(
                    downloader,
                    "999",
                    "Universidad de Prueba",
                    "https://catalog.example.edu",
                    [degree],
                    {"resolved_degrees_count": 0},
                )
        spa_instance.render_spa_page.assert_called_once_with(source_url)
        self.crawler._build_academic_catalog_map.assert_not_called()

    def test_low_priority_navigation_does_not_consume_hub_budget(self):
        """Los enlaces genéricos no desplazan al subcatálogo académico relevante."""
        downloader = MagicMock()
        generic_links = "".join(
            f'<a href="/servicios/{index}">Servicio institucional {index}</a>'
            for index in range(12)
        )
        home_html = (
            '<a href="/estudios/masteres">Oferta de Másteres</a>'
            + generic_links
        )
        catalog_html = '<a href="/estudios/masteres/master-en-datos">Máster en Datos</a>'

        def mock_fetch(url):
            if url.endswith("/estudios/masteres"):
                return catalog_html
            return home_html

        downloader.fetch_text.side_effect = mock_fetch
        catalog_map = self.crawler._build_academic_catalog_map(
            downloader,
            "https://www.example.edu",
            max_hubs=2,
            max_hops=2,
        )

        self.assertIn("datos", catalog_map)

    def test_catalog_index_has_global_and_per_token_bounds(self):
        """Un portal con navegación masiva no puede agotar la memoria del índice."""
        downloader = MagicMock()
        links = "".join(
            f'<a href="/estudios/programa-{index}">Programa académico {index}</a>'
            for index in range(250)
        )
        downloader.fetch_text.return_value = links

        with patch.object(part2, "HUB_AND_SPOKE_MAX_INDEXED_URLS", 40), \
             patch.object(part2, "HUB_AND_SPOKE_MAX_LINKS_PER_TOKEN", 3):
            catalog_map = self.crawler._build_academic_catalog_map(
                downloader,
                "https://www.example.edu",
                max_hubs=1,
            )

        indexed_urls = {
            url
            for entries in catalog_map.values()
            for url, _ in entries
        }
        self.assertLessEqual(len(indexed_urls), 40)
        self.assertTrue(all(len(entries) <= 3 for entries in catalog_map.values()))

    def test_structured_table_keeps_credit_column_when_cells_have_line_breaks(self):
        """Las líneas de docentes no deben ocultar el nombre ni los ECTS."""
        soup = BeautifulSoup(
            """
            <table>
              <tr><th>Asignatura</th><th>Créditos</th></tr>
              <tr>
                <td>43001:<br>Métodos de investigación<br>Docente (docente@example.edu)</td>
                <td>6</td>
              </tr>
            </table>
            """,
            "html.parser",
        )
        from fase1_parte2_web_crawler import extract_html_subjects

        elements = extract_html_subjects(soup, "https://www.example.edu/plan")
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["nombre_elemento"], "Métodos de investigación")
        self.assertEqual(elements[0]["creditos_ects"], "6")

if __name__ == "__main__":
    unittest.main()
