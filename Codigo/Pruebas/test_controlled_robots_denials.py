import os
import sys
import json
import tempfile
import unittest

from unittest.mock import patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from downloader import RobotsDeniedException, RUCTDownloader
from error_logger import ErrorLogger
from metrics import MetricsTracker


class TestControlledRobotsDenials(unittest.TestCase):
    def test_explicit_rule_denial_has_specific_message(self):
        error = RobotsDeniedException(
            "https://www.boe.es/boe/dias/2014/11/22/pdfs/BOE-A-2014-12127.pdf",
            "denegado_por_reglas",
        )

        self.assertIn("robots.txt deniega el rastreo", str(error))
        self.assertNotIn("No se pudo verificar", str(error))
        self.assertTrue(error.explicit_rule_denial)

    def test_unverifiable_robots_keeps_diagnostic_message(self):
        error = RobotsDeniedException("https://example.edu/plan.pdf", "error_http_503")

        self.assertIn("No se pudo verificar el permiso de robots.txt", str(error))
        self.assertFalse(error.explicit_rule_denial)

    def test_downloader_raises_typed_exception_for_robot_denial(self):
        downloader = RUCTDownloader(
            delay=0,
            max_retries=1,
            respect_robots=True,
            enable_http2=False,
        )
        try:
            with patch.object(downloader.robots_policy, "check", return_value=(False, None)), \
                 patch.object(downloader.robots_policy, "explain", return_value="denegado_por_reglas"):
                with self.assertRaises(RobotsDeniedException):
                    downloader._request_with_retry("https://www.boe.es/plan.pdf")
        finally:
            downloader.close()

    def test_metrics_separate_controlled_incidents_from_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = MetricsTracker(filepath=os.path.join(directory, "stats.json"))
            tracker.inc_incidencias_controladas(2)
            report = tracker.generate_report()

        self.assertEqual(report["operaciones_crawler"]["incidencias_controladas"], 2)
        self.assertEqual(report["operaciones_crawler"]["errores_registrados"], 0)

    def test_error_log_marks_controlled_incident(self):
        with tempfile.TemporaryDirectory() as directory:
            error_path = os.path.join(directory, "errores.json")
            ErrorLogger(filepath=error_path).log_error(
                "pdf_download",
                "015",
                "https://www.boe.es/plan.pdf",
                "Incidencia controlada: robots.txt deniega el PDF",
                "robots.txt deniega el rastreo",
                classification="incidencia_controlada",
            )
            with open(error_path, "r", encoding="utf-8") as handle:
                errors = json.load(handle)

        self.assertEqual(errors[0]["clasificacion"], "incidencia_controlada")


if __name__ == "__main__":
    unittest.main()
