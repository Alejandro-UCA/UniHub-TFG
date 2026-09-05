import unittest
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from boe_pdf_parser import merge_chronological_boe_curricula

class TestBoeChronologicalMerge(unittest.TestCase):
    def test_merge_base_and_modification_decrees(self):
        # Base plan from 2011 with 10 subjects
        base_plan = {
            "cand_url": "https://www.boe.es/boe/dias/2011/05/10/pdfs/BOE-A-2011-1000.pdf",
            "cand_date": "2011-05-10",
            "resumen_creditos": {"Formación Básica": "60", "Obligatorias": "120", "Optativas": "48", "Trabajo Fin de Grado": "12", "Créditos Totales": "240"},
            "elementos_curriculares": [
                {"nombre_elemento": f"Asignatura Base {i}", "creditos_ects": "6", "caracter": "OB", "curso": "1"}
                for i in range(1, 11)
            ]
        }
        # Modification resolution from 2018 modifying subject 1 and subject 2
        mod_plan = {
            "cand_url": "https://www.boe.es/boe/dias/2018/09/20/pdfs/BOE-A-2018-5000.pdf",
            "cand_date": "2018-09-20",
            "resumen_creditos": {"Créditos Totales": "240"},
            "elementos_curriculares": [
                {"nombre_elemento": "Asignatura Base 1 (Modificada)", "creditos_ects": "6", "caracter": "OB", "curso": "1"},
                {"nombre_elemento": "Asignatura Base 2", "creditos_ects": "9", "caracter": "OB", "curso": "1"},
                {"nombre_elemento": "Nueva Asignatura Optativa", "creditos_ects": "6", "caracter": "OP", "curso": "4"}
            ]
        }

        # Merge list in arbitrary order (mod first, then base)
        merged = merge_chronological_boe_curricula([mod_plan, base_plan])
        
        # Check that total elements includes all base subjects plus new elective
        # Base had 10, mod updated 2 and added 1 -> total should be 11
        self.assertEqual(merged["total_elementos"], 11)
        self.assertEqual(len(merged["boe_urls_procesados"]), 2)
        
        # Check that subject 2 has updated ECTS (9 instead of 6)
        elems_by_name = {e["nombre_elemento"]: e for e in merged["elementos_curriculares"]}
        self.assertEqual(elems_by_name["Asignatura Base 2"]["creditos_ects"], "9")
        self.assertIn("Nueva Asignatura Optativa", elems_by_name)
        self.assertEqual(merged["resumen_creditos"]["Créditos Totales"], "240")

if __name__ == '__main__':
    unittest.main()
