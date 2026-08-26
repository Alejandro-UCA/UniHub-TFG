import os
import sys
import time
import json
import tempfile
import unittest
import threading
import concurrent.futures

# Agregar paths para importar modulos de Crawler
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import main
import config
import downloader
import parsers
import checkpoint
import error_logger
import metrics
import univ_web_crawler
import spa_crawler
import asignaturas_crawler
import precios_crawler


class TestPhase1AuditV2Fixes(unittest.TestCase):

    def test_01_all_modules_import_cleanly(self):
        """Verifica que todos los modulos de la Fase 1 compilen y se importen sin errores de sintaxis o NameError."""
        self.assertTrue(hasattr(main, "run_crawler"))
        self.assertTrue(hasattr(spa_crawler, "SPALayoutCrawler"))
        self.assertTrue(hasattr(error_logger, "ErrorLogger"))
        self.assertTrue(hasattr(checkpoint, "CheckpointManager"))
        self.assertTrue(hasattr(metrics, "PerformanceTracker"))
        self.assertTrue(hasattr(parsers, "_RE_DYNAMIC_TIPO_FIRST"))
        self.assertTrue(hasattr(parsers, "_RE_DYNAMIC_CRED_FIRST"))

    def test_02_spa_crawler_re_import(self):
        """Verifica que spa_crawler tenga el modulo re disponible para sanitizar nombres de archivo."""
        import re
        self.assertIn("re", spa_crawler.__dict__)
        filename_sample = "Guia Docente 2025/2026: (Matematicas).pdf"
        sanitized = spa_crawler.re.sub(r'[^\w.-]', '_', filename_sample)
        self.assertEqual(sanitized, "Guia_Docente_2025_2026___Matematicas_.pdf")

    def test_03_error_logger_does_not_wipe_history_on_transient_failure(self):
        """Verifica que ErrorLogger no destruya el historial de errores ante lecturas transitorias fallidas."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tf:
            tf_path = tf.name
            initial_data = [
                {"timestamp": "2026-08-26T00:00:00", "fase": "fase_1", "id_entidad": "U001", "url": "http://test", "motivo_fallo": "error 1", "detalles_excepcion": ""}
            ]
            json.dump(initial_data, tf)

        try:
            logger = error_logger.ErrorLogger(filepath=tf_path)
            self.assertEqual(len(logger.errors), 1)

            # Simular nuevo error
            logger.log_error("fase_2", "U002", "http://test2", "error 2")
            self.assertEqual(len(logger.errors), 2)

            # Verificar que en disco hay 2 errores
            with open(tf_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[0]["id_entidad"], "U001")
            self.assertEqual(saved[1]["id_entidad"], "U002")
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_04_checkpoint_multi_process_sqlite_consolidation(self):
        """Verifica que CheckpointManager consolide datos desde SQLite WAL cuando multiples instancias escriben."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tf_json,              tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite3") as tf_db:
            json_path = tf_json.name
            db_path = tf_db.name

        try:
            mgr_a = checkpoint.CheckpointManager(filepath=json_path, db_path=db_path)
            mgr_b = checkpoint.CheckpointManager(filepath=json_path, db_path=db_path)

            # Worker A marca una universidad
            mgr_a.mark_university_processed("044")
            # Worker B marca otra universidad y un hash
            mgr_b.mark_university_processed("045")
            mgr_b.mark_non_study_plan_pdf("http://boe.es/pdf1.pdf", "hash_sha256_123")
            mgr_b.record_pdf_download_failure("http://boe.es/pdf2.pdf", "2500123", "HTTP 404")

            # Worker A fuerza el guardado a JSON
            mgr_a.flush()

            # Comprobar que el archivo JSON resultante contiene AMBOS registros consolidados desde SQLite WAL
            with open(json_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.assertIn("044", state.get("processed_universities", []))
            self.assertIn("045", state.get("processed_universities", []))
            self.assertIn("http://boe.es/pdf1.pdf", state.get("non_study_plan_pdfs", []))
            self.assertIn("hash_sha256_123", state.get("non_study_plan_hashes", []))
            self.assertIn("http://boe.es/pdf2.pdf", state.get("failed_pdf_downloads", {}))
        finally:
            for p in [json_path, db_path, f"{db_path}-wal", f"{db_path}-shm"]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    def test_05_subject_guide_cache_bounded_l1(self):
        """Verifica que SubjectGuideCache aplique poda automatica a la cache L1 en RAM."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite3") as tf_db:
            db_path = tf_db.name

        try:
            cache = asignaturas_crawler.SubjectGuideCache(db_path=db_path)
            cache.MAX_L1_ENTRIES = 10  # Ajustar a un valor pequeno para el test

            for i in range(15):
                cache.set(f"http://guide.test/{i}", {"id": i, "name": f"Subject {i}"}, u_code="044", asig_code=str(100+i))

            # Debe haber podado la cache en RAM a menos o igual a MAX_L1_ENTRIES
            self.assertLessEqual(len(cache._l1_url_cache), 10)
            self.assertLessEqual(len(cache._l1_comp_cache), 10)

            # Pero en SQLite WAL todos los registros deben seguir accesibles
            res = cache.get(url="http://guide.test/0")
            self.assertIsNotNone(res)
            self.assertEqual(res["id"], 0)
        finally:
            for p in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    def test_06_metrics_tracker_atomic_increments(self):
        """Verifica que PerformanceTracker ofrezca operaciones de incremento concurrentes y reporte preciso de I/O."""
        tracker = metrics.PerformanceTracker()
        tracker.universidades_inspeccionadas = 0
        tracker.titulaciones_inspeccionadas = 0
        tracker.titulaciones_al_dia = 0
        tracker.errores_detectados = 0

        def worker():
            for _ in range(50):
                tracker.inc_universidades(1)
                tracker.inc_titulaciones(1)
                tracker.inc_titulaciones_al_dia(1)
                tracker.inc_errores(1)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(tracker.universidades_inspeccionadas, 200)
        self.assertEqual(tracker.titulaciones_inspeccionadas, 200)
        self.assertEqual(tracker.titulaciones_al_dia, 200)
        self.assertEqual(tracker.errores_detectados, 200)

        # Probar reporte
        tracker.record_io_time(1.25, domain="boe.es", bytes_transferred=1024)
        report = tracker.generate_report()
        self.assertEqual(report["rendimiento_tiempo"]["tiempo_espera_io_red_seg"], 1.25)
        self.assertEqual(report["operaciones_crawler"]["universidades_inspeccionadas"], 200)

    def test_07_asignaturas_crawler_planes_dir_missing_handled(self):
        """Verifica que enrich_all_degrees_with_subject_guides maneje la ausencia de PLANES_DIR sin lanzar FileNotFoundError."""
        non_existent_dir = os.path.join(tempfile.gettempdir(), "unihub_non_existent_dir_test_123")
        if os.path.exists(non_existent_dir):
            os.rmdir(non_existent_dir)

        orig_planes = asignaturas_crawler.PLANES_DIR
        try:
            asignaturas_crawler.PLANES_DIR = non_existent_dir
            res = asignaturas_crawler.run_phase1_part4()
            self.assertEqual(res["total_planes_inspeccionados"], 0)
        finally:
            asignaturas_crawler.PLANES_DIR = orig_planes


if __name__ == "__main__":
    unittest.main()
