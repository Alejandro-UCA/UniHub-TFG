import unittest
import os
import sys
import tempfile
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from asignaturas_crawler import (
    parse_uca_subject_guide,
    parse_generic_eees_subject_guide,
    parse_subject_guide,
    SubjectGuideCache
)

SAMPLE_UCA_HTML = """
<!DOCTYPE html>
<html>
<head><title>Programa Docente</title></head>
<body>
    <h2>&lt; 21714009 | CÁLCULO &gt;</h2>
    <div class="info-asignatura">
        Departamento: 010 | Matemáticas | Área: 020 | Análisis Matemático | Idioma: Castellano |
        Créd. Teoría: 4,00 | Créd. Prácticas: 2,00 | Créd. ECTS: 6,00
    </div>

    <table id="temario">
        <tbody>
            <tr>
                <td>1</td>
                <td>
                    Bloque I: Cálculo Diferencial en una Variable
                    Tema 1. Números reales y funciones
                    Tema 2. Límites y continuidad
                    Tema 3. Derivabilidad y aplicaciones
                </td>
            </tr>
            <tr>
                <td>2</td>
                <td>
                    Bloque II: Cálculo Integral
                    Tema 4. Integrales inmediatas y métodos de integración
                    Tema 5. Teorema Fundamental del Cálculo y aplicaciones
                </td>
            </tr>
        </tbody>
    </table>

    <table id="procedimientos_evaluacion_nuevo">
        <tbody>
            <tr>
                <td>1</td>
                <td>Examen Parcial de Teoría y Problemas</td>
                <td>Pruebas escritas individuales</td>
                <td>40%</td>
            </tr>
            <tr>
                <td>2</td>
                <td>Prácticas de Ordenador / Laboratorio</td>
                <td>Entrega de guiones en Matlab/Python</td>
                <td>20%</td>
            </tr>
            <tr>
                <td>3</td>
                <td>Examen Final Oficial</td>
                <td>Prueba escrita global</td>
                <td>40%</td>
            </tr>
        </tbody>
    </table>

    <input type="hidden" name="criterios_evaluacion" value="Para superar la asignatura se exige una calificación mínima de 4.0 sobre 10 en la prueba final escrita. El uso fraudulento de herramientas de IA generativa está prohibido." />

    <table id="profesorado">
        <tbody>
            <tr>
                <td>García</td>
                <td>López</td>
                <td>Juan</td>
                <td>Profesor Titular</td>
                <td><i class="fa fa-star text-primary"></i></td>
            </tr>
            <tr>
                <td>Martínez</td>
                <td>Ruiz</td>
                <td>Elena</td>
                <td>Profesora Asociada</td>
                <td></td>
            </tr>
        </tbody>
    </table>
</body>
</html>
"""

SAMPLE_GENERIC_EEES_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h1>Estructura de Dades i Algorismes</h1>
    <h2>Continguts / Temario</h2>
    <ul>
        <li>Tema 1. Anàlisi de complexitat asimptòtica</li>
        <li>Tema 2. Arbres binaris de cerca i AVL</li>
        <li>Tema 3. Grafs i recorreguts BFS/DFS</li>
    </ul>

    <h2>Avaluació</h2>
    <p>Avaluació continuada: 40% entregues de pràctiques i 60% examen final.</p>

    <h2>Equip Docent</h2>
    <ul>
        <li>Dr. Jordi Gómez</li>
        <li>Dra. Montserrat Valls</li>
    </ul>

    <h2>Bibliografia</h2>
    <ul>
        <li>Cormen, T. H. - Introduction to Algorithms (3rd ed.)</li>
        <li>Sedgewick, R. - Algorithms in C++</li>
    </ul>
</body>
</html>
"""


class TestSubjectGuideCrawler(unittest.TestCase):

    def test_parse_uca_subject_guide(self):
        soup = BeautifulSoup(SAMPLE_UCA_HTML, "html.parser")
        res = parse_uca_subject_guide(soup, "https://asignaturas.uca.es/2025-26/21714009")

        self.assertEqual(res["codigo_asignatura"], "21714009")
        self.assertEqual(res["nombre_asignatura"], "CÁLCULO")
        self.assertEqual(res["departamento"], "Matemáticas")
        self.assertEqual(res["area_conocimiento"], "Análisis Matemático")
        self.assertEqual(res["idioma"], "Castellano")
        self.assertEqual(res["creditos"]["teoria"], 4.0)
        self.assertEqual(res["creditos"]["practicas"], 2.0)
        self.assertEqual(res["creditos"]["total_ects"], 6.0)

        # Temario
        self.assertEqual(len(res["temario"]), 2)
        self.assertIn("Bloque I", res["temario"][0]["titulo"])
        self.assertEqual(len(res["temario"][0]["contenidos"]), 3)

        # Sistema de evaluación
        self.assertEqual(len(res["sistema_evaluacion"]), 3)
        self.assertEqual(res["sistema_evaluacion"][0]["ponderacion_porcentaje"], 40.0)
        self.assertEqual(res["sistema_evaluacion"][1]["ponderacion_porcentaje"], 20.0)

        # Profesorado
        self.assertEqual(len(res["profesorado"]), 2)
        self.assertTrue(res["profesorado"][0]["coordinador"])
        self.assertFalse(res["profesorado"][1]["coordinador"])
        self.assertIn("Juan", res["profesorado"][0]["nombre_completo"])

    def test_parse_generic_eees_guide(self):
        soup = BeautifulSoup(SAMPLE_GENERIC_EEES_HTML, "html.parser")
        res = parse_generic_eees_subject_guide(soup, "https://fib.upc.edu/eda")

        self.assertEqual(res["nombre_asignatura"], "Estructura de Dades i Algorismes")
        self.assertEqual(len(res["temario"]), 3)
        self.assertIn("Tema 1. Anàlisi de complexitat", res["temario"][0]["titulo"])
        self.assertIn("Avaluació continuada", res["criterios_evaluacion"])
        self.assertEqual(len(res["profesorado"]), 2)
        self.assertEqual(len(res["bibliografia"]), 2)

    def test_subject_guide_cache_deduplication(self):
        tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = tmp_db.name
        tmp_db.close()

        try:
            cache = SubjectGuideCache(db_path=db_path)

            guide_data = {
                "codigo": "21714009",
                "nombre": "Cálculo",
                "temario": ["Tema 1", "Tema 2"]
            }

            url = "https://asignaturas.uca.es/2025-26/21714009"
            cache.set(url=url, data=guide_data, u_code="025", asig_code="21714009", nombre="Cálculo")

            # Recuperar de la base de datos WAL
            cached = cache.get(url)
            self.assertIsNotNone(cached)
            self.assertEqual(cached["codigo"], "21714009")
            self.assertEqual(len(cached["temario"]), 2)

            # URL no existente devuelve None
            self.assertIsNone(cache.get("https://asignaturas.uca.es/2025-26/99999999"))
        finally:
            try:
                if os.path.exists(db_path):
                    os.remove(db_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
