import os
import sys
import time
import json
import tempfile
import unittest
import threading
import concurrent.futures
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

# Agregar paths para importar modulos de Crawler
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

import main
from core import config
from core import downloader
import parsers
from core import checkpoint
from core import error_logger
from core import metrics
from pipelines import parte2_web_crawler as fase1_parte2_web_crawler
from pipelines import parte2_web_crawler
from parsers import spa_engine as spa_crawler
from pipelines import parte4_asignaturas
from pipelines import parte3_precios
from core import capabilities


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

    def test_01b_runtime_capabilities_are_explicit(self):
        capabilities = runtime_capabilities.detect_runtime_capabilities()
        self.assertIn("javascript_rendering", capabilities)
        self.assertIn("ocr", capabilities)
        self.assertEqual(
            capabilities["javascript_rendering"],
            capabilities["playwright_package"] and capabilities["chromium_binary"],
        )
        self.assertEqual(
            capabilities["ocr"],
            capabilities["pypdfium2"] and capabilities["pytesseract_package"] and capabilities["tesseract_binary"],
        )
        self.assertIsInstance(capabilities["missing"], list)

    def test_01c_part2_robots_policy_dependency_is_available(self):
        crawler = fase1_parte2_web_crawler.UniversityWebCrawler.__new__(
            fase1_parte2_web_crawler.UniversityWebCrawler
        )
        crawler.user_agent = "UniHub-test"
        with patch.object(fase1_parte2_web_crawler.RobotsPolicy, "check", return_value=(True, None)):
            allowed, delay = crawler.check_robots_allowed("https://university.example")
        self.assertTrue(allowed)
        self.assertIsNone(delay)

    def test_01d_part2_recovery_preserves_existing_pricing_metadata(self):
        target = {
            "precio_credito_ects": 21.5,
            "precio_estimado_anual": 1290.0,
        }
        recovered = {"precio_credito_ects": 22.0}
        catalog = {"precio_credito_2": 23.0}

        fase1_parte2_web_crawler.merge_preserved_pricing(
            target,
            recovered=recovered,
            catalog=catalog,
        )

        self.assertEqual(target["precio_credito_ects"], 22.0)
        self.assertEqual(target["precio_credito_2"], 23.0)
        self.assertEqual(target["precio_estimado_anual"], 1290.0)

    def test_01e_shared_plan_propagation_refreshes_quality_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "001", "source.json")
            target_path = os.path.join(directory, "002", "target.json")
            os.makedirs(os.path.dirname(source_path), exist_ok=True)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shared_plan = {
                "resumen_creditos": {"Créditos Totales": "240"},
                "elementos_curriculares": [
                    {"nombre_elemento": f"Asignatura {index}", "creditos_ects": 6}
                    for index in range(40)
                ],
            }
            with open(source_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "codigo_estudio": "SOURCE",
                        "titulo": "Grado en Datos",
                        "nivel_academico": "Grado",
                        "universidad_codigo": "001",
                        "universidad_nombre": "Universidad Fuente",
                        "boe_url": "https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf",
                        "web_fuente_directa_url": "https://source.example/otro-programa",
                        "origen_fuente": "boe",
                        "estado_fuente": "verificada",
                        "plan_estudios": shared_plan,
                    },
                    handle,
                )
            with open(target_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "codigo_estudio": "TARGET",
                        "titulo": "Grado en Datos",
                        "nivel_academico": "Grado",
                        "universidad_codigo": "002",
                        "universidad_nombre": "Universidad Destino",
                        "boe_url": "https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf",
                        "plan_estudios": None,
                    },
                    handle,
                )

            result = fase1_parte2_web_crawler.propagate_interuniversity_and_shared_boe_plans(directory)

            with open(target_path, encoding="utf-8") as handle:
                target = json.load(handle)
            self.assertEqual(result["total_propagated"], 1)
            self.assertTrue((target.get("calidad_datos") or {}).get("publicable"))
            self.assertEqual(target.get("estado_fuente"), "verificada")
            self.assertIsNone(target.get("web_fuente_directa_url"))
            self.assertTrue(target.get("fuentes"))

            target_mtime = os.stat(target_path).st_mtime_ns
            time.sleep(0.01)
            second_result = fase1_parte2_web_crawler.propagate_interuniversity_and_shared_boe_plans(directory)
            self.assertEqual(second_result["total_propagated"], 0)
            self.assertEqual(os.stat(target_path).st_mtime_ns, target_mtime)

    def test_01e2_quality_reconciliation_keeps_partial_plan_data(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_path = os.path.join(directory, "001", "PARTIAL.json")
            os.makedirs(os.path.dirname(plan_path), exist_ok=True)
            partial_plan = {
                "resumen_creditos": {"Créditos Totales": "60"},
                "elementos_curriculares": [
                    {"nombre_elemento": f"Materia {index}", "creditos_ects": 6}
                    for index in range(3)
                ],
            }
            with open(plan_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "codigo_estudio": "PARTIAL",
                        "titulo": "Máster en Datos",
                        "nivel_academico": "Máster",
                        "universidad_codigo": "001",
                        "universidad_nombre": "Universidad de Prueba",
                        "boe_url": "https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-2.pdf",
                        "origen_fuente": "boe",
                        "estado_fuente": "verificada",
                        "estado_calidad": "verificado_boe",
                        "calidad_datos": {"publicable": True},
                        "plan_estudios": partial_plan,
                    },
                    handle,
                )

            fase1_parte2_web_crawler.propagate_interuniversity_and_shared_boe_plans(directory)

            with open(plan_path, encoding="utf-8") as handle:
                after = json.load(handle)
            self.assertIsInstance(after.get("plan_estudios"), dict)
            self.assertFalse((after.get("calidad_datos") or {}).get("publicable"))
            self.assertEqual(after.get("estado_fuente"), "candidata_no_publicable")
            self.assertEqual(len(after["plan_estudios"]["elementos_curriculares"]), 3)

    def test_01e3_incompatible_web_source_collision_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            shared_url = "https://university.example/catalogo/plan"
            for index, title in enumerate(("Máster en Datos", "Máster en Historia"), start=1):
                path = os.path.join(directory, "001", f"RECORD{index}.json")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "codigo_estudio": f"RECORD{index}",
                            "titulo": title,
                            "nivel_academico": "Máster",
                            "universidad_codigo": "001",
                            "universidad_nombre": "Universidad de Prueba",
                            "web_fuente_directa_url": shared_url,
                            "origen_fuente": "web_oficial_universidad",
                            "plan_estudios": {
                                "elementos_curriculares": [
                                    {"nombre_elemento": "Materia", "creditos_ects": 6}
                                ]
                            },
                        },
                        handle,
                    )

            fase1_parte2_web_crawler.propagate_interuniversity_and_shared_boe_plans(directory)

            for index in (1, 2):
                path = os.path.join(directory, "001", f"RECORD{index}.json")
                with open(path, encoding="utf-8") as handle:
                    after = json.load(handle)
                self.assertIsNone(after.get("web_fuente_directa_url"))
                self.assertTrue(after.get("fuentes_rechazadas"))
                self.assertIsInstance(after.get("plan_estudios"), dict)

    def test_01f_part2_degree_limit_prioritizes_pending_records(self):
        universities = [{"codigo": "001", "nombre": "Universidad de Prueba", "web": "https://uni.example"}]
        degrees = [
            {"codigo_estudio": "DONE", "titulo": "Grado Resuelto", "nivel_academico": "Grado"},
            {"codigo_estudio": "PENDING", "titulo": "Grado Pendiente", "nivel_academico": "Grado"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            universities_path = os.path.join(directory, "universidades.json")
            titles_path = os.path.join(directory, "titulaciones.json")
            with open(universities_path, "w", encoding="utf-8") as handle:
                json.dump(universities, handle)
            with open(titles_path, "w", encoding="utf-8") as handle:
                json.dump({"001": {"titulaciones_vigentes": degrees}}, handle)

            fake_crawler = fase1_parte2_web_crawler.UniversityWebCrawler.__new__(
                fase1_parte2_web_crawler.UniversityWebCrawler
            )
            fake_crawler.process_university_web = MagicMock(
                return_value={
                    "missing_degrees_count": 1,
                    "resolved_degrees_count": 0,
                    "robots_allowed": True,
                }
            )
            fake_crawler.ledger = MagicMock()
            fake_crawler.checkpoint = MagicMock()

            with patch.object(fase1_parte2_web_crawler, "UNIVERSIDADES_JSON", universities_path), \
                 patch.object(fase1_parte2_web_crawler, "TITULACIONES_JSON", titles_path), \
                 patch.object(fase1_parte2_web_crawler, "UniversityWebCrawler", return_value=fake_crawler), \
                 patch.object(fase1_parte2_web_crawler, "find_plan_filepath", side_effect=lambda _u, code: os.path.join(directory, f"{code}.json")), \
                 patch.object(fase1_parte2_web_crawler, "needs_web_resolution", side_effect=lambda path, force=False: "PENDING" in path), \
                 patch.object(fase1_parte2_web_crawler, "propagate_interuniversity_and_shared_boe_plans", return_value={"total_propagated": 0}):
                result = fase1_parte2_web_crawler.run_phase1_part2(
                    limit_universities=1,
                    limit_degrees=1,
                    max_workers=1,
                )

            self.assertEqual(result["status"], "completed")
            passed_catalog = fake_crawler.process_university_web.call_args.args[1]
            selected = passed_catalog["001"]["titulaciones_vigentes"]
            self.assertEqual([item["codigo_estudio"] for item in selected], ["PENDING"])

    def test_01g_hub_budget_scales_with_pending_cohort(self):
        self.assertEqual(fase1_parte2_web_crawler.adaptive_hub_budget(0, 200), 0)
        self.assertEqual(fase1_parte2_web_crawler.adaptive_hub_budget(1, 200), 1)
        self.assertEqual(fase1_parte2_web_crawler.adaptive_hub_budget(20, 200), 11)
        self.assertEqual(fase1_parte2_web_crawler.adaptive_hub_budget(200, 100), 100)

    def test_http_protocol_fallback_preserves_host_and_path(self):
        self.assertEqual(
            fase1_parte2_web_crawler.http_protocol_fallback_url(
                "https://legacy.example.edu/catalogo"
            ),
            "http://legacy.example.edu/catalogo",
        )
        self.assertEqual(
            fase1_parte2_web_crawler.http_protocol_fallback_url("http://example.edu"),
            "",
        )

    def test_curriculum_url_identity_requires_two_discriminative_terms(self):
        unrelated = BeautifulSoup(
            "<html><head><title>Global Law</title></head>"
            "<body><h1>Global Law</h1><h2>Social Sciences and Law</h2></body></html>",
            "html.parser",
        )
        self.assertFalse(
            fase1_parte2_web_crawler.is_html_page_matching_degree(
                unrelated,
                "Máster Universitario en Antropología Social y Cultural por la "
                "Universidad de Prueba; National University of Example",
                "Universidad de Prueba",
                "https://university.example/international/social-sciences-and-law/global-law",
                allow_curriculum_url_identity=True,
            )
        )

        matching = BeautifulSoup(
            "<html><head><title>Ficha</title></head><body><h1>Ficha</h1></body></html>",
            "html.parser",
        )
        self.assertTrue(
            fase1_parte2_web_crawler.is_html_page_matching_degree(
                matching,
                "Máster Universitario en Antropología Social y Cultural por la "
                "Universidad de Prueba; National University of Example",
                "Universidad de Prueba",
                "https://university.example/master-anthropology-social-cultural",
                allow_curriculum_url_identity=True,
            )
        )

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

    def test_03b_error_logs_are_isolated_by_run(self):
        with tempfile.TemporaryDirectory() as directory:
            first = os.path.join(directory, "runs", "run-a", "errores_crawler.json")
            second = os.path.join(directory, "runs", "run-b", "errores_crawler.json")
            os.makedirs(os.path.dirname(first), exist_ok=True)
            os.makedirs(os.path.dirname(second), exist_ok=True)
            first_logger = error_logger.ErrorLogger(filepath=first)
            second_logger = error_logger.ErrorLogger(filepath=second)
            first_logger.log_error("fase1", "001", "https://a.example", "fallo controlado")
            second_logger.log_error("fase2", "002", "https://b.example", "otro fallo")
            with open(first, encoding="utf-8") as handle:
                first_entries = json.load(handle)
            with open(second, encoding="utf-8") as handle:
                second_entries = json.load(handle)
            self.assertEqual([entry["id_entidad"] for entry in first_entries], ["001"])
            self.assertEqual([entry["id_entidad"] for entry in second_entries], ["002"])

    def test_03c_run_artifact_paths_are_safe_and_isolated(self):
        paths = config.get_run_artifact_paths("run-test-01")
        self.assertIn(os.path.join("runs", "run-test-01"), paths["errors"])
        self.assertNotEqual(paths["errors"], config.ERRORES_JSON)
        with self.assertRaises(ValueError):
            config.get_run_artifact_paths("../")

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

    def test_06b_metrics_record_real_work_of_parts_2_and_4(self):
        tracker = metrics.PerformanceTracker()
        tracker.record_part_result(2, {
            "status": "completed",
            "university_codes_processed": ["101", "102"],
            "missing_degrees": 8,
            "resolved_degrees": 3,
            "propagated_degrees": 2,
            "robots_denied": 1,
        }, 12.5)
        tracker.record_part_result(4, {
            "status": "completed",
            "university_codes_processed": ["101", "102"],
            "plans_inspected": 7,
            "enriched_degrees": 4,
            "guide_subjects_considered": 20,
            "guide_candidate_urls_generated": 40,
            "guide_candidate_urls_pruned": 16,
            "guide_candidate_urls_requested": 24,
            "guide_robots_denied": 2,
        }, 30.0)
        report = tracker.generate_report()
        self.assertEqual(report["operaciones_crawler"]["universidades_inspeccionadas"], 4)
        self.assertEqual(report["operaciones_crawler"]["titulaciones_inspeccionadas"], 18)
        self.assertEqual(report["operaciones_crawler"]["titulaciones_nuevas_o_actualizadas"], 9)
        self.assertEqual(report["operaciones_por_parte"]["parte4"]["guide_candidate_urls_pruned"], 16)
        self.assertEqual(report["duracion_por_parte_seg"]["parte2"], 12.5)

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
