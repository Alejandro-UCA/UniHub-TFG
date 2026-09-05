import os
import sys
import unittest
from unittest.mock import patch

import requests


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
import robots_policy


class _Response:
    status_code = 302
    headers = {"Location": "http://127.0.0.1/internal"}
    content = b""
    text = ""

    def close(self):
        pass


class TestRobotsPolicySecurity(unittest.TestCase):
    def setUp(self):
        robots_policy.RobotsPolicy.clear_cache()
        self._request_delay = robots_policy.REQUEST_DELAY
        robots_policy.REQUEST_DELAY = 0
        self.policy = robots_policy.RobotsPolicy(timeout=0.01)

    def tearDown(self):
        robots_policy.REQUEST_DELAY = self._request_delay

    def test_http_network_failure_is_fail_closed_without_name_error(self):
        with patch.object(robots_policy.requests, "get", side_effect=requests.RequestException("network down")):
            allowed, _ = self.policy.check("http://example.edu/path")
        self.assertFalse(allowed)
        self.assertIn("error_red_", self.policy.explain("http://example.edu/path"))

    def test_redirect_outside_robots_host_is_rejected(self):
        with patch.object(robots_policy.requests, "get", return_value=_Response()) as get:
            allowed, _ = self.policy.check("https://example.edu/path")
        self.assertFalse(allowed)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(self.policy.explain("https://example.edu/path"), "robots_redireccion_fuera_del_origen")

    def test_http_to_https_fallback_keeps_same_origin_redirect_policy(self):
        network_down = requests.RequestException("HTTP unavailable")
        with patch.object(
            robots_policy.requests,
            "get",
            side_effect=[network_down, network_down, network_down, _Response()],
        ) as get:
            allowed, _ = self.policy.check("http://example.edu/path")
        self.assertFalse(allowed)
        self.assertEqual(get.call_count, 4)
        self.assertEqual(self.policy.explain("http://example.edu/path"), "robots_redireccion_fuera_del_origen")

    def test_negative_robots_result_is_temporarily_reused(self):
        with patch.object(robots_policy.requests, "get", side_effect=requests.RequestException("network down")) as get:
            self.assertFalse(self.policy.check("https://example.edu/path")[0])
            self.assertFalse(self.policy.check("https://example.edu/other")[0])
        self.assertEqual(get.call_count, 3)
        self.assertTrue(self.policy.explain("https://example.edu/path").startswith("cacheado_negativo:"))


if __name__ == "__main__":
    unittest.main()
