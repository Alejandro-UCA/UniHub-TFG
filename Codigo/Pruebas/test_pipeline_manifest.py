import os
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import main_fase_1
import run_manifest


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

    def set_finished(self):
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


if __name__ == "__main__":
    unittest.main()
