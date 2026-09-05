import os
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from pipelines import main
from core import manifest


class _Noop:
    def flush(self):
        pass

    def save(self):
        pass


class _Progress:
    def update_part(self, *_args):
        pass

    def set_failed(self, *_args):
        pass

    def set_partial(self, *_args):
        pass

    def set_finished(self):
        pass

    def set_cancelled(self, *_args):
        pass


class TestPipelineManifest(unittest.TestCase):
    def test_metrics_are_safe_and_missing_degrees_are_not_reported_as_discovered(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory):
            manifest = run_manifest.RunManifest(parts=[2])
            manifest.start()
            manifest.record_part(2, {"universities_processed": "invalid", "missing_degrees": 3, "resolved_degrees": -2})

            coverage = manifest.data["coverage"]
            self.assertEqual(coverage["universities_attempted"], 0)
            self.assertEqual(coverage["degrees_discovered"], 0)
            self.assertEqual(coverage["degrees_pending_resolution"], 3)
            self.assertEqual(coverage["degrees_resolved"], 0)

    def test_controlled_incidents_are_counted_without_marking_part_failed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory):
            manifest = run_manifest.RunManifest(parts=[1])
            manifest.start()
            manifest.record_part(1, {"status": "completed", "incidencias_controladas": 2})

            self.assertEqual(manifest.data["coverage"]["incidencias_controladas"], 2)
            self.assertEqual(manifest.data["coverage"]["partial_or_failed_parts"], [])

    def test_subject_guide_coverage_is_recorded_in_manifest(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory):
            manifest = run_manifest.RunManifest(parts=[4])
            manifest.start()
            manifest.record_part(4, {
                "status": "completed",
                "guide_subjects_considered": 67,
                "processed_guides": 54,
                "guide_subjects_not_found": 13,
            })

            coverage = manifest.data["coverage"]
            self.assertEqual(coverage["subjects_considered"], 67)
            self.assertEqual(coverage["guides_found"], 54)
            self.assertEqual(coverage["guides_not_found"], 13)

    def test_cached_guides_are_included_in_found_coverage(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory):
            manifest = run_manifest.RunManifest(parts=[4])
            manifest.start()
            manifest.record_part(4, {
                "status": "completed",
                "guide_subjects_considered": 20,
                "processed_guides": 3,
                "cached_hits": 14,
                "guide_subjects_not_found": 3,
            })

            coverage = manifest.data["coverage"]
            self.assertEqual(coverage["guides_found"], 17)
            self.assertEqual(coverage["cached_hits"], 14)

    def test_university_coverage_is_unique_across_phases_and_guide_cost_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory):
            manifest = run_manifest.RunManifest(parts=[1, 2, 4])
            manifest.start()
            manifest.record_part(1, {"universities_processed": 2, "university_codes_processed": ["008", "015"]})
            manifest.record_part(2, {"universities_processed": 2, "university_codes_processed": ["008", "015"]})
            manifest.record_part(4, {
                "universities_processed": 2,
                "university_codes_processed": ["008", "015"],
                "guide_candidate_urls_generated": 10,
                "guide_candidate_urls_requested": 8,
                "guide_http_200": 1,
                "guide_http_404": 7,
                "guide_robots_denied": 2,
            })

            coverage = manifest.data["coverage"]
            self.assertEqual(coverage["universities_attempted"], 2)
            self.assertEqual(coverage["university_codes_attempted"], ["008", "015"])
            self.assertEqual(coverage["guide_candidate_urls_generated"], 10)
            self.assertEqual(coverage["guide_candidate_urls_requested"], 8)
            self.assertEqual(coverage["guide_http_404"], 7)
            self.assertEqual(coverage["guide_robots_denied"], 2)

    def test_manifest_records_runtime_capabilities(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory), \
                patch.object(run_manifest, "detect_runtime_capabilities", return_value={"ocr": True, "missing": []}):
            manifest = run_manifest.RunManifest(parts=[1])
            self.assertEqual(manifest.data["execution"]["runtime_capabilities"], {"ocr": True, "missing": []})

    def test_failed_etl_marks_pipeline_as_partial(self):
        with patch.object(main_fase_1, "normalize_phase_selection", return_value=[1]), \
             patch.object(main_fase_1, "_run_part", return_value={"status": "completed"}), \
             patch.object(main_fase_1, "trigger_api_etl_sync", return_value=False), \
             patch.object(main_fase_1, "PerformanceTracker", return_value=_Noop()), \
             patch.object(main_fase_1, "CheckpointManager", return_value=_Noop()), \
             patch.object(main_fase_1, "ProgressEmitter", return_value=_Progress()), \
             patch.object(main_fase_1, "RunManifest") as manifest_type, \
             patch.object(main_fase_1.CrawlLedger, "prune_http_cache"):
            manifest = manifest_type.return_value
            manifest.start.return_value = "test-run"
            result = main_fase_1.run_phase1(parts=[1])

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["etl_sync"], {"status": "failed"})
        manifest.record_etl_sync.assert_called_once_with({"status": "failed"})

    def test_omitted_part_is_reported_as_partial_not_runtime_error(self):
        from unittest.mock import MagicMock

        progress = MagicMock()
        with patch.object(main_fase_1, "normalize_phase_selection", return_value=[1, 3]), \
             patch.object(main_fase_1, "_run_part", side_effect=[
                 {"status": "completed"},
                 {"status": "skipped", "reason": "unverified_price_catalog"},
             ]), \
             patch.object(main_fase_1, "PerformanceTracker", return_value=_Noop()), \
             patch.object(main_fase_1, "CheckpointManager", return_value=_Noop()), \
             patch.object(main_fase_1, "ProgressEmitter", return_value=progress), \
             patch.object(main_fase_1, "RunManifest") as manifest_type, \
             patch.object(main_fase_1.CrawlLedger, "prune_http_cache"):
            manifest_type.return_value.start.return_value = "partial-run"
            result = main_fase_1.run_phase1(parts=[1, 3], sync_etl=False)

        self.assertEqual(result["status"], "partial")
        progress.set_partial.assert_called_once()
        progress.set_failed.assert_not_called()

    def test_cancellation_finishes_manifest_with_resumable_status(self):
        from core import cancellation
        cancellation.clear_shutdown()
        try:
            def cancel_part(_part, **_kwargs):
                cancellation.request_shutdown()
                return {"status": "cancelled"}

            with patch.object(main_fase_1, "normalize_phase_selection", return_value=(1,)), \
                 patch.object(main_fase_1, "_run_part", side_effect=cancel_part), \
                 patch.object(main_fase_1, "PerformanceTracker", return_value=_Noop()), \
                 patch.object(main_fase_1, "CheckpointManager", return_value=_Noop()), \
                 patch.object(main_fase_1, "ProgressEmitter", return_value=_Progress()), \
                 patch.object(main_fase_1, "RunManifest") as manifest_type, \
                 patch.object(main_fase_1.CrawlLedger, "prune_http_cache"):
                manifest = manifest_type.return_value
                manifest.start.return_value = "cancelled-run"
                result = main_fase_1.run_phase1(parts=[1], sync_etl=False)

            self.assertEqual(result["status"], "cancelled")
            manifest.finish.assert_called_once_with("cancelled")
        finally:
            cancellation.clear_shutdown()

    def test_manifest_preserves_university_and_domain_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(run_manifest, "RUN_MANIFESTS_DIR", directory):
                manifest = run_manifest.RunManifest(parts=[4])
                manifest.start()
                manifest.record_part(4, {
                    "status": "cancelled",
                    "resumed_subjects": 2,
                    "negative_cache_hits": 3,
                    "metrics_by_university": {"999": {"guide_subjects_considered": 5}},
                    "metrics_by_domain": {"portal.example": {"http_404": 4}},
                })

                coverage = manifest.data["coverage"]
                self.assertEqual(coverage["subjects_resumed"], 2)
                self.assertEqual(coverage["negative_cache_hits"], 3)
                self.assertEqual(coverage["metrics_by_university"]["999"]["guide_subjects_considered"], 5)
                self.assertEqual(coverage["metrics_by_domain"]["portal.example"]["http_404"], 4)
                self.assertEqual(coverage["partial_or_failed_parts"], [4])


if __name__ == "__main__":
    unittest.main()
