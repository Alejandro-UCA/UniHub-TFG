import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from quality.parser_regression import evaluate_corpus


class TestParserRegression(unittest.TestCase):
    def test_local_corpus_scores_declared_fields_and_minimums(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "guide.html"), "w", encoding="utf-8") as handle:
                handle.write("""
                <html><head><meta property="og:title" content="Minería de Datos" /></head><body>
                  <table><tr><th>Código</th><td>AB1234</td></tr><tr><th>ECTS</th><td>6</td></tr></table>
                  <h2>Temario</h2><ul><li>Introducción</li><li>Modelos predictivos</li></ul>
                  <h2>Resultados de aprendizaje</h2><ul><li>RA1 - Aplicar modelos de datos</li></ul>
                </body></html>
                """)
            corpus_path = os.path.join(directory, "corpus.json")
            with open(corpus_path, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "cases": [{
                    "name": "generic-html",
                    "content": "guide.html",
                    "url": "https://uni.example/guide/ab1234",
                    "expect": {
                        "nombre_asignatura": "Minería de Datos",
                        "codigo_asignatura": "AB1234",
                        "creditos.total_ects": 6,
                        "temario_min": 2,
                        "resultados_aprendizaje_min": 1,
                    },
                }]}, handle)

            report = evaluate_corpus(corpus_path)

            self.assertEqual(report["cases"], 1)
            self.assertEqual(report["passed"], 1)
            self.assertEqual(report["failed"], 0)
            self.assertEqual(report["average_score"], 1.0)

    def test_corpus_rejects_content_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            corpus_path = os.path.join(directory, "corpus.json")
            with open(corpus_path, "w", encoding="utf-8") as handle:
                json.dump([{"name": "escape", "content": "..\\outside.html", "expect": {}}], handle)

            report = evaluate_corpus(corpus_path)

            self.assertEqual(report["failed"], 1)
            self.assertIn("escapes corpus", report["results"][0]["error"])


if __name__ == "__main__":
    unittest.main()
