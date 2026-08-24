import unittest
import sys
import os

# Asegurar path de imports al módulo Crawler
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Crawler')))
from parsers import parse_header_schema, parse_boe_text_curriculum_dynamic, parse_boe_pdf


class TestDynamicBOESchemaParser(unittest.TestCase):
    """
    Batería de pruebas unitarias para la inferencia dinámica de esquemas de columnas
    y la extracción contextual de asignaturas en resoluciones oficiales del BOE (RD 822/2021).
    """

    def test_schema_inference_variations(self):
        """Verifica que el analizador deduzca el esquema correcto para diferentes formatos de cabecera."""
        # Formato 1: Módulo Asignatura Tipo Créditos Especialidad
        h1 = "6.1 Estructura del plan de estudios: Módulo Asignatura Tipo Créditos Especialidad"
        s1 = parse_header_schema(h1)
        self.assertIn("modulo", s1)
        self.assertIn("asignatura", s1)
        self.assertIn("tipo", s1)
        self.assertIn("creditos", s1)
        self.assertLess(s1.index("tipo"), s1.index("creditos"))

        # Formato 2: Asignatura Créditos Tipo según especialidad
        h2 = "Módulo Asignatura Créditos Tipo según especialidad"
        s2 = parse_header_schema(h2)
        self.assertIn("asignatura", s2)
        self.assertIn("tipo", s2)
        self.assertIn("creditos", s2)
        self.assertLess(s2.index("creditos"), s2.index("tipo"))

        # Formato 3: Multilingüe con carácter y ECTS
        h3 = "Materia Denominación de la Asignatura Carácter ECTS Curso"
        s3 = parse_header_schema(h3)
        self.assertIn("asignatura", s3)
        self.assertIn("tipo", s3)
        self.assertIn("creditos", s3)

    def test_dynamic_curriculum_text_extraction(self):
        """Verifica la extracción completa de materias y módulos con datos sintéticos realistas."""
        sample_boe_text = """
        ANEXO
        Plan de estudios conducente a la obtención del título de Graduado o Graduada en Química
        4. Total de créditos ECTS: 240.
        6.1 Estructura del plan de estudios:
        Módulo Asignatura Tipo Créditos
        Matemáticas y Física para Químicos.
        Matemáticas I. FBA 6
        Matemáticas II. FBA 6
        Física I. FBA 6
        Química General.
        Química I. FBA 6
        Química Orgánica.
        Química Orgánica I. OB 6
        Síntesis Orgánica. OB 6
        Química Bioinorgánica. OP 6
        Trabajo de Fin de Grado de Química. Trabajo de Fin de Grado de Química. TFG 6
        6.2 Condiciones de terminación
        BOLETÍN OFICIAL DEL ESTADO
        cve: BOE-A-2025-5401
        El Rector, Jaume Carot Giner.
        """
        res = parse_boe_text_curriculum_dynamic(sample_boe_text, "Graduado en Química", "Grado")
        elems = res.get("elementos_curriculares", [])
        self.assertEqual(len(elems), 8)

        # Verificar asignaturas concretas
        names = {e["nombre_elemento"]: e for e in elems}
        self.assertIn("Matemáticas I", names)
        self.assertEqual(names["Matemáticas I"]["caracter"], "FB")
        self.assertEqual(names["Matemáticas I"]["creditos_ects"], "6")
        self.assertEqual(names["Matemáticas I"]["modulo"], "Matemáticas y Física para Químicos")

        self.assertIn("Química Orgánica I", names)
        self.assertEqual(names["Química Orgánica I"]["caracter"], "OB")
        self.assertEqual(names["Química Orgánica I"]["modulo"], "Química Orgánica")

        self.assertIn("Química Bioinorgánica", names)
        self.assertEqual(names["Química Bioinorgánica"]["caracter"], "OP")

        self.assertIn("Trabajo de Fin de Grado de Química", names)
        self.assertEqual(names["Trabajo de Fin de Grado de Química"]["caracter"], "TFG/TFM")

    def test_reverse_order_creditos_before_tipo(self):
        """Verifica la extracción cuando los créditos van antes del tipo (ej: Higiene industrial. 16 OBL)."""
        sample_text = """
        6.1 Estructura del plan de estudios:
        Módulo Asignatura Créditos Tipo según especialidad
        Módulo común.
        Fundamentos y técnicas en PRL. 6 OBL
        Gestión de la prevención. 6 OBL
        Optativas de especialidad.
        Seguridad laboral. 16 OPT
        Ergonomía aplicada. 8 OPT
        6.2 Condiciones de terminación
        """
        res = parse_boe_text_curriculum_dynamic(sample_text, "Máster en PRL", "Máster")
        elems = res.get("elementos_curriculares", [])
        self.assertEqual(len(elems), 4)

        names = {e["nombre_elemento"]: e for e in elems}
        self.assertIn("Seguridad laboral", names)
        self.assertEqual(names["Seguridad laboral"]["creditos_ects"], "16")
        self.assertEqual(names["Seguridad laboral"]["caracter"], "OP")
        self.assertEqual(names["Seguridad laboral"]["modulo"], "Optativas de especialidad")


if __name__ == "__main__":
    unittest.main()
