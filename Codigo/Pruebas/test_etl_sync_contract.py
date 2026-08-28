import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from API import main
from API.routes import estadisticas
from API.database.etl_loader import _has_authoritative_plan_snapshot


class TestEtlSyncContract(unittest.TestCase):
    def test_empty_or_missing_plan_snapshot_cannot_replace_existing_curriculum(self):
        self.assertFalse(_has_authoritative_plan_snapshot(None, "verificado_boe"))
        self.assertFalse(_has_authoritative_plan_snapshot({}, "verificado_boe"))
        self.assertFalse(_has_authoritative_plan_snapshot({"otro_metadato": "valor"}, "verificado_boe"))
        self.assertFalse(_has_authoritative_plan_snapshot({"elementos_curriculares": []}, "parcial"))
        self.assertFalse(_has_authoritative_plan_snapshot({"resumen_creditos": {}}, None))
        self.assertTrue(_has_authoritative_plan_snapshot({"elementos_curriculares": []}, "verificado_boe"))
        self.assertTrue(_has_authoritative_plan_snapshot({"resumen_creditos": {}}, "verificado_universidad"))

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
