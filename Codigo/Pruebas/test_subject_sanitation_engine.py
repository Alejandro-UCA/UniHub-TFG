import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Crawler')))
from parsers import sanitize_subject_name, is_spurious_or_administrative_subject


class TestSubjectSanitationEngine(unittest.TestCase):
    """
    Batería de pruebas unitarias para el motor de saneamiento y detección de datos espurios.
    """

    def test_sanitize_leading_numbers(self):
        """Eliminación de numeración ordinal de fila ('1. ', '4. ', 'a) ')"""
        self.assertEqual(sanitize_subject_name("4. Gestión de la Innovación. MX"), "Gestión de la Innovación")
        self.assertEqual(sanitize_subject_name("1. Filosofía"), "Filosofía")
        self.assertEqual(sanitize_subject_name("a) Estructuras de Datos"), "Estructuras de Datos")

    def test_sanitize_footnotes_and_asterisks(self):
        """Eliminación de asteriscos y llamadas a notas al pie (' *', ' (1)', ' †')"""
        self.assertEqual(
            sanitize_subject_name("Análisis de datos y aplicación a la gestión *"),
            "Análisis de datos y aplicación a la gestión"
        )
        self.assertEqual(sanitize_subject_name("Organización Industrial (1)"), "Organización Industrial")
        self.assertEqual(sanitize_subject_name("Sistemas Digitales †"), "Sistemas Digitales")

    def test_spurious_menciones_and_itinerarios(self):
        """Detección y rechazo de cabeceras de mención o itinerario"""
        self.assertTrue(is_spurious_or_administrative_subject("Mención en Educación Física", 30.0, "OP"))
        self.assertTrue(is_spurious_or_administrative_subject("Mención en Pedagogía Terapéutica", 6.0, "OP"))
        self.assertTrue(is_spurious_or_administrative_subject("Itinerario en Software", 12.0, "OP"))
        self.assertTrue(is_spurious_or_administrative_subject("Especialidad en Historia", 6.0, "OB"))

    def test_spurious_high_credits_ordinary(self):
        """Rechazo de materias agregadas con > 12 ECTS en FB/OB/OP"""
        self.assertTrue(is_spurious_or_administrative_subject("Matemáticas", 18.0, "FB"))
        self.assertTrue(is_spurious_or_administrative_subject("Máquinas térmicas", 15.0, "OB"))

    def test_legitimate_high_credits(self):
        """Aceptación de TFG/TFM y Prácticas con créditos altos (hasta 30 ECTS)"""
        self.assertFalse(is_spurious_or_administrative_subject("Trabajo Fin de Grado", 24.0, "TFG/TFM"))
        self.assertFalse(is_spurious_or_administrative_subject("Prácticas Externas", 18.0, "PE"))
        self.assertFalse(is_spurious_or_administrative_subject("Practicum II", 12.0, "PE"))

    def test_administrative_selection_phrases(self):
        """Rechazo de frases de selección de optativas o equivalencias"""
        self.assertTrue(is_spurious_or_administrative_subject("A elegir entre las siguientes optativas", 6.0, "OP"))
        self.assertTrue(is_spurious_or_administrative_subject("Oferta de optativas de 4º curso", 6.0, "OP"))
        self.assertTrue(is_spurious_or_administrative_subject("Tabla de equivalencias del plan 2010", 6.0, "OB"))

    def test_legitimate_bilingual_and_clean_subjects(self):
        """Aceptación de asignaturas docentes válidas y bilingües"""
        self.assertFalse(is_spurious_or_administrative_subject("Álgebra Lineal", 6.0, "FB"))
        self.assertFalse(is_spurious_or_administrative_subject("Cálculo I", 6.0, "FB"))
        self.assertFalse(
            is_spurious_or_administrative_subject(
                "Imperialismo global / Global imperialism and Alter-globalizations",
                6.0,
                "OB"
            )
        )


if __name__ == "__main__":
    unittest.main()
