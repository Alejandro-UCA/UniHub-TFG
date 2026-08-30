import json
import os
import sys
import tempfile
import unittest


CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if CRAWLER_DIR not in sys.path:
    sys.path.insert(0, CRAWLER_DIR)

from plan_quality_audit import audit_plan_records
from fase1_parte4_asignaturas import (
    resolve_candidate_subject_guide_urls,
    is_plausible_subject_code,
    _enrich_structured_learning_guide_from_lines,
    _looks_like_structured_learning_guide,
    _enrich_signed_learning_guide_from_lines,
    _looks_like_signed_learning_guide,
    _subject_guide_identity_matches,
)
from subject_guide_discovery import (
    build_subject_guide_discovery_index,
    extract_academic_link_records,
    parse_sitemap_locations,
    rank_discovered_guide_urls,
)
from subject_guide_quality import assess_subject_guide_quality
from univ_web_crawler import extract_html_subjects, is_valid_curricular_table
from config import ORGANIC_EXTERNAL_DOMAIN_DENYLIST
from bs4 import BeautifulSoup


class TestUcaCoverageAndProfiles(unittest.TestCase):
    def test_subject_guide_quality_reports_present_and_missing_fields(self):
        complete = assess_subject_guide_quality({
            "nombre_asignatura": "Álgebra", "codigo_asignatura": "1234",
            "creditos": {"total_ects": 6}, "temario": ["Tema 1"],
            "sistema_evaluacion": ["Examen"], "competencias": ["CG1"],
            "resultados_aprendizaje": ["RA1"], "profesorado": ["Docente"],
            "departamento": "Matemáticas",
        }, expected_name="Álgebra", expected_code="1234", source_url="https://uni.es/guia")
        self.assertEqual(complete["puntuacion"], 100.0)
        self.assertEqual(complete["nivel"], "alta")
        self.assertEqual(complete["campos_faltantes"], [])

        sparse = assess_subject_guide_quality({"nombre_asignatura": "Álgebra", "temario": ["Tema 1"]})
        self.assertLess(sparse["puntuacion"], 55.0)
        self.assertIn("codigo_asignatura", sparse["campos_faltantes"])
    def test_sitemap_parser_handles_namespaces_and_relative_locations(self):
        raw = b'''<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>/grados/ficha-algebra.html</loc></url>
          <url><loc>https://otra.example/externa.pdf</loc></url>
        </urlset>'''
        parsed = parse_sitemap_locations(raw, "https://nueva-universidad.es/sitemap.xml")
        self.assertEqual(parsed["kind"], "urlset")
        self.assertIn("https://nueva-universidad.es/grados/ficha-algebra.html", parsed["locations"])
        self.assertIn("https://otra.example/externa.pdf", parsed["locations"])

    def test_sitemap_parser_exposes_lastmod_evidence(self):
        raw = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://uni.es/guias/algebra.pdf</loc><lastmod>2026-08-01</lastmod></url>
        </urlset>'''
        parsed = parse_sitemap_locations(raw, "https://uni.es/sitemap.xml")
        self.assertEqual(parsed["records"][0]["lastmod"], "2026-08-01")

    def test_discovered_urls_are_ranked_by_code_and_subject_name(self):
        ranked = rank_discovered_guide_urls(
            [
                "https://uni.es/grados/otra-asignatura-999999.pdf",
                "https://uni.es/guias/algebra-lineal-123456.pdf",
                "https://uni.es/noticias/algebra-lineal",
            ],
            subject_name="Álgebra Lineal",
            subject_code="123456",
        )
        self.assertEqual(ranked[0], "https://uni.es/guias/algebra-lineal-123456.pdf")

    def test_discovery_evidence_keeps_context_and_rejects_generic_news(self):
        html = b"""
        <html><head><title>Oferta academica</title></head><body>
          <h2>Noticias</h2>
          <a href='/noticias/algebra-lineal-y-nuevas-investigaciones'>Algebra Lineal</a>
          <h2>Guias docentes</h2>
          <a href='/guias/algebra-lineal-123456.pdf'>Guia docente de Algebra Lineal</a>
        </body></html>
        """
        records = extract_academic_link_records(
            html, "https://uni.es/estudios", ["uni.es"], limit=10
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["url"], "https://uni.es/guias/algebra-lineal-123456.pdf")
        self.assertIn("guia docente", records[0]["anchor_text"].lower())
        self.assertIn("guias", records[0]["strong_guide_markers"])

    def test_ranker_uses_anchor_context_for_discovered_records(self):
        ranked = rank_discovered_guide_urls(
            [
                {
                    "url": "https://uni.es/academia/documento-123456",
                    "anchor_text": "Guía docente de Álgebra Lineal",
                    "title": "Oferta académica",
                },
                {
                    "url": "https://uni.es/noticias/algebra-lineal",
                    "anchor_text": "Álgebra Lineal",
                },
            ],
            subject_name="Álgebra Lineal",
            subject_code="123456",
        )
        self.assertEqual(ranked, ["https://uni.es/academia/documento-123456"])

    def test_name_only_discovery_rejects_general_pages_without_guide_path(self):
        ranked = rank_discovered_guide_urls(
            [
                "https://uni.es/noticias/salud-publica-y-nuevas-investigaciones",
                "https://uni.es/estudios/salud-publica",
                "https://uni.es/guias/salud-publica.pdf",
            ],
            subject_name="Salud Pública",
        )

        self.assertEqual(ranked, ["https://uni.es/guias/salud-publica.pdf"])

    def test_discovery_index_reads_robots_declared_sitemap_with_limits(self):
        class _Robots:
            def check(self, url):
                return True, None

        class _Downloader:
            robots_policy = _Robots()

            def __init__(self):
                self.calls = []

            def fetch_content(self, url, max_size_bytes=None):
                self.calls.append(url)
                if url.endswith("/robots.txt"):
                    return b"User-agent: *\nSitemap: https://uni.es/custom-index.xml\n"
                if url.endswith("custom-index.xml"):
                    return b'''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                      <sitemap><loc>https://uni.es/subjects.xml</loc></sitemap>
                    </sitemapindex>'''
                if url.endswith("subjects.xml"):
                    return b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                      <url><loc>https://uni.es/guias/algebra-123456.pdf</loc></url>
                      <url><loc>https://external.example/guias/algebra-123456.pdf</loc></url>
                    </urlset>'''
                raise AssertionError(url)

        downloader = _Downloader()
        result = build_subject_guide_discovery_index(
            downloader, "https://uni.es", max_roots=1, max_files=4, max_urls=10
        )
        self.assertIn("https://uni.es/guias/algebra-123456.pdf", result["urls"])
        self.assertNotIn("https://external.example/guias/algebra-123456.pdf", result["urls"])
        self.assertLessEqual(result["files_read"], 4)
    def test_explicit_guide_urls_are_preserved_for_any_official_domain(self):
        expected = "https://portal.example/guias/21714009.pdf"
        urls = resolve_candidate_subject_guide_urls(
            {"codigo_asignatura": "21714009", "nombre_elemento": "Biología", "url_guia_docente": expected},
            u_code="999",
            u_web="https://portal.example",
            d_code="PLAN-1",
            academic_year="2025-2026",
        )
        self.assertEqual(urls[0], expected)

    def test_plan_audit_detects_sparse_and_missing_catalog_records(self):
        with tempfile.TemporaryDirectory() as directory:
            plans = os.path.join(directory, "planes")
            os.makedirs(os.path.join(plans, "005"))
            catalog_path = os.path.join(directory, "catalog.json")
            with open(catalog_path, "w", encoding="utf-8") as handle:
                json.dump({"005": {"titulaciones_vigentes": [
                    {"codigo_estudio": "2500001", "titulo": "Grado en Prueba", "nivel_academico": "Grado"},
                    {"codigo_estudio": "2500002", "titulo": "Grado Ausente", "nivel_academico": "Grado"},
                ]}}, handle)
            with open(os.path.join(plans, "005", "2500001.json"), "w", encoding="utf-8") as handle:
                json.dump({"codigo_estudio": "2500001", "titulo": "Grado en Prueba"}, handle)
            with open(os.path.join(plans, "005", "2500003.json"), "w", encoding="utf-8") as handle:
                json.dump({
                    "codigo_estudio": "2500003",
                    "titulo": "Grado Completo",
                    "nivel_academico": "Grado",
                    "universidad_codigo": "005",
                    "universidad_nombre": "Universidad de Cádiz",
                    "estado_fuente": "verificada",
                    "plan_estudios": {"elementos_curriculares": [{"nombre_elemento": "Álgebra"}]},
                }, handle)

            result = audit_plan_records(plans, catalog_path, ("005",))

        self.assertEqual(result["files_seen"], 2)
        self.assertEqual(result["sparse_records"], 1)
        self.assertEqual(result["expected_missing_records"], 1)
        self.assertEqual(result["accepted_plan_records"], 1)

    def test_external_non_curricular_domains_are_quarantined(self):
        self.assertIn("erasmusplay.com", ORGANIC_EXTERNAL_DOMAIN_DENYLIST)
        self.assertIn("sepie.es", ORGANIC_EXTERNAL_DOMAIN_DENYLIST)
        self.assertNotIn("sea-eu.org", ORGANIC_EXTERNAL_DOMAIN_DENYLIST)

    def test_administrative_summary_is_not_a_curricular_table(self):
        html = """
        <table>
          <tr><td>Créditos</td><td>240 créditos europeos</td></tr>
          <tr><td>Objetivos</td><td>Formar profesionales con capacidad técnica</td></tr>
          <tr><td>Centro</td><td>Escuela Técnica Superior</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertFalse(is_valid_curricular_table(soup.find("table")))
        self.assertEqual(extract_html_subjects(soup), [])

    def test_url_lines_are_not_card_subjects(self):
        soup = BeautifulSoup("<html><body>https://portal.example</body></html>", "html.parser")
        self.assertEqual(extract_html_subjects(soup), [])

    def test_invalid_administrative_codes_do_not_generate_guide_urls(self):
        self.assertFalse(is_plausible_subject_code("OTRI"))
        self.assertFalse(is_plausible_subject_code("HRS4R"))
        urls = resolve_candidate_subject_guide_urls(
            {"codigo_asignatura": "OTRI", "nombre_elemento": "Transferencia de Resultados"},
            u_code="999", u_web="https://portal.example", d_code="PLAN-1",
        )
        self.assertTrue(urls)
        self.assertTrue(all("OTRI" not in url for url in urls))
        self.assertLessEqual(len(urls), 6)

    def test_guide_url_generation_has_a_hard_per_subject_limit(self):
        urls = resolve_candidate_subject_guide_urls(
            {"codigo_asignatura": "55000042", "nombre_elemento": "Francés I"},
            u_code="999", u_web="https://portal.example", d_code="PLAN-1",
        )
        self.assertLessEqual(len(urls), 12)

    def test_unknown_university_uses_only_its_current_official_domain(self):
        urls = resolve_candidate_subject_guide_urls(
            {"codigo_asignatura": "123456", "nombre_elemento": "Álgebra"},
            u_code="999",
            u_web="https://new-university.example",
        )
        self.assertTrue(urls)
        self.assertTrue(all("new-university.example" in url for url in urls))

    def test_name_only_subjects_receive_bounded_slug_candidates(self):
        urls = resolve_candidate_subject_guide_urls(
            {"nombre_elemento": "Introducción a la Salud Pública"},
            u_code="999",
            u_web="https://new-university.example",
        )
        self.assertGreater(len(urls), 0)
        self.assertLessEqual(len(urls), 6)
        self.assertTrue(any("introduccion-a-la-salud-publica" in url.lower() for url in urls))

    def test_name_only_subjects_use_the_official_domain(self):
        urls = resolve_candidate_subject_guide_urls(
            {"nombre_elemento": "Salud Pública"},
            u_code="999",
            u_web="https://new-university.example",
        )

        self.assertTrue(urls)
        self.assertTrue(all("new-university.example" in url for url in urls))

    def test_explicit_full_year_guide_url_is_kept_in_current_course(self):
        url = "https://new-university.example/sites/default/public/guias/2025-2026/2411138.pdf"
        urls = resolve_candidate_subject_guide_urls(
            {
                "codigo_asignatura": "2411138",
                "nombre_elemento": "Fisioterapia Comunitaria",
                "url_guia_docente": url,
            },
            u_code="999",
        )
        self.assertEqual(urls[0], url)

    def test_subject_guide_identity_gate_rejects_cross_subject_content(self):
        self.assertTrue(_subject_guide_identity_matches(
            "Fisioterapia Comunitaria", "2411138",
            {"nombre_asignatura": "Fisioterapia Comunitaria", "codigo_asignatura": "2411138"},
        ))
        self.assertFalse(_subject_guide_identity_matches(
            "Fisioterapia Comunitaria", "2411138",
            {"nombre_asignatura": "Física Aplicada", "codigo_asignatura": "9999999"},
        ))
        self.assertFalse(_subject_guide_identity_matches(
            "Fisioterapia Comunitaria", "",
            {"nombre_asignatura": "", "codigo_asignatura": ""},
            "https://ugr.es/guia-generica",
        ))

    def test_structured_learning_guide_pdf_extracts_semantics_from_text_layout(self):
        lines = [
            "GUÍA DE APRENDIZAJE",
            "1. Datos descriptivos",
            "1.1. Datos de la asignatura",
            "Nombre de la asignatura 85003111 - Álgebra Lineal y Geometría",
            "No de créditos 6 ECTS",
            "Carácter Básica",
            "Idioma de impartición Castellano",
            "4. Descripción de la asignatura y temario",
            "4.1. Descripción de la asignatura",
            "El temario está estructurado en bloques.",
            "1. Introducción",
            "2. Matrices y vectores",
            "4.2. Temario de la asignatura",
            "1. Introducción",
            "2. Matrices y vectores",
            "5. Cronograma",
            "RA33 - Calcular autovalores y autovectores",
            "CB1 - Comprender los fundamentos de la materia",
            "6. Actividades y criterios de evaluación",
            "6.1.1. Evaluación progresiva",
            "8 Primer Control",
            "Presencial 02:00 40% 3 / 10",
            "7. Recursos didácticos",
        ]
        self.assertTrue(_looks_like_structured_learning_guide(lines))
        result = {"temario": [], "competencias": [], "resultados_aprendizaje": [], "sistema_evaluacion": [], "creditos": {}}
        _enrich_structured_learning_guide_from_lines(result, lines)
        self.assertEqual(result["codigo_asignatura"], "85003111")
        self.assertEqual(result["creditos"]["total_ects"], 6.0)
        self.assertEqual(len(result["temario"]), 2)
        self.assertEqual(len(result["resultados_aprendizaje"]), 1)
        self.assertEqual(result["sistema_evaluacion"][0]["ponderacion_porcentaje"], 40.0)

    def test_signed_learning_guide_pdf_extracts_structured_sections(self):
        lines = [
            "Guías Docentes", "Curso:", "2025 / 2026", "Guía docente de la asignatura",
            "Fisioterapia Comunitaria, Salud", "Pública y Gestión en Fisioterapia", "(2411138)",
            "Departamento de Fisioterapia:", "Curso 3º Semestre 2º Créditos 6 Tipo Obligatoria",
            "COMPETENCIAS ASOCIADAS A MATERIA/ASIGNATURA", "COMPETENCIAS GENERALES",
            "CG04 - Adquirir la experiencia clínica adecuada que proporcione habilidades",
            "intelectuales y destrezas técnicas.", "CE19 - Conocer el sistema sanitario.",
            "RESULTADOS DE APRENDIZAJE (Objetivos)", "El estudiantado será capaz de:",
            "Explicar los conceptos fundamentales de salud pública.",
            "PROGRAMA DE CONTENIDOS TEÓRICOS Y PRÁCTICOS", "TEÓRICO",
            "Tema 1. Conceptos fundamentales sobre salud pública.",
            "Tema 2. Historia natural de la enfermedad.", "EVALUACIÓN (instrumentos de evaluación)",
            "1.1. Evaluación de la teoría (70% de la calificación final)",
            "INFORMACIÓN ADICIONAL",
        ]
        self.assertTrue(_looks_like_signed_learning_guide(lines))
        result = {
            "codigo_asignatura": "", "nombre_asignatura": "", "departamento": "",
            "creditos": {"total_ects": None}, "temario": [], "competencias": [],
            "resultados_aprendizaje": [], "sistema_evaluacion": [], "criterios_evaluacion": "",
        }
        _enrich_signed_learning_guide_from_lines(result, lines)
        self.assertEqual(result["codigo_asignatura"], "2411138")
        self.assertIn("Fisioterapia Comunitaria", result["nombre_asignatura"])
        self.assertEqual(result["creditos"]["total_ects"], 6.0)
        self.assertEqual(len(result["competencias"]), 2)
        self.assertEqual(len(result["resultados_aprendizaje"]), 1)
        self.assertEqual(len(result["temario"]), 2)
        self.assertEqual(result["sistema_evaluacion"][0]["ponderacion_porcentaje"], 70.0)


if __name__ == "__main__":
    unittest.main()
