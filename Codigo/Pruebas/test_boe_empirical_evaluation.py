import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from boe_empirical_evaluation import EMPIRICAL_BOE_CASES, extract_reference_subjects


class TestBOEEmpiricalEvaluation(unittest.TestCase):
    def test_reference_extractor_handles_omitted_rowspan_cells(self):
        html = """
        <table>
          <tr><th>Módulo</th><th>Asignatura</th><th>Carácter</th><th>ECTS</th></tr>
          <tr><td>Fundamentos</td><td>Álgebra</td><td>FB</td><td>6</td></tr>
          <tr><td>Cálculo</td><td>OB</td><td>6</td></tr>
          <tr><td>Total</td><td>12</td></tr>
        </table>
        """
        subjects = extract_reference_subjects(html, 0)
        self.assertEqual(set(subjects.values()), {"Álgebra", "Cálculo"})

    def test_benchmark_covers_diverse_official_formats(self):
        self.assertEqual(len(EMPIRICAL_BOE_CASES), 5)
        self.assertEqual({case["expected_ects"] for case in EMPIRICAL_BOE_CASES}, {60.0, 90.0, 240.0})
        self.assertTrue(any(case["id"] == "BOE-A-2025-21807" for case in EMPIRICAL_BOE_CASES))


if __name__ == "__main__":
    unittest.main()
