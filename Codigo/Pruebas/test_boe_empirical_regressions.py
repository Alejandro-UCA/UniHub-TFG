"""Regresiones observadas al contrastar planes publicados en el BOE.

Los ejemplos proceden de las estructuras de los BOE-A-2024-1769 y
BOE-A-2022-12382, reducidos a los nombres y encabezados imprescindibles para
probar el parser sin depender de la red ni redistribuir los PDFs.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from boe_pdf_parser import (
    clean_curricular_elements,
    detect_curricular_table_header,
    extract_credit_summary,
    first_page_curricular_search_text,
    is_section_matching,
    parse_boe_text_curriculum_dynamic,
)
from curriculum_validator import get_curriculum_completeness_status
from sanitizers import is_spurious_or_administrative_subject


class TestBOEEmpiricalRegressions(unittest.TestCase):
    def test_temporality_headings_are_not_subjects(self):
        self.assertTrue(is_spurious_or_administrative_subject("Primer semestre"))
        self.assertTrue(is_spurious_or_administrative_subject("Segundo semestre"))
        self.assertTrue(is_spurious_or_administrative_subject("Temporalidad de las asignaturas"))
        self.assertFalse(is_spurious_or_administrative_subject("Dirección de Plazos"))

    def test_elective_selection_rows_are_not_subjects(self):
        for label in ("1 Optativa de Mención", "2 Optativas de Mención", "3 Optativas de Mención", "2 Optativas"):
            self.assertTrue(is_spurious_or_administrative_subject(label), label)
        self.assertFalse(is_spurious_or_administrative_subject("Economía de las Organizaciones"))

    def test_temporality_duplicate_keeps_the_curricular_row(self):
        elements = clean_curricular_elements([
            {"nombre_elemento": "Fundamentos de la Investigación en Ingeniería", "creditos_ects": 3},
            {"nombre_elemento": "Primer semestre", "creditos_ects": None},
            {"nombre_elemento": "Fundamentos de la Investigación en la Ingeniería", "creditos_ects": 3},
            {"nombre_elemento": "Segundo semestre", "creditos_ects": None},
        ])

        self.assertEqual([item["nombre_elemento"] for item in elements], [
            "Fundamentos de la Investigación en Ingeniería",
        ])

    def test_dynamic_parser_applies_the_same_cleanup(self):
        text = """
        6.1 Estructura del plan de estudios:
        Asignatura Créditos Tipo
        Fundamentos de la Investigación en Ingeniería. 3 OB
        Fundamentos de la Investigación en la Ingeniería. 3 OB
        Primer semestre. 3 OB
        Dirección de Plazos. 3 OB
        6.2 Condiciones de terminación
        """
        parsed = parse_boe_text_curriculum_dynamic(text, "Máster Universitario", "Máster")
        self.assertEqual(
            [item["nombre_elemento"] for item in parsed["elementos_curriculares"]],
            ["Fundamentos de la Investigación en Ingeniería", "Dirección de Plazos"],
        )

    def test_total_ects_accepts_boe_label_variants(self):
        self.assertEqual(
            extract_credit_summary("Total de créditos: 90"),
            {"Créditos Totales": "90"},
        )
        parsed = parse_boe_text_curriculum_dynamic(
            """
            4. Total créditos ECTS del título: 90
            6.1 Estructura del plan de estudios:
            Asignatura Créditos Tipo
            Análisis Económico. 6 OB
            6.2 Condiciones de terminación
            """,
            "Máster Universitario en Economía",
            "Máster",
        )
        self.assertEqual(parsed["resumen_creditos"]["Créditos Totales"], "90")

    def test_credit_summary_prefers_parenthesized_boe_categories(self):
        summary = extract_credit_summary("""
            Formación básica (FB). 60
            Obligatorias (OB). 102
            Optativas (OP). 57
            Prácticas externas (PE). 12
            Trabajo fin de grado (TFG). 9
            Total. 240
            Fundamentos de Economía Política. FB 6
        """)
        self.assertEqual(summary, {
            "Formación Básica": "60",
            "Obligatorias": "102",
            "Optativas": "57",
            "Prácticas Externas": "12",
            "Trabajo Fin de Grado / Máster": "9",
            "Créditos Totales": "240",
        })

    def test_declared_ects_is_not_inflated_by_alternative_electives(self):
        status = get_curriculum_completeness_status({
            "titulo": "Máster Universitario en Dirección de Proyectos",
            "nivel_academico": "Máster Universitario",
            "plan_estudios": {
                "resumen_creditos": {"Créditos Totales": "60"},
                # Varias filas corresponden a alternativas optativas: su suma
                # no es la carga que cursa un único estudiante.
                "elementos_curriculares": [
                    {"nombre_elemento": f"Asignatura {index}", "creditos_ects": 4}
                    for index in range(22)
                ],
            },
        })

        self.assertTrue(status["is_complete"])
        self.assertEqual(status["total_ects_declared"], 60.0)
        self.assertEqual(status["total_ects_listed"], 88.0)
        self.assertEqual(status["total_ects_obtained"], 60.0)

    def test_subject_containing_materia_is_not_a_header(self):
        self.assertEqual(detect_curricular_table_header([
            "Fundamentos de la Economía Circular.",
            "Ciclos de los materiales.",
            "6",
            "Obligatoria.",
            "1",
            "Semestre 1.",
        ]), {})
        self.assertEqual(detect_curricular_table_header([
            "Módulos",
            "Asignaturas",
            "Créditos",
            "Carácter",
            "Curso",
            "Organización temporal",
        ]), {
            "materia": 0,
            "subject": 1,
            "ects": 2,
            "caracter": 3,
            "curso": 4,
        })

    def test_single_distinctive_title_keyword_accepts_contextual_section(self):
        self.assertTrue(is_section_matching(
            {"biomedica", "industrial", "mecanica"},
            {"biomedica"},
        ))
        self.assertFalse(is_section_matching(
            {"aeroespacial", "industrial", "mecanica"},
            {"biomedica"},
        ))

    def test_first_page_filter_keeps_title_before_anexo(self):
        text = """
            Resolución administrativa previa.
            Sevilla, 9 de octubre de 2025.–El Rector, Nombre Apellidos.
            Plan de estudios conducente al título de Graduado o Graduada en Biomédica.
            ANEXO I
            Distribución general del plan de estudios.
        """
        filtered = first_page_curricular_search_text(text)
        self.assertIn("Graduado o Graduada en Biomédica", filtered)
        self.assertNotIn("Resolución administrativa previa", filtered)


if __name__ == "__main__":
    unittest.main()
