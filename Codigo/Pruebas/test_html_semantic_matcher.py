import unittest
import sys
import os
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('Codigo/Crawler'))

from univ_web_crawler import is_html_page_matching_degree
from parsers import is_section_matching, extract_degree_core_keywords

class TestHTMLSemanticMatcher(unittest.TestCase):

    def test_reject_cross_degree_sitemap_collision(self):
        target_title = "Máster Universitario en Materiales Complejos: Análisis Térmico y Caracterización Estructural"
        univ_name = "Universitat Autònoma de Barcelona"

        html_mismatch = """
        <html>
        <head><title>Màster Universitari en Ecologia Terrestre i Gestió de la Biodiversitat - UAB Barcelona</title></head>
        <body>
          <h1>Ecologia Terrestre i Gestió de la Biodiversitat</h1>
          <h2>Pla d'estudis</h2>
          <table>
            <tr><td>Ecologia de Poblacions</td><td>6 ECTS</td></tr>
            <tr><td>Gestió de la Biodiversitat</td><td>6 ECTS</td></tr>
          </table>
        </body>
        </html>
        """
        soup_mismatch = BeautifulSoup(html_mismatch, "html.parser")
        matched = is_html_page_matching_degree(
            soup_mismatch, 
            target_title, 
            univ_name, 
            "https://www.uab.cat/web/estudiar/l-oferta-de-masters-oficials/matricula/ecologia-terrestre-i-gestio-de-la-biodiversitat-1345655869231.html"
        )
        self.assertFalse(matched, "Should strictly reject mismatched cross-degree HTML page")

    def test_accept_genuine_degree_page_multilingual(self):
        target_title = "Máster Universitario en Materiales Complejos: Análisis Térmico y Caracterización Estructural"
        univ_name = "Universitat Autònoma de Barcelona"

        html_catalan = """
        <html>
        <head><title>Màster Universitari en Materials Complexos - UAB</title></head>
        <body>
          <h1>Materials Complexos: Anàlisi Tèrmica i Caracterització Estructural</h1>
          <h2>Pla d'estudis</h2>
          <table>
            <tr><td>Anàlisi Tèrmica Avançada</td><td>6 ECTS</td></tr>
            <tr><td>Difracció de Raigs X</td><td>6 ECTS</td></tr>
          </table>
        </body>
        </html>
        """
        soup_catalan = BeautifulSoup(html_catalan, "html.parser")
        matched = is_html_page_matching_degree(
            soup_catalan, 
            target_title, 
            univ_name, 
            "https://www.uab.cat/web/estudiar/materials-complexos-1345655869231.html"
        )
        self.assertTrue(matched, "Should accept genuine multilingual degree match")


if __name__ == "__main__":
    unittest.main()
