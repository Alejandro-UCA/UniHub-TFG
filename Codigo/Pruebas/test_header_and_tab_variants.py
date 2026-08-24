import unittest
from bs4 import BeautifulSoup
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Crawler')))
from univ_web_crawler import extract_html_subjects, is_valid_curricular_table
from config import ACADEMIC_SUBPAGE_KEYWORDS, INVALID_METADATA_LABELS



class TestHeaderAndTabVariants(unittest.TestCase):
    """
    Batería de pruebas unitarias para la extracción robusta de tablas curriculares
    con columnas de semestre multilingües y descarte de metadatos administrativos.
    """

    def test_catalan_table_with_semesters_not_skipped(self):
        """Verifica que tablas con '1r semestre' o '2n semestre' extraigan asignaturas sin ser descartadas como cabecera."""
        html = """
        <html>
        <body>
            <table>
                <tr>
                    <th>Assignatura</th>
                    <th>Llengua</th>
                    <th>Tipus</th>
                    <th>Crèdits</th>
                </tr>
                <tr>
                    <td>Economia de l'Empresa</td>
                    <td>1r semestre</td>
                    <td>Formació bàsica</td>
                    <td>6</td>
                </tr>
                <tr>
                    <td>Introducció a l'Economia</td>
                    <td>1r semestre</td>
                    <td>Formació bàsica</td>
                    <td>6</td>
                </tr>
                <tr>
                    <td>Comptabilitat I</td>
                    <td>2n semestre</td>
                    <td>Formació bàsica</td>
                    <td>6</td>
                </tr>
                <tr>
                    <td>Entorn Econòmic Espanyol</td>
                    <td>2n semestre</td>
                    <td>Obligatòria</td>
                    <td>3</td>
                </tr>
            </table>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        elems = extract_html_subjects(soup)
        self.assertEqual(len(elems), 4)
        self.assertEqual(elems[0]["nombre_elemento"], "Economia de l'Empresa")
        self.assertEqual(elems[0]["creditos_ects"], "6")
        self.assertEqual(elems[0]["caracter"], "FB")
        self.assertEqual(elems[3]["nombre_elemento"], "Entorn Econòmic Espanyol")
        self.assertEqual(elems[3]["creditos_ects"], "3")
        self.assertEqual(elems[3]["caracter"], "OB")

    def test_euskera_and_galego_semesters(self):
        """Verifica que tablas en Euskera y Gallego no se descarten erróneamente."""
        html = """
        <html>
        <body>
            <table>
                <tr>
                    <th>Irakasgaia</th>
                    <th>Lauhilekoa</th>
                    <th>Mota</th>
                    <th>Kredituak</th>
                </tr>
                <tr>
                    <td>Programazioaren Oinarriak</td>
                    <td>1. lauhilekoa</td>
                    <td>Oinarrizkoa</td>
                    <td>6</td>
                </tr>
                <tr>
                    <td>Datu-baseak</td>
                    <td>2. lauhilekoa</td>
                    <td>Derrigorrezkoa</td>
                    <td>6</td>
                </tr>
            </table>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        elems = extract_html_subjects(soup)
        self.assertEqual(len(elems), 2)
        self.assertEqual(elems[0]["nombre_elemento"], "Programazioaren Oinarriak")
        self.assertEqual(elems[1]["nombre_elemento"], "Datu-baseak")

    def test_discard_administrative_metadata_labels(self):
        """Verifica que filas de metadatos administrativos (notas de corte, plazas, precios) se descarten."""
        html = """
        <html>
        <body>
            <table>
                <tr><th>Dada</th><th>Valor</th></tr>
                <tr><td>Centre de gestió</td><td>Facultat d'Economia</td></tr>
                <tr><td>Nota de tall</td><td>9.388</td></tr>
                <tr><td>Preu orientatiu per crèdit</td><td>17.69</td></tr>
                <tr><td>Places de nou ingrés</td><td>360</td></tr>
                <tr><td>Durada</td><td>4 anys</td></tr>
                <tr><td>Assignatura Real 1</td><td>6 ECTS</td></tr>
                <tr><td>Assignatura Real 2</td><td>6 ECTS</td></tr>
                <tr><td>Assignatura Real 3</td><td>6 ECTS</td></tr>
            </table>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        elems = extract_html_subjects(soup)
        # Solo deben quedar las 3 asignaturas reales
        names = [e["nombre_elemento"] for e in elems]
        self.assertNotIn("Centre de gestió", names)
        self.assertNotIn("Nota de tall", names)
        self.assertNotIn("Preu orientatiu per crèdit", names)
        self.assertNotIn("Places de nou ingrés", names)
        self.assertEqual(len(elems), 3)

    def test_academic_subpage_keywords_present(self):
        """Verifica que ACADEMIC_SUBPAGE_KEYWORDS esté correctamente configurado en config.py."""
        self.assertTrue(len(ACADEMIC_SUBPAGE_KEYWORDS) >= 5)
        self.assertIn("plan de estudios", ACADEMIC_SUBPAGE_KEYWORDS)
        self.assertIn("pla d'estudis", ACADEMIC_SUBPAGE_KEYWORDS)
        self.assertIn("asignaturas", ACADEMIC_SUBPAGE_KEYWORDS)
        self.assertIn("subjects", ACADEMIC_SUBPAGE_KEYWORDS)


if __name__ == "__main__":
    unittest.main()

