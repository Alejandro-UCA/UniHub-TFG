import importlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
sys.path.insert(0, CRAWLER_DIR)
from core import config
import healthcheck


class TestCrawlerKeyRotationAndHealth(unittest.TestCase):
    def test_first_rotated_key_is_used_when_legacy_variable_is_absent(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "", "ADMIN_API_KEYS": "new-key,old-key"}, clear=False):
            refreshed = importlib.reload(config)
            self.assertEqual(refreshed.ADMIN_API_KEY, "new-key")
            self.assertEqual(refreshed.ADMIN_API_KEYS, ("new-key", "old-key"))
        importlib.reload(config)

    def test_health_is_ready_before_first_scheduled_run_and_rejects_failed_run(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"CRAWLER_RUN_MANIFESTS_DIR": directory}, clear=False):
            self.assertEqual(healthcheck.main(), 0)
            with open(os.path.join(directory, "latest.json"), "w", encoding="utf-8") as handle:
                json.dump({"status": "failed"}, handle)
            self.assertEqual(healthcheck.main(), 1)


if __name__ == "__main__":
    unittest.main()
