"""Pruebas unitarias para propagación de celdas por rowspan e inferencia secuencial de curso."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from bs4 import BeautifulSoup

from parsers.html_tables import normalize_table_rows_with_spans, extract_html_subjects
from quality.curriculum_validator import infer_missing_courses_in_curriculum


class TestCourseRowspanAndECTSInference(unittest.TestCase):
    """Verifica la reconstrucción matricial con rowspan y la asignación secuencial de curso."""

    def test_normalize_table_rows_with_spans_basic(self):
        html = """
        <table>
            <tr>
                <td rowspan="2">1º</td>
                <td>Matemáticas I</td>
                <td>6</td>
            </tr>
            <tr>
                <td>Física I</td>
                <td>6</td>
            </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        grid = normalize_table_rows_with_spans(rows)

        self.assertEqual(len(grid), 2)
        # Fila 0: 1º, Matemáticas I, 6
        self.assertEqual(grid[0][2], ["1º", "Matemáticas I", "6"])
        # Fila 1: 1º (heredado por rowspan), Física I, 6
        self.assertEqual(grid[1][2], ["1º", "Física I", "6"])

    def test_normalize_table_rows_with_spans_and_colspans(self):
        html = """
        <table>
            <tr>
                <th colspan="2">Información</th>
                <th>Créditos</th>
            </tr>
            <tr>
                <td rowspan="2">Obligatoria</td>
                <td>Álgebra</td>
                <td>6</td>
            </tr>
            <tr>
                <td>Cálculo</td>
                <td>6</td>
            </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        grid = normalize_table_rows_with_spans(rows)

        self.assertEqual(len(grid), 3)
        self.assertEqual(len(grid[0][2]), 3)
        self.assertEqual(grid[1][2], ["Obligatoria", "Álgebra", "6"])
        self.assertEqual(grid[2][2], ["Obligatoria", "Cálculo", "6"])

    def test_infer_missing_courses_in_curriculum_sequential(self):
        elementos = []
        # Crear 40 asignaturas de 6 ECTS cada una (240 ECTS total) sin curso
        for i in range(1, 41):
            car = "FB" if i <= 10 else ("TFG" if i == 40 else "OB")
            elementos.append({
                "nombre_elemento": f"Asignatura {i}" if i < 40 else "Trabajo Fin de Grado",
                "creditos_ects": 6.0,
                "caracter": car,
                "curso": "",
            })

        enriched = infer_missing_courses_in_curriculum(elementos, total_duracion_anos=4)

        # Primeras 10 materias (0 a 60 ECTS) -> 1º
        for item in enriched[:10]:
            self.assertEqual(item["curso"], "1º")

        # Materias 11 a 20 (60 a 120 ECTS) -> 2º
        for item in enriched[10:20]:
            self.assertEqual(item["curso"], "2º")

        # Materias 21 a 30 (120 a 180 ECTS) -> 3º
        for item in enriched[20:30]:
            self.assertEqual(item["curso"], "3º")

        # Materias 31 a 40 (180 a 240 ECTS) -> 4º
        for item in enriched[30:40]:
            self.assertEqual(item["curso"], "4º")

        # El TFG debe estar anclado en 4º
        self.assertEqual(enriched[-1]["curso"], "4º")

    def test_infer_missing_courses_preserves_existing_courses(self):
        elementos = [
            {"nombre_elemento": "Asignatura 1", "creditos_ects": 6.0, "curso": "1º"},
            {"nombre_elemento": "Asignatura 2", "creditos_ects": 6.0, "curso": "1º"},
            {"nombre_elemento": "Asignatura 3", "creditos_ects": 6.0, "curso": "2º"},
            {"nombre_elemento": "Asignatura 4", "creditos_ects": 6.0, "curso": "2º"},
        ]
        result = infer_missing_courses_in_curriculum(elementos, total_duracion_anos=4)
        self.assertEqual([el["curso"] for el in result], ["1º", "1º", "2º", "2º"])


if __name__ == "__main__":
    unittest.main()
