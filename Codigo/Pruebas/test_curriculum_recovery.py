import unittest
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

from curriculum_recovery import (
    extract_prose_curriculum,
    extract_structured_curriculum,
    generic_curriculum_path_candidates,
    infer_declared_total_ects,
    discover_related_academic_origins,
    discover_linked_curriculum_documents,
    discover_linked_curriculum_pages,
)
from fase1_parte2_web_crawler import UniversityWebCrawler as Part2UniversityWebCrawler


class CurriculumRecoveryTests(unittest.TestCase):
    def test_admission_recognition_is_not_program_total(self):
        text = ('Estudiantes con estudios extranjeros totales que no hayan '
                'obtenido homologación a los que se les reconozca un mínimo '
                'de 30 créditos ECTS.')
        self.assertIsNone(infer_declared_total_ects(text))

    def test_total_does_not_cross_unrelated_dom_blocks(self):
        soup = BeautifulSoup('<p>Estudios totales</p><p>Reconocimiento mínimo '
                             'de 30 créditos ECTS</p>', 'html.parser')
        self.assertIsNone(infer_declared_total_ects(soup))

    def test_subtotal_is_not_program_total(self):
        self.assertIsNone(infer_declared_total_ects('Subtotal 60 ECTS'))

    def test_direct_total_with_grammatical_connectors(self):
        for text, total in [('A total of 240 ECTS credits', 240),
                            ('El total de los 60 ECTS en dos años', 60),
                            ('El total de ellos es de 90 créditos europeos ECTS', 90)]:
            with self.subTest(text=text):
                self.assertEqual(total, infer_declared_total_ects(text))

    def test_extracts_prose_subjects_and_declared_total(self):
        soup = BeautifulSoup(
            """
            <main>
              <p>El programa consta de 60 ECTS en dos semestres.</p>
              <p>Metodología de investigación (9 ECTS, OP).</p>
              <p>Prácticas externas — 15 ECTS.</p>
              <p>Trabajo Fin de Máster (6 ECTS).</p>
            </main>
            """,
            "html.parser",
        )
        elements = extract_prose_curriculum(soup, "https://example.edu/study")
        self.assertEqual(3, len(elements))
        self.assertEqual(60.0, infer_declared_total_ects(soup))
        self.assertEqual({"Metodología de investigación", "Prácticas externas", "Trabajo Fin de Máster"}, {e["nombre_elemento"] for e in elements})

    def test_extracts_declared_total_from_specialized_portal_prose(self):
        soup = BeautifulSoup(
            "<p>La dedicación del programa será de 60 ECTS distribuidos en dos semestres.</p>",
            "html.parser",
        )
        self.assertEqual(60.0, infer_declared_total_ects(soup))

    def test_extracts_program_total_above_single_subject_limit(self):
        soup = BeautifulSoup(
            "<p>Resumen por tipo de materia (total 240 ECTS).</p>",
            "html.parser",
        )
        self.assertEqual(240.0, infer_declared_total_ects(soup))

    def test_extracts_total_label_when_units_are_in_separate_table_column(self):
        soup = BeautifulSoup(
            "<p>Distribución del plan en créditos ECTS. Créditos totales 60.</p>",
            "html.parser",
        )
        self.assertEqual(60.0, infer_declared_total_ects(soup))

    def test_does_not_treat_an_optional_subtotal_as_program_total(self):
        soup = BeautifulSoup(
            "<p>Créditos optativos 60. Créditos obligatorios 20.</p>",
            "html.parser",
        )
        self.assertIsNone(infer_declared_total_ects(soup))

    def test_repairs_mojibake_before_extracting_declared_total(self):
        soup = BeautifulSoup(
            "<p>La dedicaciÃ³n del programa serÃ¡ de 60 ECTS.</p>",
            "html.parser",
        )
        self.assertEqual(60.0, infer_declared_total_ects(soup))

    def test_extracts_spanish_total_with_replacement_character(self):
        soup = BeautifulSoup(
            "<h3>Un total de 60 cr�ditos componen el plan de estudios del Grado.</h3>",
            "html.parser",
        )
        self.assertEqual(60.0, infer_declared_total_ects(soup))

    def test_extracts_jsonld_curriculum_without_institution_rules(self):
        soup = BeautifulSoup(
            '<script type="application/ld+json">{"hasCourse":[{"name":"Advanced Methods","credits":"6 ECTS"}]}</script>',
            "html.parser",
        )
        elements = extract_structured_curriculum(soup, "https://example.edu/study")
        self.assertEqual(1, len(elements))
        self.assertEqual("Advanced Methods", elements[0]["nombre_elemento"])

    def test_generates_only_same_origin_academic_routes(self):
        routes = generic_curriculum_path_candidates("https://example.edu/catalog/master", "Máster Universitario")
        self.assertTrue(routes)
        self.assertTrue(all(route.startswith("https://example.edu/") for route in routes))
        self.assertTrue(any("plan-de-estudios" in route for route in routes))

    def test_generates_title_slug_routes_without_institution_specific_rules(self):
        routes = generic_curriculum_path_candidates(
            "https://catalog.example.edu/",
            "Máster Universitario",
            "Máster Universitario en Sistemas Distribuidos por la Universidad Example",
        )
        self.assertIn("https://catalog.example.edu/master-sistemas-distribuidos", routes)
        self.assertIn(
            "https://catalog.example.edu/master-sistemas-distribuidos/plan-de-estudios",
            routes,
        )
        self.assertTrue(all("universidad-example" not in route for route in routes))

        corrupted_routes = generic_curriculum_path_candidates(
            "https://catalog.example.edu/",
            "M�ster - RD 822/2021",
            "M�ster Universitario en Anal�tica de Datos por la Universidad Example",
        )
        self.assertIn("https://catalog.example.edu/master-analitica-datos", corrupted_routes)

    def test_generates_level_specific_slug_routes_for_grades_and_doctorates(self):
        grade_routes = generic_curriculum_path_candidates(
            "https://catalog.example.edu/",
            "Grado - RD 822/2021",
            "Grado en Ciencias de Datos",
        )
        doctorate_routes = generic_curriculum_path_candidates(
            "https://catalog.example.edu/",
            "Doctor - RD 99/2011",
            "Doctorado en Ciencias de Datos",
        )
        self.assertIn(
            "https://catalog.example.edu/grados/grado-ciencias-datos",
            grade_routes,
        )
        self.assertIn(
            "https://catalog.example.edu/doctorado/doctorado-ciencias-datos",
            doctorate_routes,
        )
        self.assertTrue(all("example.edu" in route for route in grade_routes + doctorate_routes))

    def test_preserves_discovered_context_prefix_and_removes_gendered_degree_wrapper(self):
        routes = generic_curriculum_path_candidates(
            "https://catalog.example.edu/context/en",
            "Grado - RD 822/2021",
            "Graduado o Graduada en Biología por la Universidad Example",
        )
        self.assertIn("https://catalog.example.edu/context/en/biologia", routes)
        self.assertIn("https://catalog.example.edu/context/en/grado-biologia", routes)

    def test_discovers_only_same_organisation_curriculum_documents(self):
        soup = BeautifulSoup(
            """
            <a href="/files/plan-estudios.pdf">Plan de estudios</a>
            <a href="/files/informe-anual.pdf">Informe anual</a>
            <a href="https://other.example.net/plan-estudios.pdf">Plan externo</a>
            """,
            "html.parser",
        )
        documents = discover_linked_curriculum_documents(
            soup, "https://catalog.example.edu/programa"
        )
        self.assertEqual(
            [("https://catalog.example.edu/files/plan-estudios.pdf", "Plan de estudios")],
            documents,
        )

    def test_discovers_opaque_pdf_from_curriculum_section_context(self):
        soup = BeautifulSoup(
            """
            <main>
              <section>
                <h4>Plan de Estudios</h4>
                <a href="/media/doc/program-2026-final.pdf" aria-label="Descargar PDF">
                  <span>DESCARGAR PDF</span>
                </a>
              </section>
            </main>
            """,
            "html.parser",
        )
        documents = discover_linked_curriculum_documents(
            soup, "https://catalog.example.edu/degree"
        )
        self.assertEqual(
            [
                (
                    "https://catalog.example.edu/media/doc/program-2026-final.pdf",
                    "DESCARGAR PDF",
                )
            ],
            documents,
        )

    def test_discovers_pdf_when_section_has_multiple_sibling_links(self):
        soup = BeautifulSoup(
            """
            <section>
              <h4>Plan de Estudios</h4>
              <div>
                <a href="/media/opaque-plan.pdf">DESCARGAR PDF</a>
                <a href="/other/one">Oferta complementaria</a>
                <a href="/other/two">Reconocimiento de créditos</a>
                <a href="/other/three">Microtítulos</a>
              </div>
            </section>
            """,
            "html.parser",
        )
        documents = discover_linked_curriculum_documents(
            soup, "https://catalog.example.edu/degree"
        )
        self.assertEqual(
            [("https://catalog.example.edu/media/opaque-plan.pdf", "DESCARGAR PDF")],
            documents,
        )

    def test_discovers_linked_curriculum_pages_without_external_navigation(self):
        soup = BeautifulSoup(
            """
            <a href="/grado/datos/plan-de-estudios">Plan de estudios</a>
            <a href="/grado/datos/guia.pdf">Guía de asignaturas</a>
            <a href="/noticias/plan-estrategico">Plan estratégico</a>
            <a href="https://external.example.net/plan-de-estudios">Plan externo</a>
            """,
            "html.parser",
        )
        pages = discover_linked_curriculum_pages(
            soup, "https://catalog.example.edu/grado/datos"
        )
        self.assertEqual(
            [
                ("https://catalog.example.edu/grado/datos/plan-de-estudios", "Plan de estudios"),
                ("https://catalog.example.edu/grado/datos/guia.pdf", "Guía de asignaturas"),
            ],
            pages,
        )

    def test_follows_sitemap_index_without_leaving_authorised_origin(self):
        downloader = MagicMock()
        downloader.fetch_content.side_effect = lambda url: {
            "https://catalog.example.edu/robots.txt": b"Sitemap: https://catalog.example.edu/index.xml",
            "https://catalog.example.edu/index.xml": (
                b"<sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
                b"<sitemap><loc>https://catalog.example.edu/academic.xml</loc></sitemap>"
                b"</sitemapindex>"
            ),
            "https://catalog.example.edu/academic.xml": (
                b"<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
                b"<url><loc>https://catalog.example.edu/masteres/data-science</loc></url>"
                b"<url><loc>https://external.example.net/masteres/other</loc></url>"
                b"</urlset>"
            ),
        }.get(url, b"")
        crawler = Part2UniversityWebCrawler()
        crawler.check_robots_allowed = MagicMock(return_value=(True, None))
        with patch("fase1_parte2_web_crawler.RUCTDownloader", return_value=downloader):
            candidates = crawler._extract_recursive_sitemap_candidates(
                "https://catalog.example.edu/",
                [{"titulo": "Máster Universitario en Data Science"}],
            )
        self.assertIn("https://catalog.example.edu/masteres/data-science", candidates)
        self.assertNotIn("https://external.example.net/masteres/other", candidates)

    def test_rejects_credit_distribution_labels_as_subjects(self):
        soup = BeautifulSoup(
            """
            <table>
              <tr><th>Asignatura</th><th>ECTS</th></tr>
              <tr><td>Crèdits obligatoris</td><td>15</td></tr>
              <tr><td>Crèdits optatius</td><td>33</td></tr>
              <tr><td>Mètodes de recerca</td><td>6</td></tr>
            </table>
            """,
            "html.parser",
        )
        from fase1_parte2_web_crawler import extract_html_subjects

        elements = extract_html_subjects(soup, "https://example.edu/study")
        self.assertEqual(["Mètodes de recerca"], [e["nombre_elemento"] for e in elements])

    def test_rejects_fee_and_ficha_metadata_as_subjects(self):
        soup = BeautifulSoup(
            """
            <table>
              <tr><th>Asignatura</th><th>ECTS</th></tr>
              <tr><td>Cuota de reserva</td><td>1.6</td></tr>
              <tr><td>Precio total</td><td>8</td></tr>
              <tr><td>Centro Facultad de Humanidades Modalidad Presencial Créditos</td><td>60</td></tr>
              <tr><td>Metodología de investigación</td><td>6</td></tr>
            </table>
            """,
            "html.parser",
        )
        from fase1_parte2_web_crawler import extract_html_subjects

        elements = extract_html_subjects(soup, "https://example.edu/study")
        self.assertEqual(["Metodología de investigación"], [e["nombre_elemento"] for e in elements])

    def test_discovers_same_organisation_academic_subdomain_only(self):
        soup = BeautifulSoup(
            """
            <a href="https://web.example.edu/es/masteres">Másteres oficiales</a>
            <a href="https://external.example.net/masteres">Másteres externos</a>
            <link rel="canonical" href="https://catalog.example.edu/estudios">
            """,
            "html.parser",
        )
        origins = discover_related_academic_origins(soup, "https://www.example.edu/")
        self.assertEqual(
            {"https://example.edu", "https://web.example.edu", "https://catalog.example.edu"},
            set(origins),
        )

    def test_generates_compact_specialized_plan_routes(self):
        routes = generic_curriculum_path_candidates(
            "https://program.example.edu/", "Máster Universitario", "Máster en Datos"
        )
        self.assertTrue(any(url.endswith("/planestudios.html") for url in routes))
        self.assertTrue(any(url.endswith("/plan-d-estudis.html") for url in routes))

    def test_discovers_organisation_root_from_thematic_subdomain(self):
        soup = BeautifulSoup("<main>Información académica</main>", "html.parser")
        self.assertEqual(
            ["https://example.edu"],
            discover_related_academic_origins(
                soup, "https://program.example.edu/"
            ),
        )


if __name__ == "__main__":
    unittest.main()
