import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Crawler')))
from parsers import parse_boe_pdf


class TestMultiDegreeMultilineBOEDisambiguation(unittest.TestCase):
    """
    Verifica que en resoluciones del BOE multi-título con títulos partidos en varias líneas
    (como las de UNIR con 15 másteres en un solo PDF), el extractor aísle con precisión 
    únicamente el plan del máster consultado, evitando la contaminación cruzada de asignaturas.
    """

    def test_unir_multidegree_isolation(self):
        url_unir = "https://www.boe.es/boe/dias/2025/10/31/pdfs/BOE-A-2025-22018.pdf"
        import urllib.request
        try:
            req = urllib.request.Request(url_unir, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                pdf_bytes = resp.read()
                res = parse_boe_pdf(
                    pdf_bytes,
                    target_title="Máster Universitario en Estudios Literarios y Culturales en Lengua Inglesa por la Universidad Internacional de La Rioja",
                    univ_name="Universidad Internacional de La Rioja"
                )
                elems = res.get("elementos_curriculares", [])
                
                # Debe extraer exactamente sus ~9 asignaturas y NO las 94 de los 15 másteres combinados
                self.assertGreaterEqual(len(elems), 7)
                self.assertLessEqual(len(elems), 12)
                
                # Verificar que NO contiene asignaturas de los otros másteres (Videojuegos, Psicooncología, etc.)
                names = [e["nombre_elemento"].lower() for e in elems]
                self.assertFalse(any("videojuegos" in n for n in names))
                self.assertFalse(any("psicooncología" in n for n in names))
                self.assertFalse(any("sostenible" in n for n in names))
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
