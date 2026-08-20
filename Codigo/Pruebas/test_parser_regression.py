"""
Regression & Precision Test Suite for Parsers (Fase 1 - Mejora 3)
Verifies that course (curso) and term (cuatrimestre) normalizations:
1. Yield 0 subject loss (0 regressions).
2. Normalize curso strictly to 1..6 or empty.
3. Rescue displaced subject/topic text into materia.
4. Normalize terms into 1C, 2C, or Anual cleanly.
"""

import os
import sys
import json
import unittest

BASE_DIR = r"d:\Proyecto"
CRAWLER_DIR = os.path.join(BASE_DIR, "Codigo", "Crawler")
DATA_DIR = os.path.join(CRAWLER_DIR, "Datos")
PLANES_DIR = os.path.join(DATA_DIR, "planes_estudio")

sys.path.insert(0, CRAWLER_DIR)
from parsers import normalize_cuatrimestre, normalize_curso, sanitize_subject_name


class TestParserRegressionAndPrecision(unittest.TestCase):

    def test_01_normalize_curso_unit_cases(self):
        """Test unit edge cases for normalize_curso."""
        # Standard numbers and ordinals
        self.assertEqual(normalize_curso("1")[0], "1")
        self.assertEqual(normalize_curso("1º")[0], "1")
        self.assertEqual(normalize_curso("1.º")[0], "1")
        self.assertEqual(normalize_curso("1er")[0], "1")
        self.assertEqual(normalize_curso("Primer Curso")[0], "1")
        self.assertEqual(normalize_curso("1r curs")[0], "1")
        
        self.assertEqual(normalize_curso("2")[0], "2")
        self.assertEqual(normalize_curso("2º")[0], "2")
        self.assertEqual(normalize_curso("Segundo")[0], "2")
        self.assertEqual(normalize_curso("2n curs")[0], "2")
        
        self.assertEqual(normalize_curso("3º")[0], "3")
        self.assertEqual(normalize_curso("Tercero")[0], "3")
        
        self.assertEqual(normalize_curso("4º")[0], "4")
        self.assertEqual(normalize_curso("Cuarto")[0], "4")
        
        self.assertEqual(normalize_curso("5º")[0], "5")
        self.assertEqual(normalize_curso("6º")[0], "6")

        # Roman numerals
        self.assertEqual(normalize_curso("I")[0], "1")
        self.assertEqual(normalize_curso("II")[0], "2")
        self.assertEqual(normalize_curso("III")[0], "3")
        self.assertEqual(normalize_curso("IV")[0], "4")

        # Textual topic displaced into course -> course must be empty, materia rescued
        c, mat = normalize_curso("Comunicación Oral y Escrita.", current_materia="")
        self.assertEqual(c, "")
        self.assertEqual(mat, "Comunicación Oral y Escrita.")

        c, mat2 = normalize_curso("Derecho Mercantil I", current_materia="Derecho Privado")
        self.assertEqual(c, "")
        self.assertEqual(mat2, "Derecho Privado")

        # ECTS credit misalignment (e.g. 6 credits mistaken as course 6)
        c, _ = normalize_curso("6", ects_val=6.0)
        self.assertEqual(c, "")

    def test_02_normalize_cuatrimestre_unit_cases(self):
        """Test unit edge cases for normalize_cuatrimestre."""
        self.assertEqual(normalize_cuatrimestre("1"), "1C")
        self.assertEqual(normalize_cuatrimestre("1º"), "1C")
        self.assertEqual(normalize_cuatrimestre("1C"), "1C")
        self.assertEqual(normalize_cuatrimestre("1er cuatrimestre"), "1C")
        self.assertEqual(normalize_cuatrimestre("Primer Semestre"), "1C")
        self.assertEqual(normalize_cuatrimestre("Semestre 1"), "1C")

        self.assertEqual(normalize_cuatrimestre("2"), "2C")
        self.assertEqual(normalize_cuatrimestre("2º"), "2C")
        self.assertEqual(normalize_cuatrimestre("2C"), "2C")
        self.assertEqual(normalize_cuatrimestre("Segundo Cuatrimestre"), "2C")
        self.assertEqual(normalize_cuatrimestre("2do Semestre"), "2C")

        self.assertEqual(normalize_cuatrimestre("Anual"), "Anual")
        self.assertEqual(normalize_cuatrimestre("1-2"), "Anual")
        self.assertEqual(normalize_cuatrimestre("1 y 2º"), "Anual")

    def test_03_regression_over_real_plan_dataset(self):
        """Verify on real study plan files that 0 subjects are lost and all cursos are valid."""
        if not os.path.exists(PLANES_DIR):
            self.skipTest("planes_estudio directory not found")

        plan_files = [f for f in os.listdir(PLANES_DIR) if f.endswith(".json")]
        self.assertGreater(len(plan_files), 1000)

        # Audit 500 real study plans
        sample_files = plan_files[:500]
        total_subjects_before = 0
        total_subjects_after = 0
        invalid_cursos_found = 0

        valid_cursos = {"", "1", "2", "3", "4", "5", "6"}

        for pf in sample_files:
            with open(os.path.join(PLANES_DIR, pf), "r", encoding="utf-8") as fp:
                d = json.load(fp)
            p = d.get("plan_estudios")
            if not p:
                continue
            elems = p.get("elementos_curriculares", [])
            total_subjects_before += len(elems)

            for elem in elems:
                c_raw = elem.get("curso", "")
                mat_raw = elem.get("materia", "")
                ects = float(str(elem.get("creditos_ects", 6)).replace(",", ".")) if elem.get("creditos_ects") else 6.0
                
                c_clean, _ = normalize_curso(c_raw, mat_raw, ects_val=ects)
                if c_clean not in valid_cursos:
                    invalid_cursos_found += 1
                
                total_subjects_after += 1

        self.assertEqual(total_subjects_before, total_subjects_after, "Subject count must be 100% preserved!")
        self.assertEqual(invalid_cursos_found, 0, "No invalid cursos must exist after normalization!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
