import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import pipelines.parte4_asignaturas as phase4


class _Disposable:
    _persistent_cache_disabled = False
    _disabled = False

    def close(self):
        pass


class TestPhase4MetricsAggregation(unittest.TestCase):
    def test_run_aggregates_worker_metrics_by_university_and_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            plans_dir = os.path.join(directory, "plans")
            os.makedirs(plans_dir)
            with open(os.path.join(plans_dir, "plan.json"), "w", encoding="utf-8") as handle:
                json.dump({
                    "universidad_codigo": "999",
                    "codigo_estudio": "PLAN-1",
                    "plan_estudios": {"elementos_curriculares": [{
                        "codigo_asignatura": "1234",
                        "nombre_elemento": "Álgebra",
                    }]},
                }, handle, ensure_ascii=False)
            universities_path = os.path.join(directory, "universidades.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                json.dump([], handle)

            worker_result = {
                "university_code": "999",
                "guide_subjects_considered": 1,
                "guide_candidate_urls_generated": 2,
                "guide_candidate_urls_requested": 1,
                "guide_http_200": 1,
                "by_domain": {
                    "portal.example": {
                        "candidate_urls_generated": 2,
                        "candidate_urls_requested": 1,
                        "http_200": 1,
                    },
                },
            }
            with patch.object(phase4, "PLANES_DIR", plans_dir), \
                 patch.object(phase4, "UNIVERSIDADES_JSON", universities_path), \
                 patch.object(phase4, "SubjectGuideCache", return_value=_Disposable()), \
                 patch.object(phase4, "CrawlLedger", return_value=_Disposable()), \
                 patch.object(phase4, "_process_university_guides_isolated", return_value=worker_result):
                result = phase4.run_phase1_part4(max_workers=1)

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["metrics_by_university"]["999"]["guide_subjects_considered"], 1)
            self.assertEqual(result["metrics_by_domain"]["portal.example"]["http_200"], 1)

    def test_part4_keeps_a_bounded_number_of_workers_in_flight(self):
        with tempfile.TemporaryDirectory() as directory:
            plans_dir = os.path.join(directory, "plans")
            os.makedirs(plans_dir)
            for index in range(5):
                with open(os.path.join(plans_dir, f"plan-{index}.json"), "w", encoding="utf-8") as handle:
                    json.dump({
                        "universidad_codigo": str(990 + index),
                        "codigo_estudio": f"PLAN-{index}",
                        "plan_estudios": {"elementos_curriculares": []},
                    }, handle)
            universities_path = os.path.join(directory, "universidades.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                json.dump([], handle)

            state = {"active": 0, "maximum": 0}
            state_lock = threading.Lock()

            def worker(u_code, *_args):
                with state_lock:
                    state["active"] += 1
                    state["maximum"] = max(state["maximum"], state["active"])
                time.sleep(0.02)
                with state_lock:
                    state["active"] -= 1
                return {"university_code": u_code}

            with patch.object(phase4, "PLANES_DIR", plans_dir), \
                 patch.object(phase4, "UNIVERSIDADES_JSON", universities_path), \
                 patch.object(phase4, "SubjectGuideCache", return_value=_Disposable()), \
                 patch.object(phase4, "CrawlLedger", return_value=_Disposable()), \
                 patch.object(phase4, "_process_university_guides_isolated", side_effect=worker):
                result = phase4.run_phase1_part4(max_workers=2)

            self.assertEqual(result["universities_processed"], 5)
            self.assertLessEqual(state["maximum"], 2)

    def test_part4_skips_universities_denied_by_part2_before_submitting_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            plans_dir = os.path.join(directory, "plans")
            os.makedirs(plans_dir)
            for code in ("997", "998"):
                with open(os.path.join(plans_dir, f"{code}.json"), "w", encoding="utf-8") as handle:
                    json.dump({
                        "universidad_codigo": code,
                        "codigo_estudio": f"PLAN-{code}",
                        "plan_estudios": {"elementos_curriculares": []},
                    }, handle)
            universities_path = os.path.join(directory, "universidades.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                json.dump([], handle)

            submitted = []

            def worker(u_code, *_args):
                submitted.append(str(u_code))
                return {"university_code": u_code}

            with patch.object(phase4, "PLANES_DIR", plans_dir), \
                 patch.object(phase4, "UNIVERSIDADES_JSON", universities_path), \
                 patch.object(phase4, "SubjectGuideCache", return_value=_Disposable()), \
                 patch.object(phase4, "CrawlLedger", return_value=_Disposable()), \
                 patch.object(phase4, "_process_university_guides_isolated", side_effect=worker):
                result = phase4.run_phase1_part4(
                    max_workers=1,
                    robots_denied_university_codes={"997"},
                )

            self.assertEqual(submitted, ["998"])
            self.assertEqual(result["universities_processed"], 1)
            self.assertEqual(result["robots_denied_universities_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
