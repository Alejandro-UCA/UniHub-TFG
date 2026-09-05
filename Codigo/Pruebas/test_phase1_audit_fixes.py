import unittest
import threading
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers import (
    sanitize_subject_name,
    classify_subject_caracter,
    is_spurious_or_administrative_subject,
    unreverse_text
)
from pipelines.parte4_asignaturas import SubjectGuideCache, resolve_candidate_subject_guide_urls
from core.downloader import RUCTDownloader, normalize_url
from pipelines.parte2_web_crawler import normalize_url as parte2_normalize_url
from pipelines.parte2_web_crawler import is_valid_web_url


class TestPhase1AuditFixes(unittest.TestCase):
    def test_lossless_utf8_mojibake_decoding(self):
        """Verifica que el sanitizador corrige mojibake sin destruir diacríticos catalanes, valencianos o gallegos."""
        cases = [
            ("Ã³ptica", "óptica"),
            ("ProgramaciÃ³n", "Programación"),
            ("Treball Fi de Grau en Enginyeria InformÃ tica", "Treball Fi de Grau en Enginyeria Informàtica"),
            ("OrganitzaciÃ³ d'Empreses", "Organització d'Empreses"),
            ("QuÃ­mica OrgÃ nica", "Química Orgànica"),
            ("EnxeÃ±arÃ­a de CamiÃ±os", "Enxeñaría de Camiños"),
            ("FÃ­sica TeÃ³rica", "Física Teórica"),
        ]
        for raw, expected in cases:
            self.assertEqual(sanitize_subject_name(raw), expected)

    def test_classify_subject_caracter_word_boundaries(self):
        """Verifica que palabras como Topología u Óptica no se clasifiquen erróneamente como OP."""
        self.assertEqual(classify_subject_caracter("Topología"), "OB")
        self.assertEqual(classify_subject_caracter("Óptica y Optometría"), "OB")
        self.assertEqual(classify_subject_caracter("Cooperación Internacional"), "OB")
        self.assertEqual(classify_subject_caracter("Operaciones Básicas"), "OB")
        
        # Siglas y tokens exactos
        self.assertEqual(classify_subject_caracter("FB"), "FB")
        self.assertEqual(classify_subject_caracter("FBA"), "FB")
        self.assertEqual(classify_subject_caracter("OP"), "OP")
        self.assertEqual(classify_subject_caracter("OPT"), "OP")
        self.assertEqual(classify_subject_caracter("OB"), "OB")
        self.assertEqual(classify_subject_caracter("OBL"), "OB")
        self.assertEqual(classify_subject_caracter("PE"), "PE")
        self.assertEqual(classify_subject_caracter("PEX"), "PE")
        self.assertEqual(classify_subject_caracter("TFG"), "TFG/TFM")
        self.assertEqual(classify_subject_caracter("TFM"), "TFG/TFM")
        
        # Frases multilingües
        self.assertEqual(classify_subject_caracter("Formació Bàsica"), "FB")
        self.assertEqual(classify_subject_caracter("Optativa"), "OP")
        self.assertEqual(classify_subject_caracter("Hautazko"), "OP")
        self.assertEqual(classify_subject_caracter("Pràctiques Externes"), "PE")
        self.assertEqual(classify_subject_caracter("Kanpoko Praktikak"), "PE")
        self.assertEqual(classify_subject_caracter("Treball Fi de Grau"), "TFG/TFM")

    def test_subject_guide_cache_thread_safety(self):
        """Verifica que SubjectGuideCache maneje lecturas y escrituras concurrentes sin race conditions ni deadlocks."""
        cache = SubjectGuideCache(db_path=":memory:")
        errors = []

        def worker(w_id):
            try:
                for i in range(50):
                    url = f"https://example.com/guia/{w_id}_{i}"
                    data = {"temario": [f"Tema {i}"], "creditos": 6.0}
                    cache.set(url=url, data=data, u_code=str(w_id), asig_code=str(i))
                    read_back = cache.get(url=url)
                    if not read_back or read_back.get("temario") != [f"Tema {i}"]:
                        errors.append(f"Mismatch in worker {w_id} iteration {i}")
            except Exception as e:
                errors.append(f"Worker {w_id} exception: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors encountered: {errors}")

    def test_normalize_url_with_base_url(self):
        """Verifica la resolución correcta de URLs relativas con base_url."""
        base = "https://www.uca.es/grado-informatica/plan/"
        rel = "../asignaturas/guia_101.pdf"
        resolved = normalize_url(rel, base_url=base)
        self.assertEqual(resolved, "https://www.uca.es/grado-informatica/asignaturas/guia_101.pdf")

    def test_parte2_exposes_normalize_url_for_source_deduplication(self):
        """Evita que Parte 2 vuelva a fallar al deduplicar una fuente directa."""
        self.assertEqual(
            parte2_normalize_url("https://www.uca.es/plan.pdf"),
            "https://www.uca.es/plan.pdf",
        )

    def test_parte2_rejects_malformed_absolute_links_but_keeps_relative_links(self):
        self.assertFalse(is_valid_web_url("http:///catalogo/guia.pdf"))
        self.assertFalse(is_valid_web_url("javascript:alert(1)"))
        self.assertTrue(is_valid_web_url("../catalogo/guia.pdf"))

    def test_resolve_candidate_guide_urls_subdomain_formatting(self):
        """Verifica que el generador de URLs candidatas no duplique www en subdominios."""
        elem = {
            "codigo_asignatura": "7001",
            "nombre_elemento": "Álgebra Lineal",
            "url_guia_docente": ""
        }
        urls = resolve_candidate_subject_guide_urls(
            elem=elem,
            u_code="025",
            u_web="https://www.uca.es",
            d_code="2501"
        )
        self.assertTrue(any("https://asignaturas.uca.es/" in u for u in urls))
        self.assertFalse(any("https://asignaturas.www.uca.es/" in u for u in urls))


if __name__ == "__main__":
    unittest.main()
