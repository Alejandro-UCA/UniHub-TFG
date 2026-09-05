import unittest
import sys
import os
import tempfile
import json
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from ruct_xls_parser import extract_participating_universities
from fase1_parte2_web_crawler import (
    normalize_joint_title,
    propagate_interuniversity_and_shared_boe_plans,
)


class TestInteruniversityConsortiumRecovery(unittest.TestCase):
    def test_extract_participating_universities(self):
        title = (
            "Máster Universitario en Ciberseguridad por la Universidad Carlos III de Madrid, "
            "la Universidad Politécnica de Madrid y la Universidad de Alcalá"
        )
        univs = extract_participating_universities(title)
        self.assertEqual(len(univs), 3)
        self.assertIn("Universidad Carlos III de Madrid", univs)
        self.assertIn("Universidad Politécnica de Madrid", univs)
        self.assertIn("Universidad de Alcalá", univs)

        single_title = "Grado en Ingeniería Informática por la Universidad de Granada"
        univs_single = extract_participating_universities(single_title)
        self.assertEqual(len(univs_single), 1)
        self.assertEqual(univs_single[0], "Universidad de Granada")

        no_consortium = "Grado en Matemáticas"
        self.assertEqual(extract_participating_universities(no_consortium), [])

    def test_normalize_joint_title_consortium_stripping(self):
        t1 = "Máster Universitario en Ciberseguridad por la Universidad Carlos III de Madrid y la Universidad Autónoma de Madrid"
        t2 = "Máster Universitario en Ciberseguridad por la Universidad Autónoma de Madrid y la Universidad Carlos III de Madrid"

        norm1 = normalize_joint_title(t1, strip_consortium=True)
        norm2 = normalize_joint_title(t2, strip_consortium=True)

        self.assertEqual(norm1, "master universitario en ciberseguridad")
        self.assertEqual(norm2, "master universitario en ciberseguridad")
        self.assertEqual(norm1, norm2)

    def test_propagate_interuniversity_plans_delegation(self):
        temp_dir = tempfile.mkdtemp(prefix="unihub_consortium_test_")
        try:
            plan_donor = {
                "codigo_estudio": "4315001",
                "titulo": "Máster Universitario en Ciencia de Datos por la Universidad Autónoma de Madrid y la Universidad Carlos III de Madrid",
                "nivel_academico": "Máster Universitario",
                "universidad_codigo": "028",
                "universidad_nombre": "Universidad Autónoma de Madrid",
                "interuniversitario": True,
                "web_fuente_directa_url": "https://uam.es/master-datos",
                "plan_estudios": {
                    "creditos_totales": 60,
                    "elementos_curriculares": [
                        {"nombre_elemento": f"Materia {i}", "creditos_ects": "10", "caracter": "OB"}
                        for i in range(1, 7)
                    ]
                },
                "origen_fuente": "portal_facultad"
            }

            plan_target = {
                "codigo_estudio": "4315002",
                "titulo": "Máster Universitario en Ciencia de Datos por la Universidad Carlos III de Madrid y la Universidad Autónoma de Madrid",
                "nivel_academico": "Máster Universitario",
                "universidad_codigo": "038",
                "universidad_nombre": "Universidad Carlos III de Madrid",
                "interuniversitario": True,
                "plan_estudios": None,
                "origen_fuente": ""
            }

            donor_path = os.path.join(temp_dir, "plan_028_4315001.json")
            target_path = os.path.join(temp_dir, "plan_038_4315002.json")

            with open(donor_path, "w", encoding="utf-8") as f:
                json.dump(plan_donor, f, ensure_ascii=False)

            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(plan_target, f, ensure_ascii=False)

            stats = propagate_interuniversity_and_shared_boe_plans(temp_dir)
            self.assertEqual(stats["interuniv_shared_rescued"], 1)

            with open(target_path, "r", encoding="utf-8") as f:
                rescued_target = json.load(f)

            self.assertIsNotNone(rescued_target.get("plan_estudios"))
            self.assertEqual(len(rescued_target["plan_estudios"]["elementos_curriculares"]), 6)
            self.assertEqual(rescued_target["origen_fuente"], "interuniversitario_compartido")
            self.assertEqual(rescued_target["fuente_delegada_universidad"], "Universidad Autónoma de Madrid")
            self.assertEqual(rescued_target["web_fuente_directa_url"], "https://uam.es/master-datos")
            self.assertIn("universidades_participantes", rescued_target)
            self.assertIn("Universidad Carlos III de Madrid", rescued_target["universidades_participantes"])
            self.assertIn("Universidad Autónoma de Madrid", rescued_target["universidades_participantes"])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
