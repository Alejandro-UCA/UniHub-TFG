import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from core import robots_policy
from core.downloader import is_same_or_subdomain


class _MockResponse:
    def __init__(self, status_code=200, text="", headers=None, content=b""):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = content if content else text.encode("utf-8")

    def close(self):
        pass


class TestRobotsPolicyRedirects(unittest.TestCase):
    def setUp(self):
        robots_policy.RobotsPolicy.clear_cache()
        self._orig_delay = robots_policy.REQUEST_DELAY
        robots_policy.REQUEST_DELAY = 0
        self.policy = robots_policy.RobotsPolicy(timeout=0.05)

    def tearDown(self):
        robots_policy.REQUEST_DELAY = self._orig_delay

    def test_safe_redirect_institutional_tlds(self):
        """Verifica que cambios legítimos de TLD autonómico/educativo sean permitidos."""
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.uab.cat/robots.txt", "https://www.uab.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.udc.gal/robots.txt", "https://www.udc.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.ehu.eus/robots.txt", "https://www.ehu.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.upc.edu/robots.txt", "https://www.upc.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.uvigo.gal/robots.txt", "https://www.uvigo.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.uax.com/robots.txt", "https://www.uax.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://universidadeuropea.com/robots.txt", "https://madrid.universidadeuropea.es"))

    def test_safe_redirect_subdomains(self):
        """Verifica que transiciones entre subdominios y dominio raíz sean permitidas."""
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://web.unican.es/robots.txt", "https://www.unican.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://usal.es/robots.txt", "https://www.usal.es"))
        self.assertTrue(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://www.udit.es/robots.txt", "https://udit.es"))

    def test_unrelated_domain_rejected(self):
        """Verifica que redirecciones a dominios de terceros o IPs sean rechazadas."""
        self.assertFalse(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://evil.com/robots.txt", "https://www.uab.es"))
        self.assertFalse(robots_policy.RobotsPolicy._is_safe_robots_redirect("http://127.0.0.1/robots.txt", "https://example.edu"))
        self.assertFalse(robots_policy.RobotsPolicy._is_safe_robots_redirect("http://192.168.1.1/robots.txt", "https://example.edu"))
        self.assertFalse(robots_policy.RobotsPolicy._is_safe_robots_redirect("https://malicious.org/robots.txt", "https://www.ucm.es"))

    def test_waf_403_tolerated_with_courtesy_delay(self):
        """Verifica que un HTTP 403 (WAF) en robots.txt se tolere con retardo de cortesía."""
        mock_403 = _MockResponse(status_code=403, text="Forbidden by Cloudflare WAF")
        with patch.object(robots_policy.requests, "get", return_value=mock_403):
            allowed, delay = self.policy.check("https://www.uclm.es/estudios")
        self.assertTrue(allowed)
        self.assertEqual(delay, 1.0)
        self.assertIn("robots_waf_403_tolerado", self.policy.explain("https://www.uclm.es/estudios"))

    def test_http_401_still_blocks_access(self):
        """Verifica que un HTTP 401 (Autenticación requerida) sí bloquee el rastreo."""
        mock_401 = _MockResponse(status_code=401, text="Unauthorized")
        with patch.object(robots_policy.requests, "get", return_value=mock_401):
            allowed, _ = self.policy.check("https://private.univ.es/secret")
        self.assertFalse(allowed)
        self.assertIn("robots_acceso_restringido_http_401", self.policy.explain("https://private.univ.es/secret"))

    def test_ssl_error_falls_back_to_http(self):
        """Verifica que un fallo de certificado SSL en HTTPS intente el fallback a HTTP."""
        ssl_err = requests.exceptions.SSLError("certificate verify failed")
        mock_http_ok = _MockResponse(status_code=200, text="User-agent: *\nAllow: /")
        
        def fake_get(url, **kwargs):
            if url.startswith("https://"):
                raise ssl_err
            return mock_http_ok

        with patch.object(robots_policy.requests, "get", side_effect=fake_get):
            allowed, _ = self.policy.check("https://www.ub.es/estudis")
        self.assertTrue(allowed)

    def test_is_same_or_subdomain_subdomains(self):
        """Verifica que downloader.is_same_or_subdomain reconozca subdominios hermanos legítimos."""
        self.assertTrue(is_same_or_subdomain("https://web.unican.es/estudios", "https://www.unican.es"))
        self.assertTrue(is_same_or_subdomain("https://quimicas.uab.cat/grados", "https://www.uab.cat"))
        self.assertTrue(is_same_or_subdomain("https://grados.udc.gal/es/estudos", "https://udc.gal"))
        self.assertFalse(is_same_or_subdomain("https://www.evil.com/fake", "https://www.uab.cat"))


if __name__ == "__main__":
    unittest.main()
