import os
import sys
import unittest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from data_quality import (
    QUALITY_NO_VERIFIED_DATA,
    QUALITY_PARTIAL,
    QUALITY_PENDING_REVIEW,
    QUALITY_VERIFIED_BOE,
    QUALITY_VERIFIED_UNIVERSITY,
    apply_plan_quality,
    assess_plan_quality,
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

    def test_empty_plan_has_no_verified_data(self):
        payload = complete_degree_payload()
        payload["plan_estudios"] = None
        assessment = assess_plan_quality(payload, "boe")
        self.assertEqual(assessment["estado"], QUALITY_NO_VERIFIED_DATA)
        self.assertFalse(assessment["publicable"])


if __name__ == "__main__":
    unittest.main()
