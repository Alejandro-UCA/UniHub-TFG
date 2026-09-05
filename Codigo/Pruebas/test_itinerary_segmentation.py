import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from quality.curriculum_validator import (
    detect_curriculum_itineraries,
    get_curriculum_completeness_status,
    is_curriculum_complete,
)


class TestItinerarySegmentation(unittest.TestCase):
    def setUp(self):
        # 30 asignaturas obligatorias/básicas de 6 ECTS = 180 ECTS
        self.common_subjects = [
            {
                "nombre_elemento": f"Asignatura Troncal {i}",
                "creditos_ects": "6",
                "caracter": "FB" if i <= 10 else "OB",
                "curso": "1" if i <= 10 else ("2" if i <= 20 else "3"),
            }
            for i in range(1, 31)
        ]
        # TFG de 12 ECTS
        self.common_subjects.append({
            "nombre_elemento": "Trabajo Fin de Grado",
            "creditos_ects": "12",
            "caracter": "TFG",
            "curso": "4",
        })
        # Troncal común total = 192 ECTS

        # Mención 1: Computación (8 asignaturas de 6 ECTS = 48 ECTS)
        self.mencion_comp = [
            {
                "nombre_elemento": f"Materia Comp {i} (Mención en Computación)",
                "creditos_ects": "6",
                "caracter": "OP",
                "curso": "4",
            }
            for i in range(1, 9)
        ]

        # Mención 2: Sistemas de Información (8 asignaturas de 6 ECTS = 48 ECTS)
        self.mencion_si = [
            {
                "nombre_elemento": f"Materia SI {i}",
                "creditos_ects": "6",
                "caracter": "OP",
                "curso": "4",
                "mencion": "Sistemas de Información",
            }
            for i in range(1, 9)
        ]

    def test_detect_curriculum_itineraries_valid(self):
        all_elements = self.common_subjects + self.mencion_comp + self.mencion_si
        self.assertEqual(len(all_elements), 31 + 8 + 8)

        res = detect_curriculum_itineraries(all_elements, required_ects=240.0)
        self.assertTrue(res["tiene_itinerarios"])
        self.assertTrue(res["itinerarios_validos"])
        self.assertEqual(res["ects_troncal_comun"], 192.0)

        # Ambas menciones deben sumar exactamente 48 ECTS y 240 ECTS en total
        itinerarios = res["itinerarios"]
        self.assertEqual(len(itinerarios), 2)

        total_por_itin = res["total_ects_por_itinerario"]
        self.assertIn("Computación", total_por_itin)
        self.assertIn("Sistemas De Información", total_por_itin)
        self.assertEqual(total_por_itin["Computación"], 240.0)
        self.assertEqual(total_por_itin["Sistemas De Información"], 240.0)

    def test_completeness_status_with_valid_menciones(self):
        all_elements = self.common_subjects + self.mencion_comp + self.mencion_si
        degree_dict = {
            "titulo": "Grado en Ingeniería Informática",
            "nivel_academico": "Grado",
            "plan_estudios": {
                "elementos_curriculares": all_elements,
                # Sin resumen_creditos ni total declarado:
                # La suma bruta de filas es 288 ECTS (> 240 ECTS).
            }
        }

        status = get_curriculum_completeness_status(degree_dict)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "completo_con_menciones")
        self.assertEqual(status["total_ects_obtained"], 240.0)
        self.assertEqual(status["total_ects_listed"], 288.0)
        self.assertIsNotNone(status.get("segmentacion_menciones"))

        # is_curriculum_complete debe confirmar completitud
        self.assertTrue(is_curriculum_complete(degree_dict))

    def test_invalid_menciones_insufficient_credits(self):
        # Mención incompleta (sólo 2 asignaturas = 12 ECTS en lugar de 48 ECTS)
        incomplete_mencion = [
            {
                "nombre_elemento": f"Materia Incompleta {i} (Mención en Robótica)",
                "creditos_ects": "6",
                "caracter": "OP",
            }
            for i in range(1, 3)
        ]
        elements = self.common_subjects + self.mencion_comp + incomplete_mencion
        res = detect_curriculum_itineraries(elements, required_ects=240.0)
        self.assertTrue(res["tiene_itinerarios"])
        self.assertFalse(res["itinerarios_validos"])


if __name__ == "__main__":
    unittest.main()
