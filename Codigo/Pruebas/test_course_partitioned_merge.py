import os
import sys
import unittest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from extractors.curriculum_recovery import (
    discover_course_partitioned_subpages,
    merge_curriculum_elements,
)


class TestCoursePartitionedMerge(unittest.TestCase):
    def test_discover_course_partitioned_subpages(self):
        html = """
        <html>
        <body>
            <div class="tabs-cursos">
                <a href="/estudios/grado-teleco/primer-curso">Primer Curso</a>
                <a href="/estudios/grado-teleco/segundo-curso">Segundo Curso</a>
                <a href="/estudios/grado-teleco/tercer-curso">Tercer Curso</a>
                <a href="/estudios/grado-teleco/cuarto-curso">Cuarto Curso</a>
                <!-- Enlaces no pertinentes que deben ser ignorados -->
                <a href="https://externo.com/1-curso">Externo</a>
                <a href="#primer-curso">Ancla</a>
                <a href="mailto:info@teleco.example.edu">Contacto</a>
            </div>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        base_url = "https://teleco.example.edu/estudios/grado-teleco/plan"
        subpages = discover_course_partitioned_subpages(soup, base_url)
        
        self.assertEqual(len(subpages), 4)
        urls = [item[0] for item in subpages]
        labels = [item[2] for item in subpages]

        self.assertEqual(labels, ["1º", "2º", "3º", "4º"])
        self.assertEqual(urls[0], "https://teleco.example.edu/estudios/grado-teleco/primer-curso")
        self.assertEqual(urls[1], "https://teleco.example.edu/estudios/grado-teleco/segundo-curso")
        self.assertEqual(urls[2], "https://teleco.example.edu/estudios/grado-teleco/tercer-curso")
        self.assertEqual(urls[3], "https://teleco.example.edu/estudios/grado-teleco/cuarto-curso")

    def test_discover_with_query_params(self):
        html = """
        <html>
        <body>
            <ul class="nav">
                <li><a href="?curso=1">1º Curso</a></li>
                <li><a href="?curso=2">2º Curso</a></li>
                <li><a href="?curso=3">3º Curso</a></li>
                <li><a href="?curso=4">4º Curso</a></li>
            </ul>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        base_url = "https://inf.example.edu/plan-estudios"
        subpages = discover_course_partitioned_subpages(soup, base_url)
        self.assertEqual(len(subpages), 4)
        labels = [item[2] for item in subpages]
        self.assertEqual(labels, ["1º", "2º", "3º", "4º"])
        self.assertTrue(all("?curso=" in item[0] for item in subpages))

    def test_merge_curriculum_elements_across_partitions(self):
        course1_subjects = [
            {"nombre_elemento": "Cálculo I", "creditos_ects": "6", "curso": "1º"},
            {"nombre_elemento": "Álgebra Lineal", "creditos_ects": "6", "curso": "1º"},
        ]
        course2_subjects = [
            {"nombre_elemento": "Ecuaciones Diferenciales", "creditos_ects": "6", "curso": "2º"},
            {"nombre_elemento": "Cálculo I", "creditos_ects": "6", "curso": "1º"},  # Duplicado
        ]

        merged = merge_curriculum_elements(course1_subjects, course2_subjects)
        self.assertEqual(len(merged), 3)
        names = [s["nombre_elemento"] for s in merged]
        self.assertEqual(names, ["Cálculo I", "Álgebra Lineal", "Ecuaciones Diferenciales"])


if __name__ == "__main__":
    unittest.main()
