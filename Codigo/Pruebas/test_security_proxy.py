import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from API import security


class TestSecurityProxy(unittest.TestCase):
    def _request(self, headers=None, client_host="172.20.0.5"):
        return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=client_host))

    def test_proxy_ip_is_only_used_when_explicitly_enabled(self):
        request = self._request({"X-Real-IP": "203.0.113.8"})
        with patch.object(security.settings, "TRUST_PROXY_HEADERS", False):
            self.assertEqual(security._client_identifier(request), "172.20.0.5")
        with patch.object(security.settings, "TRUST_PROXY_HEADERS", True), \
             patch.object(security.settings, "TRUSTED_PROXY_NETWORKS", "172.16.0.0/12"):
            self.assertEqual(security._client_identifier(request), "203.0.113.8")

    def test_header_is_ignored_when_sender_is_not_a_trusted_proxy(self):
        request = self._request({"X-Real-IP": "203.0.113.8"}, client_host="198.51.100.10")
        with patch.object(security.settings, "TRUST_PROXY_HEADERS", True), \
             patch.object(security.settings, "TRUSTED_PROXY_NETWORKS", "172.16.0.0/12"):
            self.assertEqual(security._client_identifier(request), "198.51.100.10")


if __name__ == "__main__":
    unittest.main()
