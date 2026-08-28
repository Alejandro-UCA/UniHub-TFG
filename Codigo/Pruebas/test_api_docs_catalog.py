import os
import sys
import unittest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient
from API.main import app


class TestApiDocsCatalog(unittest.TestCase):
    def test_catalog_is_generated_from_registered_routes(self):
        response = TestClient(app).get("/api/v1/api_docs_info")
        self.assertEqual(response.status_code, 200)
        routes = {(item["metodo"], item["path"]) for item in response.json()["endpoints_disponibles"]}
        self.assertIn(("GET", "/api/v1/salud"), routes)
        self.assertIn(("POST", "/api/v1/admin/sync-etl"), routes)
        self.assertIn(("GET", "/api/v1/titulaciones/{codigo_estudio}/asignaturas"), routes)


if __name__ == "__main__":
    unittest.main()
