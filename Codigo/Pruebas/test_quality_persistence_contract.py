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
from payload_contract import validate_degree_payload


def complete_plan():
    return {
        "nombre_plan": "Grado en Ingeniería Informática",
        "elementos_curriculares": [
            {"nombre_elemento": f"Asignatura {index}", "creditos_ects": 6}
            for index in range(40)
        ],
    }


class TestQualityPersistenceContract(unittest.TestCase):
    def test_degree_payload_contract_detects_structural_errors_without_rejecting_partiality(self):
        result = validate_degree_payload({
            "codigo_estudio": "2500001",
            "universidad_codigo": "099",
            "titulo": "Grado de prueba",
            "plan_estudios": {"elementos_curriculares": [{
                "nombre_elemento": "Álgebra", "creditos_ects": "6"
            }]},
        })
        self.assertTrue(result["valid"])
        invalid = validate_degree_payload({
            "codigo_estudio": "x", "universidad_codigo": "099", "titulo": "Prueba",
            "plan_estudios": {"elementos_curriculares": [{"nombre_elemento": "", "creditos_ects": 999}]},
        })
        self.assertFalse(invalid["valid"])
        self.assertIn("codigo_estudio_invalido", invalid["issues"])
        self.assertIn("elemento_0_ects_fuera_de_rango", invalid["issues"])

    def test_persistence_archives_only_real_degree_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "degree.json")
            partition_path = os.path.join(temp_dir, "partition.json")
            history_dir = os.path.join(temp_dir, "history")
            kwargs = {
                "plan_file": plan_path,
                "d_code": "2500001",
                "d_title": "Grado en Ingeniería Informática",
                "u_code": "099",
                "u_name": "Universidad de Prueba",
                "nivel_academico": "Grado",
                "boe_url": "https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf",
                "origen_fuente": "boe",
            }
            with patch("degree_persistence.DEGREE_HISTORY_DIR", history_dir), \
                 patch("degree_persistence.DEGREE_HISTORY_ENABLED", True), \
                 patch("degree_persistence.get_plan_filepath", return_value=partition_path):
                save_degree_payload(plan_estudios=complete_plan(), **kwargs)
                # Cambiar solo la marca temporal no debe generar una copia.
                save_degree_payload(plan_estudios=complete_plan(), **kwargs)
                self.assertEqual(list(os.walk(history_dir)), [])
                changed = complete_plan()
                changed["elementos_curriculares"].append({"nombre_elemento": "Nueva", "creditos_ects": 6})
                save_degree_payload(plan_estudios=changed, **kwargs)

            archived = [
                os.path.join(root, filename)
                for root, _, files in os.walk(history_dir)
                for filename in files
                if filename.endswith(".json")
            ]
            self.assertEqual(len(archived), 1)
            with open(archived[0], encoding="utf-8") as handle:
                snapshot = json.load(handle)
            self.assertEqual(len(snapshot["plan_estudios"]["elementos_curriculares"]), 40)
            with open(plan_path, encoding="utf-8") as handle:
                current = json.load(handle)
            self.assertNotEqual(snapshot["snapshot_hash"], current["snapshot_hash"])

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
