import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from extractors.subject_guides import (
    learn_guide_url_template,
    project_missing_guide_urls,
)


class TestSubjectGuideTemplateLearning(unittest.TestCase):
    def test_learn_query_param_template(self):
        known_pairs = [
            ("101", "https://portal.univ.es/asignaturas/guia.php?codigo=101"),
            ("102", "https://portal.univ.es/asignaturas/guia.php?codigo=102"),
            ("103", "https://portal.univ.es/asignaturas/guia.php?codigo=103"),
        ]
        template = learn_guide_url_template(known_pairs)
        self.assertIsNotNone(template)
        self.assertEqual(template, "https://portal.univ.es/asignaturas/guia.php?codigo={code}")

    def test_learn_path_pdf_template(self):
        known_pairs = [
            ("MAT01", "https://ciencias.univ.es/guias/MAT01.pdf"),
            ("MAT02", "https://ciencias.univ.es/guias/MAT02.pdf"),
        ]
        template = learn_guide_url_template(known_pairs)
        self.assertIsNotNone(template)
        self.assertEqual(template, "https://ciencias.univ.es/guias/{code}.pdf")

    def test_insufficient_pairs_returns_none(self):
        single_pair = [("101", "https://portal.univ.es/guias/101.pdf")]
        self.assertIsNone(learn_guide_url_template(single_pair))
        self.assertIsNone(learn_guide_url_template([]))

    def test_project_missing_guide_urls(self):
        template = "https://portal.univ.es/guias/{code}.pdf"
        subjects = [
            {
                "codigo_asignatura": "101",
                "nombre_elemento": "Cálculo I",
                "url_guia_docente": "https://custom.univ.es/manual_101.pdf",
            },
            {
                "codigo_asignatura": "102",
                "nombre_elemento": "Física I",
                "url_guia_docente": "",
            },
            {
                "codigo_asignatura": "",
                "nombre_elemento": "Optativa General",
                "url_guia_docente": "",
            },
        ]

        enriched = project_missing_guide_urls(template, subjects)
        self.assertEqual(len(enriched), 3)

        # 101 already had an existing guide url; should remain untouched
        self.assertEqual(enriched[0]["url_guia_docente"], "https://custom.univ.es/manual_101.pdf")
        self.assertFalse(enriched[0].get("_guia_proyectada", False))

        # 102 was missing; should be projected
        self.assertEqual(enriched[1]["url_guia_docente"], "https://portal.univ.es/guias/102.pdf")
        self.assertTrue(enriched[1].get("_guia_proyectada", False))

        # 103 had no code; should remain empty
        self.assertEqual(enriched[2]["url_guia_docente"], "")
        self.assertFalse(enriched[2].get("_guia_proyectada", False))


if __name__ == "__main__":
    unittest.main()
