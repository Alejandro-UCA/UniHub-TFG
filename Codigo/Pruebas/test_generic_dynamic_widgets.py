import unittest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from fase1_parte2_web_crawler import extract_dynamic_widget_subjects


class TestGenericDynamicWidgets(unittest.TestCase):
    """Pruebas unitarias para el extractor universal y agnóstico de microservicios y widgets HTML5."""

    def test_extract_widget_from_data_config_json(self):
        html_page = """
        <html>
          <body>
            <h1>Grado de Ejemplo</h1>
            <div class="keditor-webservice" data-config='{"servicioweb":"wsplanestudios","idioma":"es","codest":"C100","url":"https://portal.universidad.es/api/PlanEstudios"}'>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html_page, "html.parser")
        
        api_response_json = """{
            "html": "<div class='arco'><div class='asi'><span class='col1'>1</span><span class='col3'>BÁSICA</span><span class='col4'><a href='/guias/101'>101 - INTRODUCCIÓN A LA INFORMÁTICA</a></span><span class='col5'>6</span></div><div class='asi'><span class='col1'>1</span><span class='col3'>OBLIGATORIA</span><span class='col4'><a href='/guias/102'>102 - ESTRUCTURAS DE DATOS</a></span><span class='col5'>6</span></div><div class='asi'><span class='col1'>2</span><span class='col3'>OPTATIVA</span><span class='col4'><a href='/guias/201'>201 - INTELIGENCIA ARTIFICIAL</a></span><span class='col5'>6</span></div></div>"
        }"""
        
        mock_downloader = MagicMock()
        mock_downloader.fetch_text.return_value = api_response_json

        subjects = extract_dynamic_widget_subjects(
            soup=soup,
            current_page_url="https://www.universidad.es/grados/informatica",
            web_url="https://www.universidad.es",
            downloader=mock_downloader,
        )

        self.assertEqual(len(subjects), 3)
        self.assertEqual(subjects[0]["nombre_elemento"], "INTRODUCCIÓN A LA INFORMÁTICA")
        self.assertEqual(subjects[0]["codigo_asignatura"], "101")
        self.assertEqual(subjects[0]["creditos_ects"], "6")
        self.assertEqual(subjects[0]["caracter"], "FB")
        self.assertEqual(subjects[0]["url_guia_docente"], "https://portal.universidad.es/guias/101")
        
        self.assertEqual(subjects[1]["nombre_elemento"], "ESTRUCTURAS DE DATOS")
        self.assertEqual(subjects[1]["caracter"], "OB")
        self.assertEqual(subjects[2]["nombre_elemento"], "INTELIGENCIA ARTIFICIAL")
        self.assertEqual(subjects[2]["caracter"], "OP")

    def test_extract_widget_from_data_url_attribute(self):
        html_page = """
        <html>
          <body>
            <div data-url="/api/v1/curriculum/plan-estudios" class="academic-plan-widget"></div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html_page, "html.parser")

        api_response_html = """
        <table>
          <thead>
            <tr><th>Asignatura</th><th>Créditos</th><th>Tipo</th></tr>
          </thead>
          <tbody>
            <tr><td>Álgebra Lineal</td><td>6</td><td>Básica</td></tr>
            <tr><td>Cálculo</td><td>6</td><td>Básica</td></tr>
            <tr><td>Física General</td><td>6</td><td>Obligatoria</td></tr>
          </tbody>
        </table>
        """
        mock_downloader = MagicMock()
        mock_downloader.fetch_text.return_value = api_response_html

        subjects = extract_dynamic_widget_subjects(
            soup=soup,
            current_page_url="https://www.otrauniversidad.es/estudios/grado-teleco",
            web_url="https://www.otrauniversidad.es",
            downloader=mock_downloader,
        )

        self.assertEqual(len(subjects), 3)
        names = [s["nombre_elemento"] for s in subjects]
        self.assertIn("Álgebra Lineal", names)
        self.assertIn("Cálculo", names)
        self.assertIn("Física General", names)

    def test_ssrf_prevention_rejects_external_domain(self):
        html_page = """
        <html>
          <body>
            <div data-url="https://evil-external-site.com/api/fake-plan" class="plan-estudios"></div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html_page, "html.parser")

        mock_downloader = MagicMock()

        subjects = extract_dynamic_widget_subjects(
            soup=soup,
            current_page_url="https://www.universidad.es/grado",
            web_url="https://www.universidad.es",
            downloader=mock_downloader,
        )

        self.assertEqual(len(subjects), 0)
        mock_downloader.fetch_text.assert_not_called()

    def test_non_academic_widgets_are_ignored(self):
        html_page = """
        <html>
          <body>
            <div data-config='{"servicioweb":"wssemaforocabecera","url":"/api/weather"}'></div>
            <div data-url="/api/v1/cookies/policy" class="cookie-banner"></div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html_page, "html.parser")

        mock_downloader = MagicMock()

        subjects = extract_dynamic_widget_subjects(
            soup=soup,
            current_page_url="https://www.universidad.es/grado",
            web_url="https://www.universidad.es",
            downloader=mock_downloader,
        )

        self.assertEqual(len(subjects), 0)
        mock_downloader.fetch_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
