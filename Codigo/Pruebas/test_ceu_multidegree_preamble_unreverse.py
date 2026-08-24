import unittest
import sys
import os

sys.path.insert(0, os.path.abspath('Codigo/Crawler'))

from parsers import (
    unreverse_text,
    is_section_matching,
    extract_degree_core_keywords,
    RE_PREAMBLE_REJECTION
)

class TestCEUMultiDegreePreambleUnreverse(unittest.TestCase):

    def test_unreverse_reversed_degree_headers(self):
        sample = "OXENA UEC-olbaP naS dadisrevinU al rop etrA led airotsiH ne adaudarG o odaudarG ed olutít led soidutse ed nalP"
        unrev = unreverse_text(sample)
        self.assertIn("Plan de estudios del", unrev)
        self.assertIn("Historia del Arte", unrev)
        self.assertIn("ANEXO", unrev)

    def test_unreverse_reversed_subjects(self):
        sample = "laveideM odnuM led sorbiL sednarG"
        unrev = unreverse_text(sample)
        self.assertEqual(unrev, "Grandes Libros del Mundo Medieval")

    def test_preamble_rejection(self):
        preambles = [
            "títulos oficiales relacionados a continuación:",
            "Este Rectorado ha resuelto ordenar la publicación de los planes de estudios",
            "títulos por Acuerdo del Consejo de Ministros de 4 de septiembre",
            "haberse establecido el carácter oficial de los títulos de Grado siguientes"
        ]
        for p in preambles:
            self.assertTrue(bool(RE_PREAMBLE_REJECTION.search(p)), f"Failed to reject preamble: {p}")

    def test_genuine_degree_section_not_rejected(self):
        genuine_headers = [
            "Plan de estudios del título de Graduado o Graduada en Ingeniería Biomédica / Bachelor in Biomedical Engineering por la Universidad San Pablo-CEU",
            "ANEXO I. Plan de estudios del título de Máster Universitario en Estudios de Seguridad Internacional por la Universidad Internacional de La Rioja",
            "Plan de estudios del título de Graduado en Odontología por la Universidad San Pablo-CEU"
        ]
        for g in genuine_headers:
            self.assertFalse(bool(RE_PREAMBLE_REJECTION.search(g)), f"Incorrectly rejected genuine header: {g}")

    def test_section_matching_biomedica_vs_odontologia(self):
        biomedica_kw = extract_degree_core_keywords("Graduado en Ingeniería Biomédica", "Universidad San Pablo-CEU")
        odontologia_kw = extract_degree_core_keywords("Graduado en Odontología", "Universidad San Pablo-CEU")
        
        self.assertFalse(is_section_matching(odontologia_kw, biomedica_kw))
        self.assertTrue(is_section_matching(biomedica_kw, biomedica_kw))


if __name__ == "__main__":
    unittest.main()
