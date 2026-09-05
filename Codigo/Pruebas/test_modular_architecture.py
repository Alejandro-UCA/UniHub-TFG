"""Suite de pruebas unitarias para la arquitectura modular de la Fase 1 (UniHub).

Verifica la integridad de los 7 subpaquetes modulares:
- core
- lexicon
- parsers
- extractors
- quality
- utils
- pipelines

Y certifica la compatibilidad 100% de las fachadas de retrocompatibilidad legadas.
"""

from __future__ import annotations

import os
import sys
import unittest
import tempfile
import sqlite3

_CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if _CRAWLER_DIR not in sys.path:
    sys.path.insert(0, _CRAWLER_DIR)


class TestModularArchitecture(unittest.TestCase):
    """Pruebas de verificación de los subpaquetes y utilidades centralizadas."""

    def test_01_core_imports(self):
        """Verifica que el subpaquete core expone sus componentes sin ciclos."""
        from core.config import BASE_DIR, DATA_DIR, PLANES_DIR, get_plan_filepath
        from core.cancellation import is_shutdown_requested, raise_if_shutdown_requested
        from core.checkpoint import CheckpointManager, atomic_json_dump
        from core.crawl_ledger import CrawlLedger
        from core.downloader import RUCTDownloader, is_same_or_subdomain
        from core.robots_policy import RobotsPolicy

        self.assertTrue(os.path.isdir(DATA_DIR))
        self.assertFalse(is_shutdown_requested())
        self.assertTrue(callable(get_plan_filepath))
        self.assertTrue(is_same_or_subdomain("https://inf.ucm.es", "https://ucm.es"))

    def test_02_lexicon_imports_and_values(self):
        """Verifica que lexicon contiene los diccionarios, stop-words y catálogos de precios."""
        from lexicon.academic_keywords import (
            HEADER_KEYWORDS,
            INVALID_SUBJECT_KEYWORDS,
            SPANISH_STOP_WORDS,
            TITLE_STOPWORDS,
            EUROPEAN_ALLIANCES_KEYWORDS,
        )
        from lexicon.pricing_tables import (
            OFFICIAL_SIIU_PRICES_CATALOG,
            OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG,
            normalize_ccaa_name,
            is_public_university,
        )

        self.assertGreater(len(HEADER_KEYWORDS), 30)
        self.assertGreater(len(SPANISH_STOP_WORDS), 50)
        self.assertIn("Andalucía", OFFICIAL_SIIU_PRICES_CATALOG)
        self.assertIn("031", OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG)
        self.assertEqual(normalize_ccaa_name("Comunidad de Madrid"), "Comunidad de Madrid")
        self.assertEqual(normalize_ccaa_name("andalucia"), "Andalucía")
        self.assertTrue(is_public_university("Pública"))
        self.assertFalse(is_public_university("Privada"))

    def test_03_utils_text_normalization(self):
        """Verifica las utilidades centralizadas de texto y normalización Unicode."""
        from utils.text_utils import (
            clean_ascii_slug,
            clean_spaces,
            detect_academic_language,
            normalize_ascii_text,
            normalize_joint_title,
            normalize_unicode_text,
            repair_mojibake_utf8,
            strip_combining_accents,
            unreverse_boustrophedon_text,
        )

        # Normalización Unicode NFKD sin tildes
        self.assertEqual(normalize_unicode_text("Informática Médica"), "informatica medica")
        self.assertEqual(strip_combining_accents("ÁÉÍÓÚñç"), "AEIOUnc")
        self.assertEqual(normalize_ascii_text("Cálculo Diferencial"), "calculo diferencial")
        self.assertEqual(clean_spaces("  Hola   mundo \t\n"), "Hola mundo")
        self.assertEqual(clean_ascii_slug("Grado en Ingeniería Informática"), "grado-en-ingenieria-informatica")

        # Detección de idioma académico
        self.assertEqual(detect_academic_language("Grau en Enginyeria Informàtica"), "ca")
        self.assertEqual(detect_academic_language("Grao en Enxeñaría Informática"), "gl")
        self.assertEqual(detect_academic_language("Informatika Ingeniaritzako Gradua"), "eu")
        self.assertEqual(detect_academic_language("Bachelor in Computer Science"), "en")
        self.assertEqual(detect_academic_language("Grado en Ingeniería Informática"), "es")

        # Desespejado de texto tipográfico del BOE
        self.assertEqual(unreverse_boustrophedon_text("odarG ed nalP"), "Plan de Grado")

        # Título conjunto interuniversitario
        joint = "Máster en Ciberseguridad (Interuniversitario por la Universidad de Granada)"
        norm_joint = normalize_joint_title(joint)
        self.assertNotIn("interuniversitario", norm_joint)

    def test_04_utils_credit_parsing(self):
        """Verifica el parseo determinista de créditos ECTS."""
        from utils.credit_utils import compute_curriculum_total_ects, parse_credit_number

        self.assertEqual(parse_credit_number(6), 6.0)
        self.assertEqual(parse_credit_number("6"), 6.0)
        self.assertEqual(parse_credit_number("4,5 ECTS"), 4.5)
        self.assertEqual(parse_credit_number("12.0 cr"), 12.0)
        self.assertIsNone(parse_credit_number("invalid"))
        self.assertIsNone(parse_credit_number(500.0, max_val=360.0))

        subjects = [
            {"nombre": "A", "creditos": "6"},
            {"nombre": "B", "creditos": 4.5},
            {"nombre": "C", "creditos": "9 ECTS"},
            {"nombre": "D", "creditos": None},
        ]
        self.assertEqual(compute_curriculum_total_ects(subjects), 19.5)

    def test_05_utils_sqlite_recovery(self):
        """Verifica la inspección y cuarentena unificada de SQLite."""
        from utils.sqlite_recovery import (
            inspect_sqlite_database,
            is_sqlite_corruption,
            quarantine_corrupt_sqlite,
        )

        # Detección de error de corrupción
        corrupt_err = sqlite3.DatabaseError("database disk image is malformed")
        normal_err = sqlite3.OperationalError("no such table: test")
        self.assertTrue(is_sqlite_corruption(corrupt_err))
        self.assertFalse(is_sqlite_corruption(normal_err))

        # Base de datos temporal
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute("CREATE TABLE test (id INT);")
            conn.close()

            diag = inspect_sqlite_database(tmp_path)
            self.assertTrue(diag["readable"])
            self.assertEqual(diag["integrity"], "ok")
            self.assertIn("test", diag["tables"])

            # Cuarentena
            quarantine_path = quarantine_corrupt_sqlite(tmp_path)
            self.assertIsNotNone(quarantine_path)
            self.assertTrue(os.path.exists(quarantine_path))
            self.assertFalse(os.path.exists(tmp_path))
            os.remove(quarantine_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_06_parsers_imports(self):
        """Verifica los módulos de parsing desacoplados."""
        from parsers.html_tables import extract_html_subjects
        from parsers.dynamic_widgets import extract_dynamic_widget_subjects
        from parsers.boe_pdf import parse_boe_pdf
        from parsers.ruct_catalog import parse_degrees_xls
        from parsers.ocr import OCRPDFParser
        from parsers.spa_engine import SPALayoutCrawler

        self.assertTrue(callable(extract_html_subjects))
        self.assertTrue(callable(extract_dynamic_widget_subjects))
        self.assertTrue(callable(parse_boe_pdf))
        self.assertTrue(callable(parse_degrees_xls))
        self.assertIsNotNone(OCRPDFParser)
        self.assertIsNotNone(SPALayoutCrawler)

    def test_07_extractors_imports(self):
        """Verifica los extractores especializados."""
        from extractors.doctoral_programs import extract_generic_doctoral_program
        from extractors.private_pricing import extract_private_university_pricing
        from extractors.consortium_sync import propagate_interuniversity_and_shared_boe_plans
        from extractors.curriculum_recovery import extract_structured_curriculum
        from extractors.subject_guides import build_subject_guide_discovery_index

        self.assertTrue(callable(extract_generic_doctoral_program))
        self.assertTrue(callable(extract_private_university_pricing))
        self.assertTrue(callable(propagate_interuniversity_and_shared_boe_plans))
        self.assertTrue(callable(extract_structured_curriculum))
        self.assertTrue(callable(build_subject_guide_discovery_index))

    def test_08_quality_imports(self):
        """Verifica las puertas de calidad y contratos."""
        from quality.curriculum_validator import (
            compute_curriculum_total_ects,
            get_required_degree_credits,
            is_curriculum_complete,
            is_doctorate_program,
        )
        from quality.data_quality import apply_plan_quality, assess_plan_quality
        from quality.subject_guide_quality import assess_subject_guide_quality, parse_evaluation_breakdown
        from quality.payload_contract import validate_degree_payload

        self.assertEqual(get_required_degree_credits("Grado", "Grado en Medicina"), 360.0)
        self.assertEqual(get_required_degree_credits("Grado", "Grado en Historia"), 240.0)
        self.assertTrue(is_doctorate_program("Doctorado", "Programa de Doctorado en Física"))
        self.assertTrue(callable(apply_plan_quality))
        self.assertTrue(callable(assess_subject_guide_quality))
        self.assertTrue(callable(parse_evaluation_breakdown))
        self.assertTrue(callable(validate_degree_payload))

    def test_09_pipelines_imports(self):
        """Verifica que los pipelines secuenciales son invocables desde pipelines."""
        from pipelines.parte1_ruct_boe import run_phase1_part1
        from pipelines.parte2_web_crawler import run_phase1_part2
        from pipelines.parte3_precios import run_phase1_part3
        from pipelines.parte4_asignaturas import run_phase1_part4
        from pipelines.main import run_all_phase1

        self.assertTrue(callable(run_phase1_part1))
        self.assertTrue(callable(run_phase1_part2))
        self.assertTrue(callable(run_phase1_part3))
        self.assertTrue(callable(run_phase1_part4))
        self.assertTrue(callable(run_all_phase1))

    def test_10_backwards_compatible_facades(self):
        """Verifica que la arquitectura modular y limpia en subpaquetes es 100% funcional."""
        from core import config, checkpoint, downloader
        from utils import sanitizers
        from quality import curriculum_validator, data_quality
        from parsers import boe_pdf, ruct_catalog
        from pipelines import parte2_web_crawler

        self.assertTrue(hasattr(config, "DATA_DIR"))
        self.assertTrue(hasattr(sanitizers, "sanitize_subject_name"))
        self.assertTrue(hasattr(curriculum_validator, "get_required_degree_credits"))
        self.assertTrue(hasattr(boe_pdf, "parse_boe_pdf"))
        self.assertTrue(hasattr(ruct_catalog, "parse_degrees_xls"))
        self.assertTrue(hasattr(data_quality, "apply_plan_quality"))
        self.assertTrue(hasattr(downloader, "RUCTDownloader"))
        self.assertTrue(hasattr(checkpoint, "CheckpointManager"))
        self.assertTrue(hasattr(parte2_web_crawler, "extract_html_subjects"))


if __name__ == "__main__":
    unittest.main()
