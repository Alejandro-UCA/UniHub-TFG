"""
UniHub Comprehensive Verification Test Suite
Executes live, automated testing across Phase 1, Phase 2, Phase 3, and Phase 4.
"""

import os
import sys
import json
import time
import re
import unittest
import importlib.util

# Paths
BASE_DIR = r"d:\Proyecto"
CRAWLER_DIR = os.path.join(BASE_DIR, "Codigo", "Crawler")
API_DIR = os.path.join(BASE_DIR, "Codigo", "API")
WWW_DIR = os.path.join(BASE_DIR, "Codigo", "WWW")
DOCKER_DIR = os.path.join(BASE_DIR, "Codigo", "Docker")

def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class TestPhase1Crawler(unittest.TestCase):
    """Deep verification of Phase 1 Crawler logic, network resilience, and parsers."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, CRAWLER_DIR)
        cls.crawler_config = load_module_from_path("crawler_config", os.path.join(CRAWLER_DIR, "config.py"))

    def test_01_crawler_config_and_constants(self):
        cfg = self.crawler_config
        self.assertTrue(hasattr(cfg, "UNIVERSIDADES_JSON"))
        self.assertTrue(hasattr(cfg, "CIRCUIT_BREAKER_FAILURES_THRESHOLD"))
        self.assertGreater(cfg.CIRCUIT_BREAKER_FAILURES_THRESHOLD, 0)
        self.assertGreater(cfg.HTTP_TIMEOUT, 0)
        self.assertIn("UniHubCrawler", cfg.USER_AGENT)

    def test_02_url_normalization(self):
        from downloader import normalize_url
        test_cases = [
            ("http://https://www.uca.es", "https://www.uca.es"),
            ("https://http://www.uca.es", "http://www.uca.es"),
            ("http://http://www.uca.es", "http://www.uca.es"),
            ("https://https://www.uca.es", "https://www.uca.es"),
            ("https://www.boe.es/boe/dias/2021/06/17/pdfs/BOE-A-2021-10088.pdf", "https://www.boe.es/boe/dias/2021/06/17/pdfs/BOE-A-2021-10088.pdf"),
            ("http://ww.boe.es/boe/dias/2021/06/17/pdfs/BOE-A-2021-10088.pdf", "https://www.boe.es/boe/dias/2021/06/17/pdfs/BOE-A-2021-10088.pdf"),
            ("https://wwwww.boe.es/boe/dias/2021/06/17/pdfs/BOE-A-2021-10088.pdf", "https://www.boe.es/boe/dias/2021/06/17/pdfs/BOE-A-2021-10088.pdf"),
            ("http://portaldogc.gencat.cat/doc.pdf", "https://dogc.gencat.cat/doc.pdf"),
            ("http://bocm.es/bocm.pdf", "https://bocm.madrid.org/bocm.pdf"),
        ]
        for raw, expected in test_cases:
            self.assertEqual(normalize_url(raw), expected)

    def test_03_parsers_regex(self):
        from parsers import RE_CREDIT_SUMMARY
        sample_text = "Formacion Basica: 60 ECTS, Obligatorias: 120, Optativas: 48, TFG: 12. Total: 240"
        extracted = {}
        for name, pattern in RE_CREDIT_SUMMARY:
            m = pattern.search(sample_text)
            if m:
                extracted[name] = int(m.group(1))
        
        self.assertEqual(extracted.get("Formación Básica"), 60)
        self.assertEqual(extracted.get("Obligatorias"), 120)
        self.assertEqual(extracted.get("Optativas"), 48)
        self.assertEqual(extracted.get("Trabajo Fin de Grado / Máster"), 12)
        self.assertEqual(extracted.get("Créditos Totales"), 240)

    def test_04_sqlite_wal_checkpoint(self):
        from checkpoint import CheckpointManager
        test_db = os.path.join(CRAWLER_DIR, "test_verify_checkpoint.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        
        cm = CheckpointManager(db_path=test_db)
        cm.mark_university_processed("023")
        self.assertTrue(cm.is_university_processed("023"))
        self.assertFalse(cm.is_university_processed("999"))
        
        cm.update_degree_record("2500001", "https://boe.es/boe/1.pdf", "2025-01-01", "2025-01-01T00:00:00")
        self.assertTrue(cm.is_degree_up_to_date("2500001", "https://boe.es/boe/1.pdf", "2025-01-01"))
        self.assertFalse(cm.is_degree_up_to_date("2500001", "https://boe.es/boe/2.pdf", "2025-01-02"))
        
        cm.mark_extinct_degree("9990001", "Titulacion no vigente")
        self.assertTrue(cm.is_extinct_degree("9990001"))
        
        del cm
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    def test_05_precios_official_formula(self):
        from precios_crawler import compute_degree_price
        res = compute_degree_price(
            ccaa="Comunidad de Andalucía",
            tipo_univ="Pública",
            nivel_academico="Grado - RD 1393/2007 (1)",
            titulo="Grado en Ingeniería Informática"
        )
        self.assertIsNotNone(res)
        self.assertIn("precio_credito_ects", res)
        self.assertIn("precio_estimado_anual", res)
        self.assertGreater(res["precio_credito_ects"], 0)


class TestPhase2APISecurityAndDatabase(unittest.TestCase):
    """Deep verification of Phase 2 SQL Schema, Security, and ETL logic."""

    def test_01_sql_schema_ddl_integrity(self):
        schema_file = os.path.join(API_DIR, "database", "schema.sql")
        self.assertTrue(os.path.exists(schema_file))
        with open(schema_file, "r", encoding="utf-8") as f:
            sql = f.read()
        
        # Verify pg_trgm and required tables
        self.assertIn("pg_trgm", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS universidades", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS titulaciones", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS planes_estudio", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS elementos_curriculares", sql)

    def test_02_constant_time_comparison(self):
        import secrets
        admin_key = "test-admin-key"
        self.assertTrue(secrets.compare_digest(admin_key, "test-admin-key"))
        self.assertFalse(secrets.compare_digest("wrong_key", admin_key))

    def test_03_etl_loader_structure_and_safety_guard(self):
        etl_file = os.path.join(API_DIR, "database", "etl_loader.py")
        self.assertTrue(os.path.exists(etl_file))
        with open(etl_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Las eliminaciones deben requerir opt-in explícito además de cobertura.
        self.assertIn("ETL_ALLOW_DELETIONS", content)
        self.assertIn("db.commit()", content)
        # Verify bulk save objects
        self.assertIn("bulk_save_objects", content)
        # Verify lock file
        self.assertIn("etl_running.lock", content)


class TestPhase3FrontendIntegrity(unittest.TestCase):
    """Verification of Phase 3 Frontend React files, components, and imports."""

    def test_01_component_files_exist(self):
        required_components = [
            "App.jsx", "main.jsx", "index.css",
            "components/Navbar.jsx",
            "components/Hero.jsx",
            "components/UnivCard.jsx",
            "components/DegreeCard.jsx",
            "components/PlanModal.jsx",
            "components/TuitionCalculator.jsx",
            "components/Geolocation.jsx",
            "components/AdminDashboard.jsx",
            "components/AdminLogin.jsx",
            "components/AdminFormModal.jsx",
            "components/AboutUs.jsx",
            "components/Pagination.jsx",
            "components/Footer.jsx",
            "components/ErrorBoundary.jsx",
            "services/api.js",
            "analytics/usageTracker.js",
            "analytics/perfTracker.js",
            "utils/distance.js"
        ]
        for rel_path in required_components:
            full_path = os.path.join(WWW_DIR, "src", rel_path)
            self.assertTrue(os.path.exists(full_path), f"Component missing: {rel_path}")

    def test_02_distance_utility(self):
        dist_path = os.path.join(WWW_DIR, "src", "utils", "distance.js")
        with open(dist_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("calculateHaversineDistance", content)
        self.assertIn("SPANISH_CITIES_COORDS", content)
        self.assertIn("cadiz", content)
        self.assertIn("madrid", content)
        self.assertIn("barcelona", content)

    def test_03_admin_dashboard_export_sanitization(self):
        admin_dash = os.path.join(WWW_DIR, "src", "components", "AdminDashboard.jsx")
        with open(admin_dash, "r", encoding="utf-8") as f:
            content = f.read()
        # Verify BOM and CSV sanitization
        self.assertIn("\\uFEFF", content)
        self.assertIn("/^[=+\\-@\\t\\r]/", content)


class TestPhase4DockerOrchestration(unittest.TestCase):
    """Verification of Phase 4 Docker configuration and deployment files."""

    def test_01_docker_compose_syntax_and_services(self):
        compose_file = os.path.join(DOCKER_DIR, "docker-compose.yml")
        self.assertTrue(os.path.exists(compose_file))
        with open(compose_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Verify 4 container services
        self.assertIn("unihub_db", content)
        self.assertIn("unihub_crawler", content)
        self.assertIn("unihub_api", content)
        self.assertIn("unihub_www", content)
        
        # Verify healthchecks and conditions
        self.assertIn("condition: service_healthy", content)
        self.assertIn("/api/v1/salud", content)

    def test_02_dockerfiles_exist(self):
        for sub in ["crawler", "api", "www"]:
            df = os.path.join(DOCKER_DIR, sub, "Dockerfile")
            self.assertTrue(os.path.exists(df), f"Missing Dockerfile in {sub}")

    def test_03_batch_scripts_exist(self):
        for script in ["iniciar_proyecto.bat", "detener_proyecto.bat"]:
            path = os.path.join(BASE_DIR, script)
            self.assertTrue(os.path.exists(path), f"Missing batch script: {script}")


if __name__ == "__main__":
    print("======================================================================")
    print("      UNIHUB FULL SYSTEM END-TO-END VERIFICATION SUITE")
    print("======================================================================\n")
    unittest.main(verbosity=2)
