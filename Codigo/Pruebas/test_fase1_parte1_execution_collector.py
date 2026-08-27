"""
Test y Recolector de Métricas de Ejecución para la Fase 1 - Parte 1 (RUCT y BOE).

Este módulo ejecuta el pipeline de la Fase 1 Parte 1 en un entorno aislado,
validando la concurrencia multiproceso, la integridad del catálogo, la resolución
de resoluciones oficiales del BOE y recolectando telemetría detallada de rendimiento.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRAWLER_DIR = os.path.join(BASE_DIR, "Crawler")
if CRAWLER_DIR not in sys.path:
    sys.path.insert(0, CRAWLER_DIR)

import config
import checkpoint as checkpoint_module
import error_logger
import metrics as metrics_module
import fase1_parte1_ruct_boe as parte1
from metrics import MetricsTracker
from progress_emitter import ProgressEmitter


class TestFase1Parte1ExecutionCollector(unittest.TestCase):
    """Ejecuta la Fase 1 Parte 1 y recolecta métricas detalladas de ejecución."""

    def setUp(self):
        try:
            self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        except TypeError:
            self.temp_dir = tempfile.TemporaryDirectory()
        self.root_tmp = self.temp_dir.name

        # Configurar rutas aisladas en el directorio temporal
        self.planes_dir = os.path.join(self.root_tmp, "planes")
        self.temp_pdf_dir = os.path.join(self.root_tmp, "temp_pdfs")
        self.univ_json = os.path.join(self.root_tmp, "universidades.json")
        self.titulaciones_json = os.path.join(self.root_tmp, "titulaciones.json")
        self.checkpoint_json = os.path.join(self.root_tmp, "checkpoint.json")
        self.stats_json = os.path.join(self.root_tmp, "stats.json")
        self.errors_json = os.path.join(self.root_tmp, "errores.json")
        self.progress_json = os.path.join(self.root_tmp, "progreso.json")
        self.cache_db = os.path.join(self.root_tmp, "cache.sqlite3")

        os.makedirs(self.planes_dir, exist_ok=True)
        os.makedirs(self.temp_pdf_dir, exist_ok=True)

        self._patches = [
            patch.object(config, "PLANES_DIR", self.planes_dir),
            patch.object(config, "TEMP_PDF_DIR", self.temp_pdf_dir),
            patch.object(config, "UNIVERSIDADES_JSON", self.univ_json),
            patch.object(config, "TITULACIONES_JSON", self.titulaciones_json),
            patch.object(config, "CHECKPOINT_JSON", self.checkpoint_json),
            patch.object(config, "ESTADISTICAS_JSON", self.stats_json),
            patch.object(config, "ERRORES_JSON", self.errors_json),
            patch.object(config, "PROGRESS_JSON", self.progress_json),
            patch.object(config, "CACHE_DB_PATH", self.cache_db),
            patch.object(checkpoint_module, "CACHE_DB_PATH", self.cache_db),
            patch.object(error_logger, "ERRORES_JSON", self.errors_json),
            patch.object(metrics_module, "ESTADISTICAS_JSON", self.stats_json),
            patch.object(parte1, "PLANES_DIR", self.planes_dir),
            patch.object(parte1, "TEMP_PDF_DIR", self.temp_pdf_dir),
            patch.object(parte1, "UNIVERSIDADES_JSON", self.univ_json),
            patch.object(parte1, "TITULACIONES_JSON", self.titulaciones_json),
            patch.object(parte1, "ERRORES_JSON", self.errors_json),
            patch.object(parte1, "CHECKPOINT_JSON", self.checkpoint_json),
            patch.object(parte1, "ESTADISTICAS_JSON", self.stats_json),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        try:
            checkpoint_module.CheckpointManager().close()
        except Exception:
            pass
        for p in reversed(self._patches):
            p.stop()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_fase1_parte1_execution_and_metrics_collection(self):
        """Lanza la Fase 1 Parte 1 con datos simulados y recolecta métricas completas."""
        
        # 1. Catálogo simulado de universidades
        mock_univ_catalog = [
            {
                "codigo": "025",
                "nombre": "Universidad de Cádiz",
                "tipo": "Pública",
                "ccaa": "Andalucía",
                "web": "https://www.uca.es"
            }
        ]

        # 2. Catálogo simulado de titulaciones activas de la UCA
        mock_degrees_catalog = [
            {
                "codigo_estudio": "2500100",
                "titulo": "Grado en Ingeniería Informática",
                "nivel_academico": "Grado",
                "estado": "Publicado en BOE",
                "situacion_matriculacion": "activa"
            },
            {
                "codigo_estudio": "2500200",
                "titulo": "Grado en Matemáticas",
                "nivel_academico": "Grado",
                "estado": "Impartiéndose",
                "situacion_matriculacion": "activa"
            }
        ]

        # 3. Ficha RUCT de detalle con candidatos BOE
        mock_detail_degree_1 = {
            "is_extinct": False,
            "lifecycle": "vigente_matriculable",
            "status_text": "Vigente",
            "latest_boe_url": "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-1000",
            "boe_date": "2024-05-15",
            "all_boe_candidates": [
                {
                    "url": "https://www.boe.es/boe/dias/2024/05/15/pdfs/BOE-A-2024-1000.pdf",
                    "priority": 100,
                    "type": "plan_correccion",
                    "boe_date": "2024-05-15"
                }
            ]
        }

        mock_detail_degree_2 = {
            "is_extinct": False,
            "lifecycle": "vigente_matriculable",
            "status_text": "Vigente",
            "latest_boe_url": None,
            "boe_date": None,
            "all_boe_candidates": []
        }

        # 4. Plan de estudios curricular simulado tras parseo del PDF
        mock_curriculum_plan = {
            "total_elementos": 40,
            "resumen_creditos": {
                "Formación Básica": "60",
                "Obligatorias": "120",
                "Optativas": "48",
                "Trabajo Fin de Grado": "12",
                "Créditos Totales": "240"
            },
            "elementos_curriculares": [
                {
                    "modulo": "Formación Básica",
                    "materia": "Informática",
                    "codigo_asignatura": f"10{i:02d}",
                    "nombre_elemento": f"Asignatura Informatica {i}",
                    "creditos_ects": "6.0",
                    "caracter": "FB" if i <= 10 else "OB",
                    "curso": str(((i - 1) // 10) + 1),
                    "cuatrimestre": "1C" if i % 2 != 0 else "2C"
                }
                for i in range(1, 41)
            ]
        }

        tracker = MetricsTracker(filepath=self.stats_json)
        emitter = ProgressEmitter()

        def mock_fetch_content(url):
            return b"dummy_content"

        def mock_fetch_text(url):
            return "<html><body>RUCT Detalle</body></html>"

        def mock_download_file(url, target_path, is_pdf=False):
            with open(target_path, "wb") as f:
                f.write(b"%PDF-1.4 Mock BOE PDF Content")

        def mock_parse_detail(html_text):
            if "2500100" in str(getattr(tracker, "current_degree", "")):
                return mock_detail_degree_1
            return mock_detail_degree_2

        start_time = time.time()

        with patch("fase1_parte1_ruct_boe.parse_universities_xls", return_value=mock_univ_catalog), \
             patch("fase1_parte1_ruct_boe.parse_degrees_xls", return_value=mock_degrees_catalog), \
             patch("fase1_parte1_ruct_boe.parse_degree_detail_html", side_effect=mock_parse_detail), \
             patch("fase1_parte1_ruct_boe.parse_boe_pdf", return_value=mock_curriculum_plan), \
             patch("downloader.RUCTDownloader.fetch_content", side_effect=mock_fetch_content), \
             patch("downloader.RUCTDownloader.fetch_text", side_effect=mock_fetch_text), \
             patch("downloader.RUCTDownloader.download_file", side_effect=mock_download_file):

            result = parte1.run_phase1_part1(
                limit_universities=1,
                limit_degrees=2,
                force=True,
                max_workers=1,
                metrics_tracker=tracker,
                progress_emitter=emitter
            )

        duration = time.time() - start_time

        telemetry = {
            "execution_summary": {
                "status": result.get("status"),
                "duration_seconds": round(duration, 3),
                "total_enqueued": result.get("total_enqueued"),
                "universities_processed": result.get("universities_processed"),
                "error": result.get("error"),
            },
            "metrics": {
                "universidades_inspeccionadas": tracker.universidades_inspeccionadas,
                "titulaciones_inspeccionadas": tracker.titulaciones_inspeccionadas,
                "titulaciones_actualizadas": tracker.titulaciones_descargadas_actualizadas,
                "titulaciones_al_dia": tracker.titulaciones_al_dia,
                "pdfs_parseados": tracker.pdfs_parseados,
                "errores_detectados": tracker.errores_detectados,
                "total_io_network_time": tracker.total_io_network_time,
                "total_pdf_parsing_time": tracker.total_pdf_parsing_time,
            },
            "persisted_artifacts": {
                "universidades_json_exists": os.path.exists(self.univ_json),
                "titulaciones_json_exists": os.path.exists(self.titulaciones_json),
                "stats_json_exists": os.path.exists(self.stats_json),
                "temp_pdfs_leaked": len(os.listdir(self.temp_pdf_dir)),
            }
        }

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["universities_processed"], 1)
        self.assertEqual(tracker.universidades_inspeccionadas, 1)
        self.assertEqual(tracker.titulaciones_inspeccionadas, 2)
        self.assertEqual(tracker.errores_detectados, 0)
        self.assertTrue(os.path.exists(self.univ_json))
        self.assertTrue(os.path.exists(self.titulaciones_json))
        self.assertEqual(len(os.listdir(self.temp_pdf_dir)), 0)

        with open(self.univ_json, "r", encoding="utf-8") as f:
            univ_data = json.load(f)
            self.assertEqual(len(univ_data), 1)
            self.assertEqual(univ_data[0]["codigo"], "025")

        with open(self.titulaciones_json, "r", encoding="utf-8") as f:
            cat_data = json.load(f)
            self.assertIn("025", cat_data)
            self.assertEqual(cat_data["025"]["total_titulaciones_vigentes"], 2)

        print("\n" + "=" * 70)
        print("          REPORTE DE EJECUCIÓN - FASE 1 PARTE 1")
        print("=" * 70)
        print(f" Estado de ejecución:            {telemetry['execution_summary']['status']}")
        print(f" Duración total:                 {telemetry['execution_summary']['duration_seconds']} s")
        print(f" Universidades procesadas:       {telemetry['metrics']['universidades_inspeccionadas']}")
        print(f" Titulaciones inspeccionadas:    {telemetry['metrics']['titulaciones_inspeccionadas']}")
        print(f" Tareas encoladas en workers:    {telemetry['execution_summary']['total_enqueued']}")
        print(f" Errores de red/pipeline:        {telemetry['metrics']['errores_detectados']}")
        print(f" Archivos temporales huérfanos:  {telemetry['persisted_artifacts']['temp_pdfs_leaked']}")
        print("=" * 70)

    def test_fase1_parte1_handles_and_records_exceptions_cleanly(self):
        """Verifica que fallos de red aislados se registren en errores sin interrumpir la fase."""
        tracker = MetricsTracker(filepath=self.stats_json)
        emitter = ProgressEmitter()

        with patch("downloader.RUCTDownloader.fetch_content", side_effect=Exception("Fallo de red simulado")):
            result = parte1.run_phase1_part1(
                limit_universities=1,
                max_workers=1,
                metrics_tracker=tracker,
                progress_emitter=emitter
            )

        self.assertEqual(result["status"], "failed")
        self.assertIsNotNone(result["error"])
        self.assertGreater(tracker.errores_detectados, 0)
        self.assertTrue(os.path.exists(self.errors_json))


if __name__ == "__main__":
    unittest.main()