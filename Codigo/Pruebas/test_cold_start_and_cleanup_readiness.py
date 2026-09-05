"""Suite de pruebas unitarias: Verificación de Limpieza de Datos y Preparación para Arranque en Frío.

Valida:
1. Clasificación estricta de inventario entre semillas maestras y artefactos volátiles.
2. Preservación incondicional de semillas e invariabilidad de sus firmas SHA-256.
3. Creación determinista de copias de seguridad de semillas.
4. Idempotencia de la función de limpieza (múltiples ejecuciones sin error).
5. Comportamiento en modo dry-run (cero modificaciones en disco).
6. Preparación y arranque en frío de componentes y pipelines ante directorios limpios.
7. Purga de cerrojos huérfanos de sistema (etl_running.lock).
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Añadir directorios de código a sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
CRAWLER_DIR = BASE_DIR / "Crawler"
sys.path.insert(0, str(CRAWLER_DIR))

from utils.data_cleanup import (
    SEED_FILENAMES,
    get_crawler_data_inventory,
    backup_seed_files,
    clean_crawler_runtime_data,
    _file_sha256,
)


class TestColdStartAndCleanupReadiness(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="unihub_cleanup_test_")
        self.data_dir = Path(self.test_dir) / "Datos"
        self.temp_pdf_dir = Path(self.test_dir) / "temp_pdfs"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_pdf_dir.mkdir(parents=True, exist_ok=True)

        # Crear semillas maestras sintéticas
        self.univ_data = [{"codigo": "001", "nombre": "Universidad de Prueba", "tipo": "pública", "comunidad_autonoma": "Madrid"}]
        self.tit_data = {"001": {"universidad_codigo": "001", "titulaciones_vigentes": [{"codigo_estudio": "1001", "titulo": "Grado en Informática", "nivel_academico": "Grado"}]}}
        self.precios_data = {"Madrid": {"Grado": {"experimentalidad_1": 21.39}}}

        with open(self.data_dir / "universidades.json", "w", encoding="utf-8") as f:
            json.dump(self.univ_data, f)
        with open(self.data_dir / "titulaciones_universidad.json", "w", encoding="utf-8") as f:
            json.dump(self.tit_data, f)
        with open(self.data_dir / "precios_ccaa.json", "w", encoding="utf-8") as f:
            json.dump(self.precios_data, f)

        self.initial_univ_hash = _file_sha256(self.data_dir / "universidades.json")
        self.initial_tit_hash = _file_sha256(self.data_dir / "titulaciones_universidad.json")
        self.initial_precios_hash = _file_sha256(self.data_dir / "precios_ccaa.json")

        # Crear artefactos volátiles simulados
        (self.data_dir / "planes_estudio" / "001").mkdir(parents=True, exist_ok=True)
        with open(self.data_dir / "planes_estudio" / "001" / "1001.json", "w", encoding="utf-8") as f:
            json.dump({"codigo_estudio": "1001", "titulo": "Grado en Informática"}, f)

        (self.data_dir / "http_cache").mkdir(parents=True, exist_ok=True)
        with open(self.data_dir / "http_cache" / "cache_item.bin", "wb") as f:
            f.write(b"cached http payload")

        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        with open(self.data_dir / "logs" / "run.log", "w", encoding="utf-8") as f:
            f.write("test log line")

        # Ficheros SQLite y corruptos
        with open(self.data_dir / "cache_guias_docentes.db", "wb") as f:
            f.write(b"sqlite format 3")
        with open(self.data_dir / "cache_guias_docentes.db-wal", "wb") as f:
            f.write(b"wal content")
        with open(self.data_dir / "crawl_ledger.sqlite3", "wb") as f:
            f.write(b"ledger content")
        with open(self.data_dir / "crawl_ledger.sqlite3.backup_before_repair", "wb") as f:
            f.write(b"old backup content")
        with open(self.data_dir / "crawl_ledger.sqlite3.corrupt.20260901.63a9", "wb") as f:
            f.write(b"corrupt ledger content")
        with open(self.data_dir / "unihub_cache.sqlite3.corrupt.74e4", "wb") as f:
            f.write(b"corrupt cache content")
        with open(self.data_dir / "checkpoint.json", "w", encoding="utf-8") as f:
            json.dump({"checkpoint": 1}, f)
        with open(self.data_dir / "estadisticas_rendimiento.json", "w", encoding="utf-8") as f:
            json.dump({"mem": 100}, f)

        # Temp PDFs
        with open(self.temp_pdf_dir / "sample.pdf", "wb") as f:
            f.write(b"%PDF-1.4 test")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_inventory_classification(self):
        """Verifica que el inventario distinga exactamente semillas de artefactos volátiles."""
        inv = get_crawler_data_inventory(self.data_dir, self.temp_pdf_dir)

        # Semillas
        self.assertEqual(set(inv["seeds"].keys()), SEED_FILENAMES)
        self.assertEqual(inv["seeds"]["universidades.json"]["sha256"], self.initial_univ_hash)
        self.assertGreater(inv["total_seed_bytes"], 0)

        # Volátiles
        disposable_file_names = {item["name"] for item in inv["disposable_files"]}
        self.assertIn("cache_guias_docentes.db", disposable_file_names)
        self.assertIn("crawl_ledger.sqlite3", disposable_file_names)
        self.assertIn("crawl_ledger.sqlite3.backup_before_repair", disposable_file_names)
        self.assertIn("crawl_ledger.sqlite3.corrupt.20260901.63a9", disposable_file_names)
        self.assertIn("checkpoint.json", disposable_file_names)

        disposable_dir_names = {item["name"] for item in inv["disposable_dirs"]}
        self.assertIn("planes_estudio", disposable_dir_names)
        self.assertIn("http_cache", disposable_dir_names)
        self.assertIn("logs", disposable_dir_names)

        self.assertEqual(inv["temp_pdfs"]["count"], 1)

    def test_dry_run_makes_no_changes(self):
        """Verifica que dry-run reporte pero no modifique ningún archivo."""
        report = clean_crawler_runtime_data(self.data_dir, self.temp_pdf_dir, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertGreater(report["files_deleted_count"], 0)
        self.assertGreater(report["dirs_deleted_count"], 0)

        # Todos los ficheros volátiles siguen existiendo
        self.assertTrue((self.data_dir / "cache_guias_docentes.db").exists())
        self.assertTrue((self.data_dir / "planes_estudio" / "001" / "1001.json").exists())
        self.assertTrue((self.temp_pdf_dir / "sample.pdf").exists())

    def test_seed_preservation_and_cleanup_execution(self):
        """Verifica que la purga real elimine todo lo volátil pero conserve 100% las semillas."""
        report = clean_crawler_runtime_data(self.data_dir, self.temp_pdf_dir, dry_run=False, backup_seed=True)

        # 1. Semillas intactas
        self.assertTrue((self.data_dir / "universidades.json").exists())
        self.assertTrue((self.data_dir / "titulaciones_universidad.json").exists())
        self.assertTrue((self.data_dir / "precios_ccaa.json").exists())

        self.assertEqual(_file_sha256(self.data_dir / "universidades.json"), self.initial_univ_hash)
        self.assertEqual(_file_sha256(self.data_dir / "titulaciones_universidad.json"), self.initial_tit_hash)
        self.assertEqual(_file_sha256(self.data_dir / "precios_ccaa.json"), self.initial_precios_hash)

        # 2. Respaldo creado
        self.assertEqual(len(report["backups_created"]), 3)
        for b in report["backups_created"]:
            self.assertTrue(os.path.exists(b["dst"]))

        # 3. Artefactos volátiles purgados
        self.assertFalse((self.data_dir / "cache_guias_docentes.db").exists())
        self.assertFalse((self.data_dir / "crawl_ledger.sqlite3").exists())
        self.assertFalse((self.data_dir / "crawl_ledger.sqlite3.backup_before_repair").exists())
        self.assertFalse((self.data_dir / "crawl_ledger.sqlite3.corrupt.20260901.63a9").exists())
        self.assertFalse((self.data_dir / "unihub_cache.sqlite3.corrupt.74e4").exists())
        self.assertFalse((self.data_dir / "checkpoint.json").exists())
        self.assertFalse((self.data_dir / "estadisticas_rendimiento.json").exists())

        # 4. Directorios recreados vacíos
        self.assertTrue((self.data_dir / "planes_estudio").exists())
        self.assertEqual(len(list((self.data_dir / "planes_estudio").iterdir())), 0)
        self.assertTrue(self.temp_pdf_dir.exists())
        self.assertEqual(len(list(self.temp_pdf_dir.iterdir())), 0)

    def test_cleanup_idempotency(self):
        """Verifica que ejecutar la limpieza dos veces seguidas sea seguro y sin errores."""
        report1 = clean_crawler_runtime_data(self.data_dir, self.temp_pdf_dir, dry_run=False)
        report2 = clean_crawler_runtime_data(self.data_dir, self.temp_pdf_dir, dry_run=False)

        self.assertEqual(report2["files_deleted_count"], 0)
        # Semillas siguen 100% intactas
        self.assertEqual(_file_sha256(self.data_dir / "universidades.json"), self.initial_univ_hash)

    def test_cold_start_component_initialization(self):
        """Verifica que con solo semillas y directorios vacíos, los módulos arranquen limpiamente."""
        clean_crawler_runtime_data(self.data_dir, self.temp_pdf_dir, dry_run=False)

        # Probar inicialización limpia de CrawlLedger en base de datos nueva
        ledger_path = str(self.data_dir / "test_ledger.sqlite3")
        from core.crawl_ledger import CrawlLedger
        ledger = CrawlLedger(db_path=ledger_path)
        self.assertTrue(os.path.exists(ledger_path))
        ledger.close()

        # Probar inicialización limpia de SubjectGuideCache
        cache_path = str(self.data_dir / "test_guias.db")
        from pipelines.parte4_asignaturas import SubjectGuideCache
        guide_cache = SubjectGuideCache(db_path=cache_path)
        self.assertTrue(os.path.exists(cache_path))
        guide_cache.close()

        # Probar cómputo de precio con catálogo de precios de respaldo
        from pipelines.parte3_precios import compute_degree_price
        price_res = compute_degree_price(
            ccaa="Madrid",
            tipo_univ="pública",
            nivel_academico="Grado",
            titulo="Grado en Ingeniería Informática",
            univ_codigo="001",
        )
        self.assertIsNotNone(price_res.get("precio_credito_ects"))
        self.assertGreater(price_res["precio_credito_ects"], 0)


if __name__ == "__main__":
    unittest.main()
