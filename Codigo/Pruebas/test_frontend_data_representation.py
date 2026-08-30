import os
import unittest


WWW_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "WWW", "src"))


def read_source(*parts):
    with open(os.path.join(WWW_SRC, *parts), encoding="utf-8") as handle:
        return handle.read()


class TestFrontendDataRepresentation(unittest.TestCase):
    def test_plan_modal_consumes_credit_summary_list_and_verified_source(self):
        source = read_source("components", "PlanModal.jsx")
        self.assertIn("Array.isArray(curriculum.resumen_creditos)", source)
        self.assertIn("resumen.map((item, index)", source)
        self.assertIn("planData?.fuente_verificada_url", source)
        self.assertNotIn("numEcts * 60 + 45", source)

    def test_degree_cards_only_claim_verified_sources_and_do_not_add_fees(self):
        source = read_source("components", "DegreeCard.jsx")
        self.assertIn("degree.tiene_plan_verificado", source)
        self.assertIn("Datos incompletos", source)
        self.assertIn("estado_calidad_plan", source)
        self.assertIn("verifiedSourceLabel", source)
        self.assertNotIn("numEcts * 60 + 45", source)

    def test_plan_modal_shows_incomplete_data_with_quality_warning(self):
        source = read_source("components", "PlanModal.jsx")
        self.assertIn("Información incompleta", source)
        self.assertIn("motivos_calidad", source)
        self.assertIn("isIncompletePlan", source)
        self.assertNotIn("No mostramos asignaturas, ECTS", source)

    def test_calculator_never_derives_a_credit_rate_from_annual_price(self):
        source = read_source("components", "TuitionCalculator.jsx")
        self.assertNotIn("annualPrice / 60", source)
        self.assertIn("if (baseRate === null) calculationUnavailable = true", source)

    def test_app_reports_catalog_loading_errors_and_uses_neutral_catalog_label(self):
        app_source = read_source("App.jsx")
        hero_source = read_source("components", "Hero.jsx")
        self.assertIn("const [degreeError, setDegreeError]", app_source)
        self.assertIn("No se pudieron cargar las titulaciones", app_source)
        self.assertIn("incompleteDegreesOnPage", app_source)
        self.assertIn("incompletos o pendientes", app_source)
        self.assertIn("Titulaciones del catálogo", hero_source)
        self.assertNotIn("Titulaciones Vigentes", hero_source)

    def test_admin_error_links_are_limited_to_http_urls(self):
        source = read_source("components", "AdminDashboard.jsx")
        self.assertIn("const getSafeExternalUrl", source)
        self.assertIn("['http:', 'https:'].includes(url.protocol)", source)
        self.assertIn("href={getSafeExternalUrl(err.url)}", source)


if __name__ == "__main__":
    unittest.main()
