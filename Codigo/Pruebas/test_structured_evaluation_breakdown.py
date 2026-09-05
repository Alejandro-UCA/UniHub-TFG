import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from subject_guide_quality import parse_evaluation_breakdown, assess_subject_guide_quality, annotate_subject_guide_quality


class TestStructuredEvaluationBreakdown(unittest.TestCase):
    def test_standard_breakdown_100_percent(self):
        text = "Examen final: 50%. Evaluación continua: 20%. Prácticas de laboratorio: 20%. Trabajos y proyectos: 10%."
        res = parse_evaluation_breakdown(text)
        self.assertTrue(res["desglose_valido"])
        self.assertEqual(res["suma_porcentual"], 100.0)
        self.assertEqual(res["examen_final"], 50.0)
        self.assertEqual(res["evaluacion_continua"], 20.0)
        self.assertEqual(res["practicas_laboratorio"], 20.0)
        self.assertEqual(res["trabajos_proyectos"], 10.0)
        self.assertEqual(res["otros"], 0.0)

    def test_breakdown_with_tolerance(self):
        text = "Examen teórico: 33.3%, Prácticas de laboratorio: 33.3%, Trabajos individuales: 33.3%"
        res = parse_evaluation_breakdown(text)
        self.assertTrue(res["desglose_valido"])
        self.assertAlmostEqual(res["suma_porcentual"], 99.9, places=1)

    def test_breakdown_with_invalid_sum(self):
        text = "Prueba final: 40%. Prácticas: 30%."
        res = parse_evaluation_breakdown(text)
        self.assertFalse(res["desglose_valido"])
        self.assertEqual(res["suma_porcentual"], 70.0)
        self.assertEqual(res["examen_final"], 40.0)
        self.assertEqual(res["practicas_laboratorio"], 30.0)

    def test_ignores_minimum_score_thresholds(self):
        text = (
            "Examen final: 60% (es necesario obtener una nota mínima del 40% para mediar). "
            "Prácticas en ordenador: 40% (al menos un 50% de asistencia obligatoria)."
        )
        res = parse_evaluation_breakdown(text)
        self.assertTrue(res["desglose_valido"])
        self.assertEqual(res["suma_porcentual"], 100.0)
        self.assertEqual(res["examen_final"], 60.0)
        self.assertEqual(res["practicas_laboratorio"], 40.0)

    def test_integration_assess_subject_guide_quality(self):
        guide = {
            "nombre_asignatura": "Sistemas Distribuidos",
            "codigo_asignatura": "802145",
            "creditos_ects": "6",
            "temario": "Tema 1: RPC, Tema 2: Consenso Paxos, Tema 3: Replicación",
            "sistema_evaluacion": "Examen final: 70%. Prácticas de laboratorio: 30%.",
        }
        assessment = assess_subject_guide_quality(
            guide,
            expected_name="Sistemas Distribuidos",
            expected_code="802145",
            source_url="https://uam.es/guias/802145",
        )
        self.assertIn("evaluacion_desglose", assessment)
        breakdown = assessment["evaluacion_desglose"]
        self.assertTrue(breakdown["desglose_valido"])
        self.assertEqual(breakdown["suma_porcentual"], 100.0)
        self.assertEqual(breakdown["examen_final"], 70.0)
        self.assertEqual(breakdown["practicas_laboratorio"], 30.0)

        annotated = annotate_subject_guide_quality(guide)
        self.assertIn("calidad_extraccion", annotated)
        self.assertIn("evaluacion_desglose", annotated["calidad_extraccion"])


if __name__ == "__main__":
    unittest.main()
