import os
import sys
import unittest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers.schema_org import extract_schema_org_curriculum


class TestSchemaOrgCurriculum(unittest.TestCase):
    def test_extract_basic_course_json_ld(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Course",
                "name": "Estructuras de Datos y Algoritmos",
                "courseCode": "EDA101",
                "numberOfCredits": 6,
                "courseType": "Obligatoria",
                "academicTerm": "1º curso, 2º cuatrimestre",
                "url": "/guias/eda101.pdf"
            }
            </script>
        </head>
        <body>
            <h1>Grado en Ingeniería Informática</h1>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = extract_schema_org_curriculum(soup, base_url="https://etsii.example.edu/plan/")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["nombre_elemento"], "Estructuras de Datos y Algoritmos")
        self.assertEqual(item["codigo_asignatura"], "EDA101")
        self.assertEqual(item["creditos_ects"], "6")
        self.assertEqual(item["caracter"], "OB")
        self.assertEqual(item["curso"], "1")
        self.assertEqual(item["cuatrimestre"], "2C")
        self.assertEqual(item["url_guia_docente"], "https://etsii.example.edu/guias/eda101.pdf")

    def test_extract_graph_structure_and_multiple_courses(self):
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "EducationalOccupationalProgram",
                        "name": "Grado en Matemáticas",
                        "hasCourse": [
                            {
                                "@type": "Course",
                                "name": "Álgebra Lineal",
                                "courseCode": "ALG01",
                                "numberOfCredits": {"@type": "QuantitativeValue", "value": 9},
                                "courseType": "Formación Básica",
                                "academicTerm": "Primer Curso - Primer Semestre",
                                "url": "https://mat.example.edu/guias/alg01.pdf"
                            },
                            {
                                "@type": "Course",
                                "name": "Geometría Diferencial",
                                "courseCode": "GEO02",
                                "numberOfCredits": "6.0",
                                "courseType": "Optativa",
                                "academicTerm": "4º curso, 1C",
                                "url": "https://mat.example.edu/guias/geo02.pdf"
                            }
                        ]
                    }
                ]
            }
            </script>
        </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = extract_schema_org_curriculum(soup, base_url="https://mat.example.edu")
        self.assertEqual(len(items), 2)
        names = [it["nombre_elemento"] for it in items]
        self.assertIn("Álgebra Lineal", names)
        self.assertIn("Geometría Diferencial", names)

        alg = next(it for it in items if it["nombre_elemento"] == "Álgebra Lineal")
        self.assertEqual(alg["codigo_asignatura"], "ALG01")
        self.assertEqual(alg["creditos_ects"], "9")
        self.assertEqual(alg["caracter"], "FB")
        self.assertEqual(alg["curso"], "1")
        self.assertEqual(alg["cuatrimestre"], "1C")

        geo = next(it for it in items if it["nombre_elemento"] == "Geometría Diferencial")
        self.assertEqual(geo["codigo_asignatura"], "GEO02")
        self.assertEqual(geo["creditos_ects"], "6")
        self.assertEqual(geo["caracter"], "OP")
        self.assertEqual(geo["curso"], "4")
        self.assertEqual(geo["cuatrimestre"], "1C")

    def test_spurious_administrative_filtering(self):
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            [
                {
                    "@type": "Course",
                    "name": "Matrícula y Tasas Administrativas",
                    "numberOfCredits": 0
                },
                {
                    "@type": "Course",
                    "name": "Física Cuántica I",
                    "courseCode": "FIS301",
                    "numberOfCredits": 6,
                    "courseType": "Obligatoria"
                }
            ]
            </script>
        </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = extract_schema_org_curriculum(soup)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["nombre_elemento"], "Física Cuántica I")


if __name__ == "__main__":
    unittest.main()
