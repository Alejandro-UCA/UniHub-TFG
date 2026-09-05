import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from bs4 import BeautifulSoup
from curriculum_recovery import (
    extract_hydration_payload,
    extract_curriculum_from_json_tree,
)
from fase1_parte2_web_crawler import extract_html_subjects


class TestHydrationCurriculumRecovery(unittest.TestCase):
    def test_nextjs_hydration_extraction(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Grado en Informatica</title></head>
        <body>
            <div id="__next">Cargando contenido...</div>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "pageProps": {
                        "titulacion": {
                            "nombre": "Grado en Ingeniería Informática",
                            "asignaturas": [
                                {
                                    "codigo": "INF101",
                                    "nombre": "Fundamentos de Programación",
                                    "creditos": 6,
                                    "curso": "1",
                                    "cuatrimestre": "1C",
                                    "tipo": "Formación Básica",
                                    "url": "https://uni.es/guias/INF101"
                                },
                                {
                                    "codigo": "INF102",
                                    "nombre": "Estructuras de Datos y Algoritmos",
                                    "creditos": "6.0",
                                    "curso": "2",
                                    "cuatrimestre": "1C",
                                    "tipo": "Obligatoria"
                                },
                                {
                                    "codigo": "INF103",
                                    "nombre": "Trabajo Fin de Grado",
                                    "creditos": 12,
                                    "curso": "4",
                                    "cuatrimestre": "2C",
                                    "tipo": "TFG"
                                },
                                {
                                    "codigo": "META01",
                                    "nombre": "Política de Cookies y Privacidad",
                                    "creditos": 6
                                }
                            ]
                        }
                    }
                }
            }
            </script>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        payloads = extract_hydration_payload(soup, raw_html=html)
        self.assertEqual(len(payloads), 1)

        subjects = extract_curriculum_from_json_tree(payloads, source_url="https://uni.es/grado")
        self.assertEqual(len(subjects), 3)

        s1 = next(s for s in subjects if s["nombre_elemento"] == "Fundamentos de Programación")
        self.assertEqual(s1["creditos_ects"], "6")
        self.assertEqual(s1["codigo_asignatura"], "INF101")
        self.assertEqual(s1["curso"], "1")
        self.assertEqual(s1["cuatrimestre"], "1C")
        self.assertEqual(s1["caracter"], "FB")
        self.assertEqual(s1["url_guia_docente"], "https://uni.es/guias/INF101")

        s3 = next(s for s in subjects if s["nombre_elemento"] == "Trabajo Fin de Grado")
        self.assertEqual(s3["creditos_ects"], "12")
        self.assertEqual(s3["caracter"], "TFM")

    def test_nuxt_hydration_extraction(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Master en Ciberseguridad</title></head>
        <body>
            <script>
            window.__NUXT__ = {
                "layout": "default",
                "data": [
                    {
                        "planEstudios": [
                            {"subject": "Criptografía Avanzada", "ects": 6, "nature": "Obligatoria"},
                            {"subject": "Auditoría de Redes", "ects": "4.5", "nature": "Optativa"}
                        ]
                    }
                ]
            };
            </script>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        payloads = extract_hydration_payload(soup, raw_html=html)
        self.assertEqual(len(payloads), 1)

        subjects = extract_curriculum_from_json_tree(payloads, source_url="https://uni.es/master")
        self.assertEqual(len(subjects), 2)
        names = [s["nombre_elemento"] for s in subjects]
        self.assertIn("Criptografía Avanzada", names)
        self.assertIn("Auditoría de Redes", names)

    def test_extract_html_subjects_with_hydration(self):
        html = """
        <div>
            <h1>Grado en Matemáticas</h1>
            <p>El plan de estudios se detalla a continuación:</p>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "materias": [
                        {"nombre": "Álgebra Lineal", "creditos": 6, "tipo": "FB", "curso": "1"},
                        {"nombre": "Cálculo Infinitesimal", "creditos": 6, "tipo": "FB", "curso": "1"}
                    ]
                }
            }
            </script>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        subjects = extract_html_subjects(soup, base_url="https://uni.es/mates", raw_html=html)
        self.assertEqual(len(subjects), 2)
        self.assertEqual(subjects[0]["nombre_elemento"], "Álgebra Lineal")
        self.assertEqual(subjects[0]["creditos_ects"], "6")


if __name__ == "__main__":
    unittest.main()
