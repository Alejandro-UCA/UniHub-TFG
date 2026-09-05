"""Pruebas unitarias para concordancia web con plantilla de distribución de créditos del BOE."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from extractors.curriculum_recovery import matches_boe_credit_distribution


class TestBoeSummaryWebMatching(unittest.TestCase):
    """Verifica que un candidato web se valide contra el resumen de créditos oficial del BOE."""

    def test_matches_boe_credit_distribution_exact_standard(self):
        # Título estándar de 240 ECTS: 60 FB + 120 OB + 48 OP + 12 TFG
        resumen_boe = {
            "Formación Básica": "60 ECTS",
            "Obligatorias": "120 ECTS",
            "Optativas": "48 ECTS",
            "Trabajo Fin de Grado": "12 ECTS",
            "Total": "240 ECTS",
        }
        elementos_web = []
        # 10 asignaturas FB de 6 ECTS
        for i in range(10):
            elementos_web.append({"nombre_elemento": f"Básica {i}", "creditos_ects": 6.0, "caracter": "FB"})
        # 20 asignaturas OB de 6 ECTS
        for i in range(20):
            elementos_web.append({"nombre_elemento": f"Obligatoria {i}", "creditos_ects": 6.0, "caracter": "OB"})
        # 1 TFG de 12 ECTS
        elementos_web.append({"nombre_elemento": "TFG", "creditos_ects": 12.0, "caracter": "TFG"})

        self.assertTrue(matches_boe_credit_distribution(elementos_web, resumen_boe, tolerance=6.0))

    def test_matches_boe_credit_distribution_rejects_incompatible(self):
        resumen_boe = {
            "Formación Básica": "60",
            "Obligatorias": "120",
            "Trabajo Fin de Grado": "12",
            "Total": "240",
        }
        # Candidato web con solo 2 materias (12 ECTS)
        elementos_incompletos = [
            {"nombre_elemento": "Materia A", "creditos_ects": 6.0, "caracter": "FB"},
            {"nombre_elemento": "Materia B", "creditos_ects": 6.0, "caracter": "OB"},
        ]
        self.assertFalse(matches_boe_credit_distribution(elementos_incompletos, resumen_boe))

    def test_matches_boe_credit_distribution_handles_tolerance(self):
        resumen_boe = {
            "Formación Básica": "60",
            "Obligatorias": "120",
            "Trabajo Fin de Grado": "12",
        }
        # Web tiene 54 FB (tolerancia <= 6.0 permite concordar)
        elementos_web = [
            {"nombre_elemento": f"Básica {i}", "creditos_ects": 6.0, "caracter": "FB"}
            for i in range(9)
        ] + [
            {"nombre_elemento": f"Obligatoria {i}", "creditos_ects": 6.0, "caracter": "OB"}
            for i in range(20)
        ] + [
            {"nombre_elemento": "TFG", "creditos_ects": 12.0, "caracter": "TFG"}
        ]
        self.assertTrue(matches_boe_credit_distribution(elementos_web, resumen_boe, tolerance=6.0))


if __name__ == "__main__":
    unittest.main()
