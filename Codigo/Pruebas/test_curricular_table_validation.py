import unittest
from bs4 import BeautifulSoup
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from univ_web_crawler import is_valid_curricular_table, extract_html_subjects

class TestCurricularTableValidation(unittest.TestCase):
    """
    Suite de pruebas rigurosas para validar que is_valid_curricular_table:
    1. Acepta el 100% de las tablas curriculares auténticas en ES, CA, GL, EU y EN.
    2. Rechaza el 100% de las tablas administrativas, de cookies, DPO, convalidaciones y baremos.
    """

    # --- CONTROLES POSITIVOS: Tablas auténticas de asignaturas ---
    def test_positive_spanish_uca(self):
        html = """
        <table>
            <thead><tr><th>Código</th><th>Asignatura</th><th>Carácter</th><th>Créditos</th><th>Cuatrimestre</th></tr></thead>
            <tbody>
                <tr><td>101</td><td>Fundamentos de Programación</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>102</td><td>Cálculo y Álgebra Lineal</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>103</td><td>Estructura de Computadores</td><td>OB</td><td>6</td><td>2</td></tr>
                <tr><td>104</td><td>Sistemas Operativos</td><td>OB</td><td>6</td><td>2</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertTrue(is_valid_curricular_table(table), "Debe aceptar la tabla curricular de la UCA")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 4)
        self.assertEqual(subjects[0]["nombre_elemento"], "Fundamentos de Programación")
        self.assertEqual(subjects[0]["creditos_ects"], "6")

    def test_positive_catalan_uab(self):
        html = """
        <table>
            <thead><tr><th>Codi</th><th>Assignatura</th><th>Tipus</th><th>Crèdits ECTS</th><th>Curs</th></tr></thead>
            <tbody>
                <tr><td>1001</td><td>Anatomia Humana I</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>1002</td><td>Biologia Cel·lular</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>1003</td><td>Bioquímica Mèdica</td><td>OB</td><td>6</td><td>1</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertTrue(is_valid_curricular_table(table), "Debe aceptar la tabla en catalán de la UAB")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 3)
        self.assertEqual(subjects[0]["nombre_elemento"], "Anatomia Humana I")

    def test_positive_galician_usc(self):
        html = """
        <table>
            <thead><tr><th>Materia</th><th>Carácter</th><th>Créditos</th><th>Semestre</th></tr></thead>
            <tbody>
                <tr><td>Química Xeral</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>Física para Químicos</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>Matemáticas Aplicadas</td><td>OB</td><td>6</td><td>2</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertTrue(is_valid_curricular_table(table), "Debe aceptar la tabla en gallego de la USC")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 3)

    def test_positive_basque_ehu(self):
        html = """
        <table>
            <thead><tr><th>Irakasgaia</th><th>Mota</th><th>Kredituak</th><th>Maila</th></tr></thead>
            <tbody>
                <tr><td>Programazioaren Oinarriak</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>Aljebra eta Geometria</td><td>FB</td><td>6</td><td>1</td></tr>
                <tr><td>Konputagailuen Egitura</td><td>OB</td><td>6</td><td>2</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertTrue(is_valid_curricular_table(table), "Debe aceptar la tabla en euskera de la UPV/EHU")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 3)

    def test_positive_english_uc3m(self):
        html = """
        <table>
            <thead><tr><th>Subject</th><th>Type</th><th>Credits</th><th>Semester</th></tr></thead>
            <tbody>
                <tr><td>Aerodynamics I</td><td>Compulsory</td><td>6</td><td>1</td></tr>
                <tr><td>Flight Mechanics</td><td>Compulsory</td><td>6</td><td>1</td></tr>
                <tr><td>Aerospace Propulsion</td><td>Elective</td><td>6</td><td>2</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertTrue(is_valid_curricular_table(table), "Debe aceptar la tabla en inglés de la UC3M")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 3)

    # --- CONTROLES NEGATIVOS: Tablas administrativas que DEBEN ser rechazadas ---
    def test_negative_uam_reconocimiento_creditos(self):
        html = """
        <table>
            <thead><tr><th>Créditos que se pueden reconocer</th><th>Normativa aplicable</th></tr></thead>
            <tbody>
                <tr><td>Máximo: 12 (3 por curso/seminario)</td><td>Ver art. 4 de la normativa</td></tr>
                <tr><td>Coro, orquesta y formación instrumental: máximo 6. Aula de teatro: 3</td><td>Ver art. 6 de la normativa</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertFalse(is_valid_curricular_table(table), "Debe RECHAZAR la tabla de reconocimiento de créditos de la UAM")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 0)

    def test_negative_cookies_ubu(self):
        html = """
        <table>
            <thead><tr><th>Nombre</th><th>Tipo</th><th>Titularidad</th><th>Caducidad</th><th>Finalidad</th></tr></thead>
            <tbody>
                <tr><td>_fbp</td><td>Publicitaria</td><td>www.ubu.es</td><td>90 días</td><td>Facebook Pixel</td></tr>
                <tr><td>_ga</td><td>Analítica</td><td>www.ubu.es</td><td>2 años</td><td>Google Analytics</td></tr>
                <tr><td>_gid</td><td>Analítica</td><td>www.ubu.es</td><td>1 día</td><td>Google Analytics</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertFalse(is_valid_curricular_table(table), "Debe RECHAZAR la tabla de política de cookies")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 0)

    def test_negative_dpo_privacy_uja(self):
        html = """
        <table>
            <tbody>
                <tr><th>Responsable del tratamiento</th><td>Universidad de Jaén</td></tr>
                <tr><th>Delegado de Protección de Datos (DPO)</th><td>dpo@ujaen.es</td></tr>
                <tr><th>Finalidades o usos de los datos</th><td>Gestión académica y matrícula</td></tr>
                <tr><th>Base jurídica</th><td>Cumplimiento de una misión realizada en interés público</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertFalse(is_valid_curricular_table(table), "Debe RECHAZAR la tabla de protección de datos de la UJA")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 0)

    def test_negative_company_training_uab(self):
        html = """
        <table>
            <thead><tr><th>Empresa / institución</th><th>Programa de formación impartida</th><th>Descripción del programa</th></tr></thead>
            <tbody>
                <tr><td>Centro Iberoamericano de Gerencia</td><td>Márketing Político: Máster</td><td>Formación a medida corporativa</td></tr>
                <tr><td>IDC Salud Holding S.L.U.</td><td>Cirugía de Mohs</td><td>Formación para empresas</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        self.assertFalse(is_valid_curricular_table(table), "Debe RECHAZAR la tabla de convenios de formación a medida")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 0)

    def test_negative_modular_summary_table(self):
        """Verifica que tablas que solo contienen el resumen por tipo de materia (Formación Básica, Obligatorias, Optativas) no sean tratadas como asignaturas."""
        html = """
        <table>
            <thead><tr><th>Tipo de Materia</th><th>Créditos ECTS</th></tr></thead>
            <tbody>
                <tr><td>Formación Básica (T)</td><td>60.0</td></tr>
                <tr><td>Obligatorios (B)</td><td>172.0</td></tr>
                <tr><td>Optativas (O)</td><td>72.0</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 0, "No debe extraer filas de resumen modular de 60/172 ECTS como asignaturas individuales")

if __name__ == "__main__":
    unittest.main()
