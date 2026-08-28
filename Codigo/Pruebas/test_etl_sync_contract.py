import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from API import main
from API.routes import estadisticas


class TestEtlSyncContract(unittest.TestCase):
    def test_admin_sync_only_returns_success_after_successful_etl(self):
        with patch.object(main, "run_etl", return_value=True):
            result = main.trigger_etl_sync(api_key="test")
        self.assertEqual(result["status"], "SUCCESS")

        with patch.object(main, "run_etl", return_value=False), self.assertRaises(HTTPException) as error:
            main.trigger_etl_sync(api_key="test")
        self.assertEqual(error.exception.status_code, 503)

    def test_legacy_sync_route_has_the_same_result_contract(self):
        with patch.object(estadisticas, "run_etl", return_value=False), self.assertRaises(HTTPException) as error:
            estadisticas.sync_etl_data(api_key="test")
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
