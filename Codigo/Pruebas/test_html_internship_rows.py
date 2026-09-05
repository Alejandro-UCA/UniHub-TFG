"""Regresiones de filas PE descartadas antes de leer carácter y ECTS."""
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
from pipelines.parte2_web_crawler import extract_html_subjects


class InternshipRowsTests(unittest.TestCase):
    def test_real_snapshot_preserves_all_thirteen_subjects_and_ninety_ects(self):
        html = (Path(__file__).parent / 'fixtures' / 'curriculum_internships.html').read_bytes()
        items = extract_html_subjects(BeautifulSoup(html, 'html.parser'))
        self.assertEqual(13, len(items))
        self.assertEqual(90, sum(float(item['creditos_ects']) for item in items))
        self.assertEqual({'2976', '2977'}, {item['codigo_asignatura'] for item in items if item['caracter'] == 'PE'})

    def extract(self, rows):
        html = ('<h2>Plan de estudios</h2><table><tr><th>Código</th>'
                '<th>Nombre</th><th>Tipo</th><th>ECTS</th></tr>' + rows + '</table>')
        return extract_html_subjects(BeautifulSoup(html, 'html.parser'))

    def test_preserves_separate_internships_with_explicit_credits(self):
        items = self.extract(
            '<tr><td>2976</td><td>Prácticas Externas I</td><td>PE</td><td>6</td></tr>'
            '<tr><td>2977</td><td>Prácticas Externas II</td><td>PE</td><td>24</td></tr>')
        self.assertEqual(['Prácticas Externas I', 'Prácticas Externas II'],
                         [item['nombre_elemento'] for item in items])
        self.assertEqual(30, sum(float(item['creditos_ects']) for item in items))

    def test_metadata_remains_rejected_even_with_pe_character(self):
        items = self.extract(
            '<tr><td>1001</td><td>Coordinación de prácticas externas</td><td>PE</td><td>6</td></tr>'
            '<tr><td>1002</td><td>Prácticas Externas</td><td>PE</td><td></td></tr>')
        self.assertEqual([], items)

    def test_multilingual_internship(self):
        items = self.extract(
            '<tr><td>1001</td><td>Pràctiques externes II</td><td>PE</td><td>12</td></tr>')
        self.assertEqual(1, len(items))
        self.assertEqual('12', items[0]['creditos_ects'])

    def test_academic_office_management_is_not_teacher_contact(self):
        items = self.extract(
            '<tr><td>2967</td><td>Ejercicio Profesional, Organización Colegial y Gestión de Despachos</td><td>OB</td><td>3</td></tr>'
            '<tr><td>1002</td><td>Despacho 302</td><td>OB</td><td>6</td></tr>')
        self.assertEqual(1, len(items))
        self.assertEqual('3', items[0]['creditos_ects'])


if __name__ == '__main__':
    unittest.main()
