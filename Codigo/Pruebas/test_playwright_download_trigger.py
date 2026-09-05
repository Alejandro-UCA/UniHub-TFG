import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append('d:/Proyecto/Codigo/Crawler')
from parsers.spa_engine import RenderResult, SPALayoutCrawler

class TestPlaywrightDownloadTriggerPatternA(unittest.TestCase):
    def test_render_result_str_subclass_compatibility(self):
        """Verifica que RenderResult se comporta 100% como un string transparente en código legacy."""
        html_str = "<html><body><h1>Test Title</h1></body></html>"
        res = RenderResult(html_str)
        self.assertEqual(str(res), html_str)
        self.assertTrue("Test Title" in res)
        self.assertFalse(res.is_download)
        self.assertEqual(res.content_bytes, b"")

    def test_render_result_binary_download_metadata(self):
        """Verifica el encapsulamiento de binarios interceptados bajo el Patrón A."""
        fake_pdf = b"%PDF-1.4 Fake PDF Content with curricular tables"
        res = RenderResult("", is_download=True, content_bytes=fake_pdf, filename="guia_docente.pdf")
        self.assertTrue(res.is_download)
        self.assertEqual(res.filename, "guia_docente.pdf")
        self.assertTrue(res.content_bytes.startswith(b"%PDF-"))
        self.assertEqual(len(res), 0)

if __name__ == '__main__':
    unittest.main()
