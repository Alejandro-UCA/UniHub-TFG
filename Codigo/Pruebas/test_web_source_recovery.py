import unittest

from extractors.web_source_recovery import (
    classify_source_failure,
    currentness_score,
    is_explicitly_historical,
    is_trusted_institutional_redirect,
)


class TestWebSourceRecovery(unittest.TestCase):
    def test_accepts_same_brand_cross_tld_redirect(self):
        self.assertTrue(is_trusted_institutional_redirect(
            "https://www.uab.es",
            "https://www.uab.cat",
            "Universitat Autònoma de Barcelona",
        ))

    def test_accepts_brand_migration_with_city_subdomain(self):
        self.assertTrue(is_trusted_institutional_redirect(
            "https://madrid.universidadeuropea.es",
            "https://universidadeuropea.com",
            "Universidad Europea de Madrid",
        ))

    def test_rejects_unrelated_redirect(self):
        self.assertFalse(is_trusted_institutional_redirect(
            "https://www.uab.es",
            "https://uab.evil.example",
            "Universitat Autònoma de Barcelona",
        ))

    def test_current_page_outranks_explicit_historical_page(self):
        current = currentness_score(
            "https://www.ucm.es/estudios/grado-antropologiasocialycultural-plan",
            "Curso 2026/2027 Grado en Antropología Social y Cultural",
        )
        historical = currentness_score(
            "https://www.ucm.es/estudios/grado-antropologiasocialyculturalext-plan",
            "Plan en extinción",
        )
        self.assertGreater(current, historical)
        self.assertTrue(is_explicitly_historical("https://example.es/plan-ext-plan"))

    def test_classifies_failure_for_next_action(self):
        self.assertEqual(classify_source_failure("redirect externo no permitido"), "redireccion_institucional")
        self.assertEqual(classify_source_failure("SSL hostname mismatch"), "tls_o_protocolo")
        self.assertEqual(classify_source_failure(status_code=404), "url_obsoleta_o_404")


if __name__ == "__main__":
    unittest.main()
