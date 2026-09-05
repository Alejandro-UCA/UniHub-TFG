import unittest
import sys
import os
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers import (
    is_spurious_or_administrative_subject,
    sanitize_subject_name,
    classify_subject_caracter,
    unreverse_text
)
from univ_web_crawler import (
    is_valid_curricular_table,
    is_html_page_matching_degree,
    is_source_url_level_compatible,
)

class TestDeepForensicAuditor(unittest.TestCase):

    def test_reject_departments_and_research_institutes(self):
        """Verifica que nombres de departamentos, áreas o institutos se descarten siempre como asignaturas."""
        dep_examples = [
            "Departamento de Filología Española y Latina",
            "Departament de Química Analítica",
            "Instituto Universitario de Investigación Biomédica",
            "Área de Conocimiento de Ingeniería del Software",
            "Sección Departamental de Derecho Constitucional",
            "Centro de Investigación en Tecnologías de la Información"
        ]
        for name in dep_examples:
            self.assertTrue(
                is_spurious_or_administrative_subject(name, ects_val=6.0, caracter="OB"),
                f"Debe rechazar departamento/instituto: {name}"
            )

    def test_reject_language_prerequisites_and_graduation_rules(self):
        """Verifica que requisitos de acreditación de idiomas se descarten de asignaturas."""
        req_examples = [
            "Acreditación de nivel B2 de lengua inglesa",
            "Requisito de competencia lingüística en idioma extranjero",
            "Prueba de nivel de idioma",
            "Exigencia de idioma B1",
            "Nivel B2 de Alemán",
            "Requisito de graduación en lengua extranjera"
        ]
        for name in req_examples:
            self.assertTrue(
                is_spurious_or_administrative_subject(name, ects_val=6.0, caracter="OB"),
                f"Debe rechazar requisito lingüístico: {name}"
            )

    def test_reject_office_hours_and_tutoring_schedules(self):
        """Verifica que horarios de tutorías y atención al alumno se descarten."""
        sched_examples = [
            "Horario de tutorías personalizadas",
            "Tutorías del primer cuatrimestre",
            "Atención a alumnos despacho 302",
            "Turno de mañana",
            "Horario de clases grupo A",
            "Lunes a Viernes de 9:00 a 14:00"
        ]
        for name in sched_examples:
            self.assertTrue(
                is_spurious_or_administrative_subject(name, ects_val=6.0, caracter="OB"),
                f"Debe rechazar horario/tutoría: {name}"
            )

    def test_reject_grading_scales_and_score_brackets(self):
        """Verifica que calificaciones numéricas y escalas se descarten."""
        grade_examples = [
            "Aprobado (5.0 a 6.9)",
            "Notable (7.0 - 8.9)",
            "Sobresaliente (9.0 - 10.0)",
            "Matrícula de Honor con mención",
            "Escala de calificaciones oficiales",
            "Baremo de convalidación de créditos"
        ]
        for name in grade_examples:
            self.assertTrue(
                is_spurious_or_administrative_subject(name, ects_val=6.0, caracter="OB"),
                f"Debe rechazar calificación/baremo: {name}"
            )

    def test_accept_genuine_multilingual_subjects(self):
        """Verifica que asignaturas docentes legítimas en todas las lenguas oficiales sean admitidas."""
        genuine_subjects = [
            ("Estructura de Datos y Algoritmos", 6.0, "FB"),
            ("Sistemas Operativos Distribuidos", 6.0, "OB"),
            ("Inteligencia Artificial Avanzada", 6.0, "OP"),
            ("Trabajo Fin de Grado", 12.0, "TFG/TFM"),
            ("Prácticas Externas Curriculares", 18.0, "PE"),
            ("Treball de Fi de Màster", 15.0, "TFG/TFM"),
            ("Programació Web i Sistemes Encastats", 6.0, "OB"),
            ("Estatística e Investigación Operativa", 6.0, "FB"),
            ("Konputagailuen Arkitektura", 6.0, "OB"),
            ("Cloud Computing Architecture", 6.0, "OB")
        ]
        for name, ects, car in genuine_subjects:
            self.assertFalse(
                is_spurious_or_administrative_subject(name, ects_val=ects, caracter=car),
                f"Debe aceptar asignatura legítima: {name}"
            )

    def test_reject_html_form_and_schedule_tables(self):
        """Verifica que tablas con formularios o calendarios de exámenes no se confundan con planes de estudio."""
        # 1. Tabla con formulario de búsqueda
        html_form = """
        <table>
          <tr><th>Buscar Asignatura</th><td><input type="text" name="q" /></td></tr>
          <tr><th>Departamento</th><td><select><option>Informática</option></select></td></tr>
          <tr><td colspan="2"><button>Filtrar</button></td></tr>
        </table>
        """
        soup_form = BeautifulSoup(html_form, "html.parser").find("table")
        self.assertFalse(is_valid_curricular_table(soup_form), "Debe rechazar tabla con formulario")

        # 2. Tabla de calendario de exámenes
        html_exam = """
        <table>
          <tr><th>Convocatoria Ordinaria</th><th>Fecha</th><th>Aula</th></tr>
          <tr><td>Enero 2026</td><td>15/01/2026</td><td>Aula Magna</td></tr>
        </table>
        """
        soup_exam = BeautifulSoup(html_exam, "html.parser").find("table")
        self.assertFalse(is_valid_curricular_table(soup_exam), "Debe rechazar tabla de exámenes")

        # 3. Tabla curricular genuina
        html_curriculum = """
        <table>
          <tr><th>Código</th><th>Asignatura</th><th>Carácter</th><th>Créditos ECTS</th><th>Curso</th></tr>
          <tr><td>1001</td><td>Cálculo Infinitesimal</td><td>Formación Básica</td><td>6</td><td>1</td></tr>
          <tr><td>1002</td><td>Álgebra Lineal</td><td>Formación Básica</td><td>6</td><td>1</td></tr>
        </table>
        """
        soup_curr = BeautifulSoup(html_curriculum, "html.parser").find("table")
        self.assertTrue(is_valid_curricular_table(soup_curr), "Debe aceptar tabla curricular genuina")

    def test_rejects_explicitly_cross_level_source_url(self):
        self.assertFalse(
            is_source_url_level_compatible(
                "https://example.edu/es/grados/estudios-literarios/como-accedo.html",
                "Máster",
            )
        )
        self.assertTrue(
            is_source_url_level_compatible(
                "https://example.edu/es/estudios/master/estudios-literarios",
                "Máster",
            )
        )


if __name__ == "__main__":
    unittest.main()
