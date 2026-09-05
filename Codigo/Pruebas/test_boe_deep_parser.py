"""Contratos del análisis profundo de PDFs BOE, sin red ni ficheros externos."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers.boe_pdf import clean_curricular_elements, parse_boe_pdf, clear_document_model_cache


class _Table:
    def __init__(self, rows, top=100):
        self._rows = rows
        self.bbox = (0, top, 500, top + 100)

    def extract(self):
        return self._rows


class _Page:
    def __init__(self, text, lines, tables=()):
        self._text = text
        self._lines = lines
        self._tables = tables

    def extract_text(self):
        return self._text

    def extract_words(self, **_kwargs):
        return [
            {"text": line, "top": top, "x0": 10}
            for top, line in self._lines
        ]

    def find_tables(self):
        return self._tables


class _Document:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestDeepBOEParser(unittest.TestCase):
    def setUp(self):
        clear_document_model_cache()

    def test_curricular_deduplication_prefers_code_identity(self):
        elements = clean_curricular_elements([
            {"codigo_asignatura": "1234", "nombre_elemento": "Álgebra", "creditos_ects": 6},
            {"codigo_asignatura": "1234", "nombre_elemento": "Álgebra (mención)", "creditos_ects": 6},
            {"codigo_asignatura": "5678", "nombre_elemento": "Álgebra", "creditos_ects": 6},
        ])
        self.assertEqual(len(elements), 2)
    def _parse(self, pages, title="Grado en Matemáticas"):
        with patch("boe_pdf_parser.pdfplumber.open", return_value=_Document(pages)):
            return parse_boe_pdf(b"%PDF-1.4\nfixture", title, "Universidad de Prueba")

    def test_uses_a_declared_table_without_calling_legacy_text_parser(self):
        page = _Page(
            "Plan de estudios conducente al título de Grado en Matemáticas",
            [(10, "Plan de estudios conducente al título de Grado en Matemáticas")],
            [_Table([
                ["Asignatura", "Créditos", "Carácter"],
                ["Álgebra", "6", "FB"],
                ["Cálculo", "6", "OB"],
            ])],
        )
        with patch("boe_pdf_parser.parse_boe_text_curriculum_dynamic", side_effect=AssertionError("No debe invocarse")):
            parsed = self._parse([page])
        self.assertEqual(parsed["metodo_extraccion"], "analisis_profundo_pdf")
        self.assertEqual([row["nombre_elemento"] for row in parsed["elementos_curriculares"]], ["Álgebra", "Cálculo"])

    def test_recovers_a_borderless_table_from_positioned_lines(self):
        page = _Page(
            "Plan de estudios conducente al título de Grado en Matemáticas",
            [
                (10, "Plan de estudios conducente al título de Grado en Matemáticas"),
                (50, "Asignatura Créditos Tipo"),
                (70, "Álgebra Lineal. 6 FB"),
                (90, "Cálculo Diferencial. 6 OB"),
                (110, "6.2 Condiciones de terminación"),
            ],
        )
        parsed = self._parse([page])
        self.assertEqual([row["nombre_elemento"] for row in parsed["elementos_curriculares"]], ["Álgebra Lineal", "Cálculo Diferencial"])

    def test_multi_degree_page_keeps_only_the_target_table(self):
        page = _Page(
            "Plan de estudios conducente al título de Grado en Matemáticas\nPlan de estudios conducente al título de Grado en Física",
            [
                (10, "Plan de estudios conducente al título de Grado en Matemáticas"),
                (210, "Plan de estudios conducente al título de Grado en Física"),
            ],
            [
                _Table([["Asignatura", "Créditos", "Carácter"], ["Álgebra", "6", "FB"]], top=80),
                _Table([["Asignatura", "Créditos", "Carácter"], ["Mecánica", "6", "FB"]], top=280),
            ],
        )
        parsed = self._parse([page])
        self.assertEqual([row["nombre_elemento"] for row in parsed["elementos_curriculares"]], ["Álgebra"])


if __name__ == "__main__":
    unittest.main()
