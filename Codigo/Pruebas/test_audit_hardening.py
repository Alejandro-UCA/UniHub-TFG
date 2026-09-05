import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Crawler"))

from curriculum_validator import get_curriculum_completeness_status
from data_quality import assess_plan_quality
from ruct_xls_parser import classify_registry_entity
from subject_guide_quality import assess_subject_guide_quality


class AuditHardeningTests(unittest.TestCase):
    def test_optional_catalogue_is_not_flat_sum(self):
        degree = {
            "codigo_estudio": "2500001",
            "titulo": "Grado en Historia",
            "nivel_academico": "Grado - RD 822/2021 (2)",
            "plan_estudios": {
                "elementos_curriculares": [
                    {"nombre_elemento": "Obligatoria", "caracter": "OB", "creditos_ects": 6},
                    {"nombre_elemento": "Optativa A", "caracter": "OP", "creditos_ects": 18},
                    {"nombre_elemento": "Optativa B", "caracter": "OP", "creditos_ects": 18},
                ]
            },
        }
        status = get_curriculum_completeness_status(degree)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["status"], "optatividad_no_resuelta")

    def test_optional_catalogue_is_complete_when_core_covers_required_load(self):
        degree = {
            "codigo_estudio": "2500002",
            "titulo": "Máster en Historia",
            "nivel_academico": "Máster - RD 822/2021 (3)",
            "plan_estudios": {
                "elementos_curriculares": [
                    *[
                        {"nombre_elemento": f"Obligatoria {index}", "caracter": "OB", "creditos_ects": 6}
                        for index in range(8)
                    ],
                    {"nombre_elemento": "Optativa A", "caracter": "OP", "creditos_ects": 12},
                ]
            },
        }
        status = get_curriculum_completeness_status(degree)
        self.assertTrue(status["is_complete"])
        self.assertTrue(status["optatividad_inferida_resuelta"])
        self.assertEqual(status["total_ects_obtained"], 60.0)
        self.assertEqual(status["total_ects_listed"], 60.0)

    def test_optional_catalogue_stays_partial_when_core_is_insufficient(self):
        degree = {
            "codigo_estudio": "2500003",
            "titulo": "Máster en Historia",
            "nivel_academico": "Máster - RD 822/2021 (3)",
            "plan_estudios": {
                "elementos_curriculares": [
                    *[
                        {"nombre_elemento": f"Obligatoria {index}", "caracter": "OB", "creditos_ects": 6}
                        for index in range(4)
                    ],
                    {"nombre_elemento": "Optativa A", "caracter": "OP", "creditos_ects": 36},
                ]
            },
        }
        status = get_curriculum_completeness_status(degree)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["status"], "optatividad_no_resuelta")

    def test_optional_catalogue_uses_current_evidence_not_previous_source_state(self):
        degree = {
            "codigo_estudio": "3500004",
            "titulo": "Máster en Literatura",
            "nivel_academico": "Máster - RD 822/2021 (3)",
            # Este estado describe un intento anterior; no debe invalidar una
            # estructura curricular explícita que acaba de ser recuperada.
            "estado_fuente": "candidata_no_publicable",
            "plan_estudios": {
                "elementos_curriculares": [
                    *[
                        {"nombre_elemento": f"Obligatoria {index}", "caracter": "OB", "creditos_ects": 6}
                        for index in range(8)
                    ],
                    {"nombre_elemento": "Optativa A", "caracter": "OP", "creditos_ects": 12},
                ]
            },
        }

        status = get_curriculum_completeness_status(degree)

        self.assertTrue(status["is_complete"])
        self.assertTrue(status["optatividad_inferida_resuelta"])
        self.assertEqual(status["total_ects_obtained"], 60.0)
        self.assertEqual(status["total_ects_listed"], 60.0)

    def test_master_optional_catalogue_can_have_a_42_ects_fixed_core(self):
        degree = {
            "codigo_estudio": "3500005",
            "titulo": "Máster en Literatura",
            "nivel_academico": "Máster - RD 1393/2007 (1)",
            "plan_estudios": {
                "elementos_curriculares": [
                    *[
                        {"nombre_elemento": f"Obligatoria {index}", "caracter": "OB", "creditos_ects": 6}
                        for index in range(5)
                    ],
                    {"nombre_elemento": "Trabajo final", "caracter": "TFM", "creditos_ects": 12},
                    {"nombre_elemento": "Optativa A", "caracter": "OP", "creditos_ects": 18},
                    {"nombre_elemento": "Optativa B", "caracter": "OP", "creditos_ects": 60},
                ]
            },
        }

        status = get_curriculum_completeness_status(degree)

        self.assertTrue(status["is_complete"])
        self.assertTrue(status["optatividad_inferida_resuelta"])
        self.assertEqual(status["total_ects_obtained"], 60.0)
        self.assertEqual(status["total_ects_listed"], 120.0)

    def test_category_summary_can_supply_missing_total(self):
        degree = {
            "codigo_estudio": "2500004",
            "titulo": "Grado en Biología",
            "nivel_academico": "Grado - RD 822/2021 (2)",
            "plan_estudios": {
                "resumen_creditos": {
                    "Formación Básica": "60",
                    "Obligatorias": "120",
                    "Optativas": "54",
                    "Trabajo Fin de Grado": "6",
                },
                "elementos_curriculares": [
                    {"nombre_elemento": f"Materia {index}", "caracter": "OB", "creditos_ects": 6}
                    for index in range(40)
                ],
            },
        }
        status = get_curriculum_completeness_status(degree)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["total_ects_declared"], 240.0)

    def test_historical_source_cannot_be_publicable(self):
        payload = {
            "codigo_estudio": "2500001",
            "titulo": "Grado en Historia",
            "nivel_academico": "Grado - RD 822/2021 (2)",
            "web_fuente_directa_url": "https://univ.es/estudios/2025-26/grado-historia-ext-plan",
            "origen_fuente": "web_oficial_universidad",
            "plan_estudios": {"elementos_curriculares": [{"nombre_elemento": "Historia", "caracter": "OB", "creditos_ects": 240}]},
        }
        result = assess_plan_quality(payload, "web_oficial_universidad")
        self.assertFalse(result["publicable"])
        self.assertIn("fuente_historica_o_plan_extinguido", result["errores"])

    def test_guide_requires_identity(self):
        result = assess_subject_guide_quality(
            {"nombre_asignatura": "", "codigo_asignatura": "", "creditos": {"total_ects": 6}, "temario": ["Tema"]},
            expected_name="Ciencia Política",
            expected_code="801161",
        )
        self.assertFalse(result["identidad"]["verificada"])
        self.assertFalse(result["publicable"])

    def test_ruct_special_entities_are_classified(self):
        self.assertEqual(classify_registry_entity("Centros extranjeros autorizados por la Comunidad Autónoma de Aragón"), "centro_extranjero_autorizado")
        self.assertEqual(classify_registry_entity("Universidad de Alicante"), "universidad")


if __name__ == "__main__":
    unittest.main()
