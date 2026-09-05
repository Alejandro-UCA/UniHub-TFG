"""Pruebas unitarias para validación y calidad de doctorados oficiales (RD 99/2011)."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from quality.curriculum_validator import (
    get_curriculum_completeness_status,
    is_doctorate_program,
)
from quality.data_quality import (
    QUALITY_VERIFIED_DOCTORATE,
    assess_plan_quality,
)


class TestDoctorateValidationRD99(unittest.TestCase):
    """Verifica que los programas de doctorado oficiales se consideren completos y publicables."""

    def test_is_doctorate_program_detection(self):
        self.assertTrue(is_doctorate_program("Doctorado", "Programa de Doctorado en Informática"))
        self.assertTrue(is_doctorate_program("Tercer Ciclo", "Doctorat en Biomedicina"))
        self.assertTrue(is_doctorate_program("Doctorate", "PhD in Computer Science"))
        self.assertFalse(is_doctorate_program("Grado", "Grado en Ingeniería Informática"))
        self.assertFalse(is_doctorate_program("Máster", "Máster Universitario en Ciberseguridad"))

    def test_doctorate_with_boe_url_is_complete(self):
        degree = {
            "codigo_estudio": "5600123",
            "titulo": "Programa de Doctorado en Matemáticas",
            "nivel_academico": "Doctorado",
            "boe_url": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2015-1234",
            "plan_estudios": {},
        }
        status = get_curriculum_completeness_status(degree)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "doctorado_oficial")
        self.assertEqual(status["required_ects"], 0.0)

    def test_doctorate_with_web_url_is_complete(self):
        degree = {
            "codigo_estudio": "5600456",
            "titulo": "Programa de Doctorado en Física Avanzada",
            "nivel_academico": "Doctorado",
            "web": "https://www.uam.es/estudios/doctorado-fisica",
            "plan_estudios": None,
        }
        status = get_curriculum_completeness_status(degree)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "doctorado_oficial")

    def test_doctorate_with_research_lines_is_structural(self):
        degree = {
            "codigo_estudio": "5600789",
            "titulo": "Programa de Doctorado en Historia",
            "nivel_academico": "Doctorado",
            "programa_doctoral": {
                "lineas_investigacion": [
                    "Historia Medieval de la Península Ibérica",
                    "Arqueología del Mediterráneo",
                ]
            },
        }
        status = get_curriculum_completeness_status(degree)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "doctorado_estructural")
        self.assertEqual(status["total_subjects"], 2)

    def test_doctorate_without_source_or_lines_is_incomplete(self):
        degree = {
            "codigo_estudio": "5600999",
            "titulo": "Programa de Doctorado en Filosofía",
            "nivel_academico": "Doctorado",
        }
        status = get_curriculum_completeness_status(degree)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["status"], "doctorado_sin_detalle")

    def test_doctorate_assess_plan_quality_publishes_verified(self):
        payload = {
            "codigo_estudio": "5600123",
            "titulo": "Programa de Doctorado en Informática",
            "nivel_academico": "Doctorado",
            "boe_url": "https://www.boe.es/boe/dias/2014/10/15/pdfs/BOE-A-2014-10492.pdf",
            "origen_fuente": "resolucion_boe",
            "plan_estudios": {},
        }
        quality = assess_plan_quality(payload)
        self.assertTrue(quality["publicable"])
        self.assertEqual(quality["estado"], QUALITY_VERIFIED_DOCTORATE)
        self.assertTrue(quality["verificaciones"]["detalle_curricular_suficiente"])


if __name__ == "__main__":
    unittest.main()
