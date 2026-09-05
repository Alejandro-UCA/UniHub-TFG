import os
import sys
import unittest

from curriculum_validator import get_curriculum_completeness_status


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from data_quality import (
    QUALITY_NO_VERIFIED_DATA,
    QUALITY_PARTIAL,
    QUALITY_PENDING_REVIEW,
    QUALITY_VERIFIED_BOE,
    QUALITY_VERIFIED_UNIVERSITY,
    apply_plan_quality,
    assess_plan_quality,
    promote_verified_candidate,
)


def complete_degree_payload(source_url="https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf"):
    return {
        "codigo_estudio": "2500001",
        "titulo": "Grado en Ingeniería Informática",
        "nivel_academico": "Grado",
        "boe_url": source_url,
        "plan_estudios": {
            "nombre_plan": "Grado en Ingeniería Informática",
            "elementos_curriculares": [
                {"nombre_elemento": f"Asignatura {index}", "creditos_ects": 6}
                for index in range(40)
            ],
        },
    }


class TestPlanQualityGate(unittest.TestCase):
    def test_complete_boe_plan_is_publishable(self):
        assessment = assess_plan_quality(complete_degree_payload(), "boe")
        self.assertEqual(assessment["estado"], QUALITY_VERIFIED_BOE)
        self.assertTrue(assessment["publicable"])

    def test_apply_quality_synchronizes_persisted_plan_metadata(self):
        payload = complete_degree_payload()
        assessment = apply_plan_quality(payload, payload["plan_estudios"], "boe")
        self.assertTrue(assessment["publicable"])
        self.assertEqual(payload["plan_estudios"]["ects_totales_detectados"], 240.0)
        self.assertEqual(payload["plan_estudios"]["ects_exigidos"], 240.0)
        self.assertTrue(payload["plan_estudios"]["plan_completo"])
        self.assertFalse(payload["plan_estudios"]["optatividad_no_resuelta"])

    def test_complete_official_web_plan_is_publishable(self):
        payload = complete_degree_payload("https://www.example-university.es/grado/informatica")
        payload.pop("boe_url")
        payload["web_fuente_directa_url"] = "https://www.example-university.es/grado/informatica"
        assessment = assess_plan_quality(payload, "web_oficial_universidad")
        self.assertEqual(assessment["estado"], QUALITY_VERIFIED_UNIVERSITY)
        self.assertTrue(assessment["publicable"])

    def test_incomplete_plan_is_never_publishable(self):
        payload = complete_degree_payload()
        payload["plan_estudios"]["elementos_curriculares"] = payload["plan_estudios"]["elementos_curriculares"][:2]
        assessment = assess_plan_quality(payload, "boe")
        self.assertEqual(assessment["estado"], QUALITY_PARTIAL)
        self.assertFalse(assessment["publicable"])

    def test_identity_mismatch_is_quarantined(self):
        payload = complete_degree_payload()
        payload["plan_estudios"]["nombre_plan"] = "Máster Universitario en Derecho"
        assessment = assess_plan_quality(payload, "boe")
        self.assertEqual(assessment["estado"], QUALITY_PENDING_REVIEW)
        self.assertIn("titulo_plan_no_coincide", assessment["errores"])

    def test_failed_candidate_cannot_replace_verified_plan(self):
        payload = complete_degree_payload()
        apply_plan_quality(payload, payload["plan_estudios"], "boe")
        verified_plan = payload["plan_estudios"]
        candidate = {"elementos_curriculares": []}
        assessment = apply_plan_quality(payload, candidate, "web_oficial_universidad")
        self.assertEqual(assessment["estado"], QUALITY_PARTIAL)
        self.assertEqual(payload["plan_estudios"], verified_plan)
        self.assertEqual(payload["candidato_plan_estudios"], candidate)
        self.assertEqual(payload["estado_calidad"], QUALITY_VERIFIED_BOE)
        self.assertTrue(payload["calidad_datos"]["publicable"])

    def test_missing_new_evidence_reassesses_existing_verified_plan(self):
        payload = complete_degree_payload("https://www.example-university.es/grado/informatica")
        payload.pop("boe_url")
        payload["web_fuente_directa_url"] = "https://www.example-university.es/grado/informatica"
        existing_plan = payload["plan_estudios"]

        assessment = apply_plan_quality(payload, None, "web_oficial_universidad")

        self.assertTrue(assessment["publicable"])
        self.assertEqual(payload["plan_estudios"]["elementos_curriculares"], existing_plan["elementos_curriculares"])
        self.assertEqual(payload["calidad_datos"]["estado"], QUALITY_VERIFIED_UNIVERSITY)
        self.assertEqual(payload["estado_calidad"], QUALITY_VERIFIED_UNIVERSITY)

    def test_empty_plan_has_no_verified_data(self):
        payload = complete_degree_payload()
        payload["plan_estudios"] = None
        assessment = assess_plan_quality(payload, "boe")
        self.assertEqual(assessment["estado"], QUALITY_NO_VERIFIED_DATA)
        self.assertFalse(assessment["publicable"])

    def test_persisted_complete_candidate_is_promoted(self):
        payload = complete_degree_payload()
        candidate = payload.pop("plan_estudios")
        payload["plan_estudios"] = None
        payload["candidato_plan_estudios"] = candidate

        result = promote_verified_candidate(payload)

        self.assertTrue(result["promoted"])
        self.assertEqual(payload["plan_estudios"], candidate)
        self.assertNotIn("candidato_plan_estudios", payload)
        self.assertTrue(payload["calidad_datos"]["publicable"])
        self.assertEqual(payload["estado_fuente"], "verificada")

    def test_candidate_does_not_replace_existing_curriculum_detail(self):
        payload = complete_degree_payload()
        current = {
            "elementos_curriculares": [
                {"nombre_elemento": "Materia existente", "creditos_ects": 6}
            ]
        }
        candidate = payload.pop("plan_estudios")
        payload["plan_estudios"] = current
        payload["candidato_plan_estudios"] = candidate

        result = promote_verified_candidate(payload)

        self.assertFalse(result["promoted"])
        self.assertEqual(result["reason"], "plan_actual_con_detalle_preservado")
        self.assertEqual(payload["plan_estudios"], current)
        self.assertEqual(payload["candidato_plan_estudios"], candidate)

    def test_manifestly_excessive_ects_are_not_complete(self):
        payload = complete_degree_payload()
        payload["titulo"] = "Máster Universitario en Estudios Literarios"
        payload["nivel_academico"] = "Máster"
        payload["plan_estudios"]["elementos_curriculares"] = [
            {"nombre_elemento": f"Materia {index}", "creditos_ects": 6}
            for index in range(74)
        ]
        status = get_curriculum_completeness_status(payload)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["status"], "inconsistencia_exceso_ects")

    def test_declared_total_allows_large_explicit_optional_offer(self):
        payload = complete_degree_payload()
        payload["titulo"] = "Máster Universitario en Estudios Avanzados"
        payload["nivel_academico"] = "Máster"
        payload["plan_estudios"] = {
            "resumen_creditos": {"Créditos Totales": "90"},
            "elementos_curriculares": (
                [
                    {"nombre_elemento": f"Obligatoria {index}", "creditos_ects": 6, "caracter": "OB"}
                    for index in range(7)
                ]
                + [
                    {"nombre_elemento": f"Optativa {index}", "creditos_ects": 6, "caracter": "OP"}
                    for index in range(45)
                ]
            ),
        }
        status = get_curriculum_completeness_status(payload)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "completo_normativo")


if __name__ == "__main__":
    unittest.main()
