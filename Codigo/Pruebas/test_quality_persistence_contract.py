import json
import os
import queue
import sys
import tempfile
import unittest
from unittest.mock import patch


CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if CRAWLER_DIR not in sys.path:
    sys.path.insert(0, CRAWLER_DIR)

import fase1_parte1_ruct_boe as ruct_boe
from degree_persistence import save_degree_payload


def complete_plan():
    return {
        "nombre_plan": "Grado en Ingeniería Informática",
        "elementos_curriculares": [
            {"nombre_elemento": f"Asignatura {index}", "creditos_ects": 6}
            for index in range(40)
        ],
    }


class TestQualityPersistenceContract(unittest.TestCase):
    def test_persistence_quarantines_partial_candidate_and_keeps_verified_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "2500001.json")
            common = {
                "plan_file": plan_path,
                "d_code": "2500001",
                "d_title": "Grado en Ingeniería Informática",
                "u_code": "",
                "u_name": "Universidad de Prueba",
                "nivel_academico": "Grado",
                "boe_url": "https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf",
                "origen_fuente": "boe",
            }
            save_degree_payload(plan_estudios=complete_plan(), **common)
            with open(plan_path, encoding="utf-8") as payload_file:
                verified = json.load(payload_file)
            self.assertEqual(verified["estado_calidad"], "verificado_boe")
            original_plan = verified["plan_estudios"]

            save_degree_payload(
                plan_estudios={"elementos_curriculares": []},
                existing_data=verified,
                **common,
            )
            with open(plan_path, encoding="utf-8") as payload_file:
                quarantined = json.load(payload_file)
            self.assertEqual(quarantined["estado_calidad"], "verificado_boe")
            self.assertEqual(quarantined["plan_estudios"], original_plan)
            self.assertEqual(quarantined["estado_ultima_extraccion"], "parcial")
            self.assertEqual(quarantined["candidato_plan_estudios"], {"elementos_curriculares": []})

    def test_persistence_creates_a_missing_partition_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "nueva-universidad", "5600001.json")
            save_degree_payload(
                plan_file=plan_path,
                d_code="5600001",
                d_title="Programa de Doctorado en Biomedicina",
                u_code="",
                u_name="Universidad de Prueba",
                nivel_academico="Doctorado",
                plan_estudios=None,
                source_status="sin_resolucion_boe_sin_dato",
            )
            self.assertTrue(os.path.exists(plan_path))
            with open(plan_path, encoding="utf-8") as payload_file:
                payload = json.load(payload_file)
            self.assertIsNone(payload["plan_estudios"])
            self.assertEqual(payload["estado_calidad"], "sin_datos_verificados")

    def test_degree_without_boe_never_receives_a_generated_doctoral_plan(self):
        tasks = queue.Queue()
        tasks.put({
            "type": "DEGREE_NO_BOE",
            "d_code": "5600001",
            "d_title": "Programa de Doctorado en Biomedicina",
            "u_code": "001",
            "u_name": "Universidad de Prueba",
            "nivel_academico": "Doctorado",
        })
        tasks.put({"type": "STOP"})
        with patch.object(ruct_boe, "save_degree_payload") as save_payload:
            ruct_boe.pdf_parser_consumer(tasks)
        self.assertEqual(save_payload.call_count, 1)
        self.assertIsNone(save_payload.call_args.kwargs["plan_estudios"])

    def test_european_fallback_contains_no_generated_curriculum_text(self):
        source_path = os.path.join(CRAWLER_DIR, "fase1_parte2_web_crawler.py")
        with open(source_path, encoding="utf-8") as source_file:
            content = source_file.read()
        self.assertNotIn("descripcion_consorcio", content)
        self.assertNotIn("Programa Conjunto de Excelencia Internacional", content)


if __name__ == "__main__":
    unittest.main()
