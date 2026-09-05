import io
import os
import tempfile
import json
import unittest
from unittest.mock import MagicMock, patch
from pypdf import PdfWriter

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from boe_pdf_parser import parse_boe_pdf
import degree_persistence
from degree_persistence import save_degree_payload
from crawl_ledger import CrawlLedger
from downloader import RUCTDownloader


class TestPdfVersionChangeDetection(unittest.TestCase):
    """
    Verifica que el sistema detecta de forma determinista y precisa cuándo un PDF
    en la misma URL y ruta ha sido modificado o actualizado (Versión 2 / Modificación).
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_ledger.sqlite3")
        self.ledger = CrawlLedger(db_path=self.db_path)
        self.history_dir = os.path.join(self.temp_dir.name, "history")

        # La persistencia mantiene una copia particionada para producción. En
        # una prueba, ambas rutas deben permanecer dentro del temporal: de lo
        # contrario, un código de fixture puede coincidir con uno real y
        # contaminar el conjunto de datos del piloto.
        self._persistence_patches = [
            patch.object(
                degree_persistence,
                "get_plan_filepath",
                side_effect=lambda u_code, d_code, **_kwargs: os.path.join(
                    self.temp_dir.name,
                    "partitioned",
                    str(u_code or "unknown").zfill(3),
                    f"{d_code}.json",
                ),
            ),
            patch.object(degree_persistence, "DEGREE_HISTORY_DIR", self.history_dir),
        ]
        for active_patch in self._persistence_patches:
            active_patch.start()

    def tearDown(self):
        self.ledger.close()
        for active_patch in reversed(self._persistence_patches):
            active_patch.stop()
        self.temp_dir.cleanup()

    def _create_sample_pdf(self, title: str, extra_text: str = "") -> bytes:
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        writer.add_metadata({"/Title": title, "/Subject": extra_text})
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def test_pdf_sha256_changes_on_version_update(self):
        """Certifica que dos versiones del mismo PDF generan hashes criptográficos distintos."""
        pdf_v1_bytes = self._create_sample_pdf("Grado en Ingenieria Informatica", "Version 2010")
        pdf_v2_bytes = self._create_sample_pdf("Grado en Ingenieria Informatica", "Version 2024 Modificada")

        res_v1 = parse_boe_pdf(pdf_v1_bytes, target_title="Grado en Ingenieria Informatica")
        res_v2 = parse_boe_pdf(pdf_v2_bytes, target_title="Grado en Ingenieria Informatica")

        sha1 = res_v1.get("pdf_sha256")
        sha2 = res_v2.get("pdf_sha256")

        self.assertIsNotNone(sha1)
        self.assertIsNotNone(sha2)
        self.assertNotEqual(sha1, sha2, "El hash SHA-256 debe cambiar cuando el contenido del PDF se actualiza a V2")

    def test_persistence_updates_when_pdf_version_changes(self):
        """Valida que la persistencia reemplaza el plan anterior cuando detecta un PDF V2."""
        u_code = "005"
        d_code = "2500123"
        d_title = "Grado en Biotecnologia"
        target_path = os.path.join(self.temp_dir.name, f"{d_code}.json")

        # Versión 1: 10 asignaturas (60 ECTS)
        curriculum_v1 = {
            "resumen_creditos": {"Formación Básica": 60, "Obligatorias": 120, "Optativas": 60},
            "total_elementos": 10,
            "elementos_curriculares": [
                {"codigo": f"B0{i}", "nombre_elemento": f"Asignatura V1-{i}", "creditos_ects": 6.0, "curso": 1}
                for i in range(10)
            ],
            "pdf_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "idioma_predominante": "es"
        }

        # Guardar V1
        save_degree_payload(
            plan_file=target_path,
            d_code=d_code,
            d_title=d_title,
            u_code=u_code,
            u_name="Universidad de Cadiz",
            nivel_academico="Grado",
            boe_url="https://www.boe.es/boe/dias/2010/05/10/pdfs/BOE-A-2010-12345.pdf",
            boe_fecha="2010-05-10",
            plan_estudios=curriculum_v1,
            origen_fuente="resolucion_boe"
        )

        with open(target_path, "r", encoding="utf-8") as f:
            saved_v1 = json.load(f)

        plan_v1 = saved_v1.get("plan_estudios") or saved_v1.get("candidato_plan_estudios")
        self.assertIsNotNone(plan_v1)
        self.assertEqual(len(plan_v1["elementos_curriculares"]), 10)

        # Versión 2: Modificación en BOE con 12 asignaturas
        curriculum_v2 = {
            "resumen_creditos": {"Formación Básica": 60, "Obligatorias": 120, "Optativas": 60},
            "total_elementos": 12,
            "elementos_curriculares": [
                {"codigo": f"B0{i}", "nombre_elemento": f"Asignatura V2-{i}", "creditos_ects": 6.0, "curso": 1}
                for i in range(12)
            ],
            "pdf_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "idioma_predominante": "es"
        }

        # Guardar V2 sobre la misma ruta
        save_degree_payload(
            plan_file=target_path,
            d_code=d_code,
            d_title=d_title,
            u_code=u_code,
            u_name="Universidad de Cadiz",
            nivel_academico="Grado",
            boe_url="https://www.boe.es/boe/dias/2024/02/15/pdfs/BOE-A-2024-99999.pdf",
            boe_fecha="2024-02-15",
            plan_estudios=curriculum_v2,
            origen_fuente="resolucion_boe",
            existing_data=saved_v1
        )

        with open(target_path, "r", encoding="utf-8") as f:
            saved_v2 = json.load(f)

        # Comprobar que los datos de V2 sobreescribieron a V1 limpiamente
        plan_v2 = saved_v2.get("plan_estudios") or saved_v2.get("candidato_plan_estudios")
        self.assertIsNotNone(plan_v2)
        self.assertEqual(len(plan_v2["elementos_curriculares"]), 12)
        self.assertEqual(plan_v2["elementos_curriculares"][0]["nombre_elemento"], "Asignatura V2-0")
        self.assertEqual(saved_v2["boe_fecha"], "2024-02-15")
        self.assertEqual(saved_v2["boe_url"], "https://www.boe.es/boe/dias/2024/02/15/pdfs/BOE-A-2024-99999.pdf")

    def test_http_cache_and_ledger_invalidation_on_200_update(self):
        """Verifica que el ledger y la caché en disco actualizan el cuerpo y hash cuando el servidor devuelve 200 con nueva versión."""
        downloader = RUCTDownloader(ledger=self.ledger)
        url = "https://www.boe.es/boe/dias/2020/01/01/pdfs/BOE-A-2020-0001.pdf"

        # Registrar intento inicial y descarga V1
        self.ledger.record_attempt(url, phase="fase1_parte1")
        mock_resp_v1 = MagicMock()
        mock_resp_v1.status_code = 200
        mock_resp_v1.headers = {"ETag": '"etag-v1"', "Last-Modified": "Wed, 01 Jan 2020 00:00:00 GMT"}
        mock_resp_v1._unihub_cached = False
        content_v1 = b"%PDF-1.4 Version 1 Content"

        downloader.store_response_content(url, mock_resp_v1, content_v1)
        validators_v1 = self.ledger.validators(url)
        self.assertEqual(validators_v1.get("etag"), '"etag-v1"')

        # Registrar intento de revalidación y nueva versión V2 devuelta por el servidor
        self.ledger.record_attempt(url, phase="fase1_parte1")
        mock_resp_v2 = MagicMock()
        mock_resp_v2.status_code = 200
        mock_resp_v2.headers = {"ETag": '"etag-v2"', "Last-Modified": "Fri, 15 Mar 2024 10:00:00 GMT"}
        mock_resp_v2._unihub_cached = False
        content_v2 = b"%PDF-1.4 Version 2 Updated Content with New Subjects"

        downloader.store_response_content(url, mock_resp_v2, content_v2)
        validators_v2 = self.ledger.validators(url)

        self.assertEqual(validators_v2.get("etag"), '"etag-v2"')
        self.assertEqual(validators_v2.get("last_modified"), "Fri, 15 Mar 2024 10:00:00 GMT")

        # Comprobar que el archivo de caché en disco contiene los bytes de la V2
        cache_file = validators_v2.get("cache_path")
        self.assertIsNotNone(cache_file)
        self.assertTrue(os.path.exists(cache_file))
        with open(cache_file, "rb") as f:
            cached_body = f.read()
        self.assertEqual(cached_body, content_v2)


if __name__ == "__main__":
    unittest.main()
