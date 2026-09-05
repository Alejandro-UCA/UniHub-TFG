import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from parsers import spa_engine as spa_crawler

class TestSPAInteractiveTabs(unittest.TestCase):
    def test_render_result_with_json_payloads(self):
        rr = spa_crawler.RenderResult("<html><body>Hello</body></html>", json_payloads=[{"asignaturas": []}])
        self.assertIn("Hello", str(rr))
        self.assertTrue(hasattr(rr, "json_payloads"))
        self.assertEqual(len(rr.json_payloads), 1)

    def test_render_spa_page_unhides_and_captures_json(self):
        crawler = spa_crawler.SPALayoutCrawler(timeout=5)
        browser = MagicMock()
        browser.is_connected.return_value = True
        context = MagicMock()
        page = MagicMock()
        page.content.return_value = "<html><body><details open><summary>Curso 2</summary><div>Asignatura X</div></details></body></html>"
        context.new_page.return_value = page
        browser.new_context.return_value = context

        with patch.object(spa_crawler, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(crawler, "_ensure_browser", return_value=browser), \
             patch.object(crawler._robots_policy, "check", return_value=(True, None)):
            res = crawler.render_spa_page("https://universidad.example/estudios/grado")
            self.assertIn("Asignatura X", str(res))
            self.assertTrue(page.evaluate.called)
            # Verify that page.evaluate contained unhiding logic
            eval_arg = page.evaluate.call_args[0][0]
            self.assertIn("details", eval_arg)
            self.assertIn("collapse", eval_arg)

if __name__ == '__main__':
    unittest.main()
