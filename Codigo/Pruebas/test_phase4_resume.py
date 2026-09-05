import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import cancellation
import pipelines.parte4_asignaturas as phase4


class Phase4ResumeTests(unittest.TestCase):
    def test_recent_not_found_subject_is_resumed_without_network(self):
        data = {
            "codigo_estudio": "PLAN-1",
            "universidad_codigo": "999",
            "plan_estudios": {"elementos_curriculares": [{
                "codigo_asignatura": "1234",
                "nombre_elemento": "Álgebra",
                "estado_guia_docente": "no_encontrada",
                "fecha_ultima_comprobacion_guia": datetime.now().isoformat(),
            }]},
        }

        class NoopDownloader:
            respect_robots = False

            def set_degree_context(self, _code):
                pass

        class ExplodingCache:
            def get(self, **_kwargs):
                raise AssertionError("No debe consultar red/caché al reanudar")

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "degree.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            result = phase4._process_single_university_guides(
                "999", [{"p_path": path, "data": data}], ExplodingCache(), NoopDownloader(), force=False
            )

        self.assertEqual(result["resumed_subjects"], 1)
        self.assertEqual(result["guide_candidate_urls_requested"], 0)

    def test_force_disables_resume(self):
        element = {
            "estado_guia_docente": "no_encontrada",
            "fecha_ultima_comprobacion_guia": datetime.now().isoformat(),
        }
        self.assertTrue(phase4._can_resume_guide_element(element, False))
        self.assertFalse(phase4._can_resume_guide_element(element, True))

    def test_cancellation_is_cooperative(self):
        cancellation.request_shutdown()
        try:
            with self.assertRaises(cancellation.CrawlerCancelled):
                cancellation.raise_if_shutdown_requested()
        finally:
            cancellation.clear_shutdown()

    def test_negative_cache_survives_a_new_cache_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "guides.sqlite3")
            first = phase4.SubjectGuideCache(db_path)
            first.mark_negative("https://portal.example/404")
            first.close()
            second = phase4.SubjectGuideCache(db_path)
            try:
                self.assertTrue(second.is_negative("https://portal.example/404"))
            finally:
                second.close()

    def test_expired_negative_cache_allows_revalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "guides.sqlite3")
            cache = phase4.SubjectGuideCache(db_path)
            url = "https://portal.example/recovered"
            cache.mark_negative(url, reason="http_404")
            conn = cache._get_conn()
            conn.execute(
                "UPDATE guias_negativas SET fecha_marca = ? WHERE url = ?",
                ("2000-01-01 00:00:00", url),
            )
            conn.commit()
            cache.close()
            cache = phase4.SubjectGuideCache(db_path)
            try:
                self.assertFalse(cache.is_negative(url))
                self.assertIsNone(cache.get(url=url))
            finally:
                cache.close()


if __name__ == "__main__":
    unittest.main()
