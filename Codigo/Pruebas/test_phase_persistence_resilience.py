import os
import sys
import tempfile
import unittest
from unittest.mock import patch


CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
sys.path.insert(0, CRAWLER_DIR)

import fase1_parte2_web_crawler as phase2
import fase1_parte3_precios as phase3
import fase1_parte4_asignaturas as phase4
from fase1_parte2_web_crawler import (
    are_degree_titles_compatible,
    is_authorized_external_academic_hub,
)
import spa_crawler
from fase1_parte4_asignaturas import SubjectGuideCache


class TestPhasePersistenceResilience(unittest.TestCase):
    def test_incompatible_degree_titles_cannot_share_a_curriculum_source(self):
        self.assertFalse(
            are_degree_titles_compatible(
                "Máster Universitario en Ingeniería Web por la Universidad de Oviedo",
                "Máster Universitario en Ingeniería Mecatrónica por la Universidad de Oviedo",
                "Universidad de Oviedo",
            )
        )

    def test_external_hubs_need_explicit_academic_relationship(self):
        self.assertTrue(
            is_authorized_external_academic_hub(
                "https://partner.example.edu/programas",
                "Centro adscrito de la Universidad",
            )
        )
        self.assertTrue(
            is_authorized_external_academic_hub(
                "https://alliance.example.org/master",
                "Erasmus Mundus Joint Master",
            )
        )
        self.assertFalse(
            is_authorized_external_academic_hub(
                "https://www.facebook.com/ESNOviedo",
                "Erasmus Student Network Oviedo",
            )
        )
        for service_url in (
            "https://youtu.be/example",
            "https://www.pinterest.com/pin/example",
            "https://tenant.sharepoint.com/sites/erasmus",
        ):
            self.assertFalse(
                is_authorized_external_academic_hub(
                    service_url,
                    "Erasmus Mundus Joint Master",
                )
            )
        self.assertFalse(
            is_authorized_external_academic_hub(
                "https://ocw.mit.edu/course",
                "Instituto Tecnológico de Massachussets",
            )
        )
        self.assertTrue(
            are_degree_titles_compatible(
                "Máster Universitario en Ingeniería Web",
                "Máster Universitario en Ingeniería Web por la Universidad de Oviedo",
                "Universidad de Oviedo",
            )
        )

    def test_phase4_marks_a_valid_cached_guide_as_verified(self):
        class NoopDownloader:
            respect_robots = False

            def set_degree_context(self, _code):
                return None

        data = {
            "codigo_estudio": "PLAN-1",
            "universidad_codigo": "099",
            "plan_estudios": {"elementos_curriculares": [{
                "codigo_asignatura": "1234", "nombre_elemento": "Álgebra",
                "url_guia_docente": "https://uni.example/guia/1234",
            }]},
        }
        cached_guide = {
            "nombre_asignatura": "Álgebra",
            "codigo_asignatura": "1234",
            "temario": [{"titulo": "Tema 1"}],
        }

        class Cache:
            def get(self, **_kwargs):
                return cached_guide

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "degree.json")
            import json
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            result = phase4._process_single_university_guides(
                "099", [{"p_path": path, "data": data}], Cache(), NoopDownloader(), force=False
            )
            self.assertEqual(result["cached_hits"], 1)
            with open(path, encoding="utf-8") as handle:
                saved = json.load(handle)
            element = saved["plan_estudios"]["elementos_curriculares"][0]
            self.assertEqual(element["estado_guia_docente"], "verificada")

    def test_phase4_uses_spa_fallback_when_html_shell_has_no_guide_content(self):
        class FakeResponse:
            status_code = 200
            headers = {"Content-Type": "text/html"}

            def iter_content(self, chunk_size=None):
                yield b"<html><body><div id='app'></div></body></html>"

            def close(self):
                return None

        class FakeDownloader:
            respect_robots = False

            class Robots:
                def check(self, url):
                    return True, None

            robots_policy = Robots()

            def set_degree_context(self, code):
                return None

            def _request_with_retry(self, url, stream=True, robots_prechecked=False):
                return FakeResponse()

            def store_response_content(self, url, response, body):
                return None

        class FakeSPA:
            def render_spa_page(self, url):
                return "<html><body>rendered</body></html>"

        data = {
            "codigo_estudio": "PLAN-1",
            "universidad_codigo": "099",
            "web": "https://uni.example",
            "plan_estudios": {"elementos_curriculares": [{
                "codigo_asignatura": "1234", "nombre_elemento": "Álgebra"
            }]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "degree.json")
            import json
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            parsed_empty = {"nombre_asignatura": "", "codigo_asignatura": "", "temario": [], "sistema_evaluacion": [], "profesorado": [], "competencias": [], "resultados_aprendizaje": []}
            parsed_rendered = {"nombre_asignatura": "Álgebra", "codigo_asignatura": "1234", "temario": [{"titulo": "Tema 1"}], "sistema_evaluacion": [], "profesorado": [], "competencias": [], "resultados_aprendizaje": []}
            cache = SubjectGuideCache(os.path.join(directory, "guides.db"))
            try:
                with patch.object(phase4, "parse_subject_guide", side_effect=[parsed_empty, parsed_rendered]), \
                     patch.object(phase4, "build_subject_guide_discovery_index", return_value={"urls": []}), \
                     patch.object(spa_crawler.SPALayoutCrawler, "get_shared_instance", return_value=FakeSPA()), \
                     patch.dict(os.environ, {"CRAWLER_P4_ENABLE_SPA_FALLBACK": "1"}):
                    result = phase4._process_single_university_guides(
                        "099", [{"p_path": path, "data": data}], cache, FakeDownloader(), force=True
                    )
            finally:
                cache.close()
        self.assertEqual(result["processed_guides"], 1)
        self.assertEqual(result["guide_spa_fallbacks"], 1)
    def test_phase2_skips_an_invalid_university_catalog_before_creating_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            universities_path = os.path.join(directory, "universidades.json")
            titles_path = os.path.join(directory, "titulaciones.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")
            with open(titles_path, "w", encoding="utf-8") as handle:
                handle.write("{}")

            with patch.object(phase2, "UNIVERSIDADES_JSON", universities_path), patch.object(phase2, "TITULACIONES_JSON", titles_path):
                result = phase2.run_phase1_part2(max_workers=1)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "invalid_catalogs")

    def test_phase3_requires_an_identified_academic_year_before_writing_prices(self):
        self.assertTrue(phase3.is_verified_academic_year("2026-2027"))
        self.assertFalse(phase3.is_verified_academic_year("no especificado"))
        self.assertTrue(phase3.is_price_catalog_publishable("2026-2027", True))
        self.assertFalse(phase3.is_price_catalog_publishable("2026-2027", False))
        with patch.object(phase3, "PRICE_CATALOG_ACADEMIC_YEAR", ""):
            result = phase3.run_phase1_part3()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "unverified_price_catalog")

    def test_phase3_reports_partial_when_a_price_file_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_path = os.path.join(directory, "degree.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                handle.write('{"codigo_estudio":"1","universidad_codigo":"001","nivel_academico":"Grado","titulo":"Grado de Prueba"}')
            price_catalog = {
                "Andalucía": {
                    "Grado": {"1": 12.62, "defecto": 12.62},
                    "tasas_admin": 0,
                    "decreto_oficial": "Decreto de prueba",
                }
            }
            with patch.object(phase3, "PRICE_CATALOG_ACADEMIC_YEAR", "2026-2027"), \
                 patch.object(phase3, "PRICE_CATALOG_VERIFIED", True), \
                 patch.object(phase3, "PLANES_DIR", directory), \
                 patch.object(phase3, "DATA_DIR", directory), \
                 patch.object(phase3, "iter_plan_files", return_value=[plan_path]), \
                 patch.object(phase3, "load_precios_ccaa", return_value=price_catalog), \
                 patch.object(phase3, "load_universidades_map", return_value={"001": {"comunidad_autonoma": "Andalucía", "tipo": "Pública"}}), \
                 patch.object(phase3, "atomic_json_dump", side_effect=OSError("read-only")):
                result = phase3.run_phase1_part3()

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], 1)

    def test_phase4_uses_l1_cache_when_its_sqlite_path_is_unusable(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = os.path.join(directory, "not_a_directory")
            with open(blocked_parent, "wb") as handle:
                handle.write(b"blocker")
            cache = SubjectGuideCache(db_path=os.path.join(blocked_parent, "guides.sqlite3"))
            data = {"temario": ["Tema 1"]}

            cache.set("https://www.uca.es/guia", data, "025", "123")

            self.assertTrue(cache._persistent_cache_disabled)
            self.assertEqual(cache.get("https://www.uca.es/guia"), data)
            cache.close()

    def test_phase4_quarantines_and_recreates_corrupt_sqlite_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "guides.sqlite3")
            with open(db_path, "wb") as handle:
                handle.write(b"not a sqlite database")

            cache = SubjectGuideCache(db_path=db_path)
            try:
                data = {"temario": ["Tema 1"]}
                cache.set("https://portal.example/guia", data, "999", "1234")
                self.assertEqual(cache.get("https://portal.example/guia"), data)
                self.assertTrue(cache.recovered_corrupt_path)
                self.assertTrue(os.path.exists(cache.recovered_corrupt_path))
                self.assertTrue(os.path.exists(db_path))
                with open(cache.recovered_corrupt_path, "rb") as handle:
                    self.assertEqual(handle.read(), b"not a sqlite database")
            finally:
                cache.close()

    def test_phase4_reports_partial_when_a_university_worker_fails(self):
        class NoopResource:
            def close(self):
                return None

        with tempfile.TemporaryDirectory() as directory:
            plan_path = os.path.join(directory, "degree.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                handle.write('{"codigo_estudio":"1","universidad_codigo":"001","web":"https://www.uca.es"}')
            universities_path = os.path.join(directory, "universidades.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                handle.write('[]')

            with patch.object(phase4, "PLANES_DIR", directory), \
                 patch.object(phase4, "UNIVERSIDADES_JSON", universities_path), \
                 patch.object(phase4, "SubjectGuideCache", return_value=NoopResource()), \
                 patch.object(phase4, "CrawlLedger", return_value=NoopResource()), \
                 patch.object(phase4, "_process_university_guides_isolated", side_effect=RuntimeError("worker failed")):
                result = phase4.run_phase1_part4(max_workers=1)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], 1)

    def test_phase4_passes_catalog_domain_to_university_worker(self):
        class NoopResource:
            def close(self):
                return None

        captured = {}

        def fake_worker(u_code, degree_items, cache, force=False, ledger=None):
            captured["u_code"] = u_code
            captured["web"] = degree_items[0]["data"].get("web")
            return {"processed_guides": 0}

        with tempfile.TemporaryDirectory() as directory:
            plan_dir = os.path.join(directory, "planes", "008")
            os.makedirs(plan_dir)
            plan_path = os.path.join(plan_dir, "4310001.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                handle.write('{"codigo_estudio":"4310001","universidad_codigo":"008","titulo":"Máster de prueba"}')

            universities_path = os.path.join(directory, "universidades.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                handle.write('[{"codigo":"008","web":"www.ugr.es"}]')

            with patch.object(phase4, "PLANES_DIR", os.path.join(directory, "planes")), \
                 patch.object(phase4, "UNIVERSIDADES_JSON", universities_path), \
                 patch.object(phase4, "SubjectGuideCache", return_value=NoopResource()), \
                 patch.object(phase4, "CrawlLedger", return_value=NoopResource()), \
                 patch.object(phase4, "_process_university_guides_isolated", side_effect=fake_worker):
                result = phase4.run_phase1_part4(max_workers=1)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(captured, {"u_code": "008", "web": "www.ugr.es"})


if __name__ == "__main__":
    unittest.main()
