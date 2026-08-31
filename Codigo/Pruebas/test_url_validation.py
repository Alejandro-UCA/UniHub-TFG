import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from downloader import RUCTDownloader, is_valid_http_url, normalize_url
from fase1_parte4_asignaturas import resolve_candidate_subject_guide_urls


class URLValidationTests(unittest.TestCase):
    def test_rejects_plain_text_and_malformed_hosts(self):
        for value in (
            "erasmus mundus en medio ambiente y recursos marinos",
            "https://bad host.example/guide",
            "https://example.com:99999/guide",
            "https://.example.com/guide",
        ):
            self.assertFalse(is_valid_http_url(value), value)

    def test_accepts_unicode_path_and_idna_host(self):
        self.assertTrue(is_valid_http_url("https://xn--universidad-9za.es/guía/álgebra"))

    def test_normalize_url_does_not_invent_a_base_for_relative_paths(self):
        self.assertEqual(normalize_url("/relative/guide.pdf"), "")

    def test_normalize_url_rejects_malformed_or_special_schemes(self):
        for value in ("http:///bad", "javascript:alert(1)", "mailto:test@example.org"):
            self.assertEqual(normalize_url(value), "", value)

    def test_request_rejects_invalid_url_before_network(self):
        downloader = RUCTDownloader(enable_http2=False)
        try:
            with self.assertRaises(Exception) as context:
                downloader._request_with_retry("erasmus mundus en medio ambiente y recursos marinos")
            self.assertIn("URL HTTP(S) no válida", str(context.exception))
        finally:
            downloader.close()

    def test_candidate_generation_discards_invalid_explicit_url(self):
        urls = resolve_candidate_subject_guide_urls(
            {
                "url_guia_docente": "erasmus mundus en medio ambiente y recursos marinos",
                "codigo_asignatura": "123456",
                "nombre_elemento": "Medio Ambiente",
            },
            u_code="999",
            u_web="https://new-university.example",
        )
        self.assertTrue(urls)
        self.assertNotIn("erasmus mundus en medio ambiente y recursos marinos", urls)
        self.assertTrue(all(is_valid_http_url(url) for url in urls))


if __name__ == "__main__":
    unittest.main()
