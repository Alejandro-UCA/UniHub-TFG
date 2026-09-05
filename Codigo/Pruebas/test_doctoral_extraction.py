"""
UniHub - Pruebas unitarias de Extracción y Validación de Programas de Doctorado (RD 99/2011).
Verifica los 3 patrones universales de extracción, filtrado anti-ruido administrativo,
detección de escuela de doctorado, navegación canónica y validación curricular.
"""

import unittest
from bs4 import BeautifulSoup
from unittest.mock import MagicMock

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "API"))

from pipelines.parte2_web_crawler import (
    extract_doctoral_lines_from_soup,
    extract_doctoral_activities_from_soup,
    extract_doctoral_school_name,
    extract_generic_doctoral_program,
    is_valid_doctoral_line,
)
from quality.curriculum_validator import get_curriculum_completeness_status, is_doctorate_program


class TestDoctoralExtractionAndValidation(unittest.TestCase):

    def test_01_pattern_list_extraction(self):
        """Verifica la extracción de líneas mediante listas HTML (ul/ol) bajo encabezado."""
        html = """
        <div class="content">
            <h2>Líneas de Investigación</h2>
            <ul>
                <li>Biodiversidad, Sistemática y Evolución</li>
                <li>Ecología Terrestre y Conservación de Flora</li>
                <li>Genómica de Poblaciones y Biología Molecular</li>
            </ul>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        lines = extract_doctoral_lines_from_soup(soup, "https://univ.es/doctorado/bio")
        self.assertEqual(len(lines), 3)
        self.assertIn("Biodiversidad, Sistemática y Evolución", lines)
        self.assertIn("Ecología Terrestre y Conservación de Flora", lines)

    def test_02_pattern_subheaders_extraction(self):
        """Verifica la extracción mediante subtítulos H4/H5 en secciones (p. ej. UAB)."""
        html = """
        <section class="research-section">
            <h3>Línies de Recerca</h3>
            <div class="line-card">
                <h4>Física Teòrica i Cosmologia</h4>
                <p>Estudi dels fonaments cuántics i estructura de l'univers.</p>
            </div>
            <div class="line-card">
                <h4>Informació i Fenòmens Quàntics</h4>
                <p>Computació quàntica i criptografia avançada.</p>
            </div>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        lines = extract_doctoral_lines_from_soup(soup, "https://univ.cat/doctorats/fisica")
        self.assertEqual(len(lines), 2)
        self.assertIn("Física Teòrica i Cosmologia", lines)
        self.assertIn("Informació i Fenòmens Quàntics", lines)

    def test_03_pattern_table_extraction(self):
        """Verifica la extracción mediante celdas y tablas estructuradas (p. ej. UGR/UCA)."""
        html = """
        <div>
            <h2>Líneas de Investigación del Programa</h2>
            <table>
                <tr>
                    <td><span style="font-size: 14pt;">Farmacología y Nuevas Dianas Terapéuticas</span></td>
                </tr>
                <tr>
                    <td><span style="font-size: 14pt;">Tecnología Farmacéutica y Nanomedicina</span></td>
                </tr>
            </table>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        lines = extract_doctoral_lines_from_soup(soup, "https://doctorados.univ.es/farmacia")
        self.assertEqual(len(lines), 2)
        self.assertIn("Farmacología y Nuevas Dianas Terapéuticas", lines)

    def test_04_disqualifiers_filter_administrative_noise(self):
        """Comprueba que no se confunda información administrativa con líneas de investigación."""
        self.assertFalse(is_valid_doctoral_line("Informe de seguimiento DEVA"))
        self.assertFalse(is_valid_doctoral_line("Matrícula y tasas oficiales"))
        self.assertFalse(is_valid_doctoral_line("Normativa de permanencia"))
        self.assertFalse(is_valid_doctoral_line("Prof. Dra. María Gómez"))
        self.assertFalse(is_valid_doctoral_line("info@doctorado.es"))
        self.assertTrue(is_valid_doctoral_line("Neurociencia del Comportamiento y Adicciones"))

    def test_05_school_name_multilingual(self):
        """Verifica la detección multilingüe de la Escuela de Doctorado."""
        soup_es = BeautifulSoup("<header>Escuela Internacional de Posgrado de la Universidad</header>", "html.parser")
        self.assertIn("Escuela Internacional de Posgrado", extract_doctoral_school_name(soup_es))

        soup_ca = BeautifulSoup("<div>Organitzat per l'Escola de Doctorat UAB</div>", "html.parser")
        self.assertIn("Escola de Doctorat", extract_doctoral_school_name(soup_ca))

    def test_06_generic_doctoral_subpage_navigation_and_pdf_bypass(self):
        """Verifica la navegación hacia subpágina canónica ignorando ficheros PDF/binarios."""
        downloader = MagicMock()

        main_html = """
        <html>
            <body>
                <h1>Doctorado en Informática</h1>
                <a href="/docs/memoria_verificacion.pdf">Líneas de investigación (PDF)</a>
                <a href="/doctorado/info/lineas-de-investigacion">Líneas de investigación</a>
            </body>
        </html>
        """
        sub_html = """
        <html>
            <body>
                <h2>Líneas de investigación</h2>
                <ul>
                    <li>Inteligencia Artificial y Procesamiento del Lenguaje Natural</li>
                    <li>Sistemas Distribuidos y Ciberseguridad</li>
                </ul>
            </body>
        </html>
        """
        def fake_fetch(url):
            if "lineas-de-investigacion" in url:
                return sub_html
            return main_html

        downloader.fetch_text.side_effect = fake_fetch

        result = extract_generic_doctoral_program("https://univ.es/doctorado/info", downloader)
        self.assertEqual(result.get("total_lineas"), 2)
        self.assertIn("Inteligencia Artificial y Procesamiento del Lenguaje Natural", result.get("lineas_investigacion"))
        self.assertTrue(result.get("url_fuente").endswith("lineas-de-investigacion"))

    def test_07_curriculum_validator_with_doctoral_program(self):
        """Comprueba que el validador curricular marca el doctorado como completo y verificado."""
        degree_dict = {
            "titulo": "Doctorado en Biomedicina",
            "nivel_academico": "Doctor",
            "programa_doctoral": {
                "regulacion": "RD 99/2011",
                "lineas_investigacion": [
                    "Oncología Molecular",
                    "Inmunoterapia Avanzada"
                ]
            }
        }
        self.assertTrue(is_doctorate_program(degree_dict["nivel_academico"], degree_dict["titulo"]))
        status = get_curriculum_completeness_status(degree_dict)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["total_elementos"], 2)
        self.assertEqual(status["required_ects"], 0.0)


if __name__ == "__main__":
    unittest.main()
