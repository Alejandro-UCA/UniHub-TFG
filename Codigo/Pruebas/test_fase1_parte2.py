import os
import sys
import unittest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from univ_web_crawler import (
    extract_html_subjects,
    extract_private_university_pricing,
    UniversityWebCrawler,
    is_valid_web_url,
    is_same_or_subdomain,
    ensure_https_url,
    parse_price_value,
    build_html_curriculum_payload
)
from spa_crawler import SPALayoutCrawler

class TestPhase1Part2Fixes(unittest.TestCase):

    def test_01_no_undefined_variables_in_module(self):
        """Verifica que no quede ningún rastro de la variable inexistente univ_nombre en el código fuente."""
        crawler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler", "univ_web_crawler.py"))
        with open(crawler_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("univ_nombre", content)

    def test_02_subject_character_token_boundaries(self):
        """Verifica que palabras como 'Cooperación' u 'Operaciones' no se clasifiquen erróneamente como carácter 'OP'."""
        html = """
        <table>
            <tr><th>Asignatura</th><th>Tipo</th><th>Créditos</th></tr>
            <tr><td>Cooperación Internacional al Desarrollo</td><td>OB</td><td>6</td></tr>
            <tr><td>Investigación de Operaciones</td><td>OB</td><td>6</td></tr>
            <tr><td>Antropología Filosófica</td><td>FB</td><td>6</td></tr>
            <tr><td>Optativa de Especialidad I</td><td>OP</td><td>6</td></tr>
            <tr><td>Prácticas Tuteladas</td><td>PE</td><td>12</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 5)
        
        subj_map = {s["nombre_elemento"]: s["caracter"] for s in subjects}
        self.assertEqual(subj_map["Cooperación Internacional al Desarrollo"], "OB")
        self.assertEqual(subj_map["Investigación de Operaciones"], "OB")
        self.assertEqual(subj_map["Antropología Filosófica"], "FB")
        self.assertEqual(subj_map["Optativa de Especialidad I"], "OP")
        self.assertEqual(subj_map["Prácticas Tuteladas"], "PE")

    def test_03_private_pricing_extraction_and_safety(self):
        """Verifica la extracción segura de precios de universidades privadas sin KeyError."""
        html = "<div>El precio del crédito ECTS es de 85,50 € para el presente curso académico.</div>"
        soup = BeautifulSoup(html, "html.parser")
        pricing = extract_private_university_pricing(soup, html)
        
        self.assertIn("precio_credito_ects", pricing)
        self.assertEqual(pricing["precio_credito_ects"], 85.50)
        self.assertEqual(pricing["precio_estimado_anual"], 5130.0)

    def test_04_thread_safe_robots_cache(self):
        """Verifica la existencia y correcto funcionamiento del Lock en la caché de robots.txt."""
        crawler = UniversityWebCrawler()
        self.assertTrue(hasattr(UniversityWebCrawler, "_robots_lock"))
        self.assertTrue(hasattr(crawler, "_robots_lock"))

    def test_05_spa_crawler_thread_safe_singleton(self):
        """Verifica que SPALayoutCrawler utilice sincronización por Lock en su singleton."""
        self.assertTrue(hasattr(SPALayoutCrawler, "_lock"))
        instance1 = SPALayoutCrawler.get_shared_instance()
        instance2 = SPALayoutCrawler.get_shared_instance()
        self.assertIs(instance1, instance2)

    def test_06_url_validation_and_domain_safety(self):
        """Verifica la validación estricta de URLs seguras y subdominios."""
        self.assertTrue(is_valid_web_url("https://www.uca.es/estudios"))
        self.assertFalse(is_valid_web_url("javascript:void(0)"))
        self.assertFalse(is_valid_web_url("mailto:info@uca.es"))
        self.assertFalse(is_valid_web_url("#seccion"))

        self.assertTrue(is_same_or_subdomain("https://ingenieria.uca.es/grado", "https://www.uca.es"))
        self.assertFalse(is_same_or_subdomain("https://www.google.com", "https://www.uca.es"))

    def test_07_ensure_https_url(self):
        """Verifica que ensure_https_url normalice correctamente los prefijos HTTP a HTTPS."""
        self.assertEqual(ensure_https_url("http://www.uca.es"), "https://www.uca.es")
        self.assertEqual(ensure_https_url("https://www.uca.es"), "https://www.uca.es")
        self.assertEqual(ensure_https_url("www.uca.es"), "https://www.uca.es")
        self.assertEqual(ensure_https_url(""), "")

    def test_08_parse_price_value(self):
        """Verifica la conversión numérica robusta en formato europeo y estándar."""
        self.assertEqual(parse_price_value("85,50", 15.0, 500.0), 85.50)
        self.assertEqual(parse_price_value("1.250", 1000.0, 45000.0), 1250.0)
        self.assertEqual(parse_price_value("9.800,00", 1000.0, 45000.0), 9800.0)
        self.assertIsNone(parse_price_value("5.0", 15.0, 500.0))  # Fuera de rango
        self.assertIsNone(parse_price_value("invalid", 15.0, 500.0))

    def test_09_build_html_curriculum_payload(self):
        """Verifica la construcción uniforme del payload curricular HTML."""
        elements = [{"nombre_elemento": "Matemáticas", "creditos_ects": "6", "caracter": "FB"}]
        payload_grado = build_html_curriculum_payload(elements, "Grado en Ingeniería Informática")
        self.assertEqual(payload_grado["total_elementos"], 1)
        self.assertEqual(payload_grado["resumen_creditos"], {})

        payload_master = build_html_curriculum_payload(elements, "Máster en Ciberseguridad")
        self.assertEqual(payload_master["resumen_creditos"], {})

if __name__ == "__main__":
    unittest.main(verbosity=2)
