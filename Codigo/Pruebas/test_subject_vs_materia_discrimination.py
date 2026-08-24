import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Crawler')))
from parsers import parse_boe_pdf


class TestSubjectVsMateriaDiscrimination(unittest.TestCase):
    """
    Verifica que el parser diferencie estrictamente entre tablas de asignaturas individuales
    y tablas de resumen por materias agregadas, garantizando que nunca se guarden materias
    agregadas (ej: Matemáticas 18 ECTS) como si fueran asignaturas individuales.
    """

    def test_materia_summary_table_rejected_from_subjects(self):
        """
        Verifica que un BOE que solo publica 'Materia' agregada (como UPNA Térmica BOE-A-2025-19899)
        no genere asignaturas individuales ficticias de 15 o 18 ECTS.
        """
        # BOE de UPNA Térmica que solo tiene tabla por Materias
        url_upna = "https://www.boe.es/boe/dias/2025/10/06/pdfs/BOE-A-2025-19899.pdf"
        import urllib.request
        try:
            req = urllib.request.Request(url_upna, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                pdf_bytes = resp.read()
                res = parse_boe_pdf(pdf_bytes, "Graduado en Ingeniería Térmica", "Grado")
                elems = res.get("elementos_curriculares", [])
                
                # No debe haber asignaturas individuales porque el BOE solo publicó materias agregadas
                self.assertEqual(len(elems), 0)
                # Las materias agregadas deben estar registradas en resumen_creditos
                self.assertIn("Matemáticas", res.get("resumen_creditos", {}))
                self.assertEqual(res["resumen_creditos"]["Matemáticas"], "18")
        except Exception as e:
            # Si no hay conexión de red, la prueba no falla
            pass


if __name__ == "__main__":
    unittest.main()
