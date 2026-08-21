import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers import (
    get_required_degree_credits,
    compute_curriculum_total_ects,
    is_curriculum_complete,
    get_curriculum_completeness_status,
    parse_degree_detail_html
)

class TestCurriculumCompletenessValidation(unittest.TestCase):

    def test_01_grado_standard_complete(self):
        """Un Grado estándar de 240 ECTS con 40 asignaturas de 6 ECTS (240 ECTS) es COMPLETO."""
        elementos = [{"nombre_elemento": f"Asignatura {i}", "creditos_ects": 6.0} for i in range(40)]
        deg = {
            "titulo": "Grado en Ingeniería Informática",
            "nivel_academico": "Grado",
            "plan_estudios": {
                "resumen_creditos": {"Créditos Totales": 240},
                "total_elementos": 40,
                "elementos_curriculares": elementos
            }
        }
        self.assertTrue(is_curriculum_complete(deg))
        status = get_curriculum_completeness_status(deg)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["total_ects_obtained"], 240.0)
        self.assertEqual(status["required_ects"], 240.0)
        self.assertEqual(status["status"], "completo")

    def test_02_grado_partial_boe_incomplete(self):
        """Un Grado con solo 4 asignaturas (24 ECTS de modificación parcial) es INCOMPLETO."""
        elementos = [{"nombre_elemento": f"Asignatura Modificada {i}", "creditos_ects": 6.0} for i in range(4)]
        deg = {
            "titulo": "Grado en Matemáticas",
            "nivel_academico": "Grado",
            "plan_estudios": {
                "total_elementos": 4,
                "elementos_curriculares": elementos
            }
        }
        self.assertFalse(is_curriculum_complete(deg))
        status = get_curriculum_completeness_status(deg)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["total_ects_obtained"], 24.0)
        self.assertEqual(status["required_ects"], 240.0)
        self.assertEqual(status["status"], "incompleto_parcial")

    def test_03_grado_summary_only_no_subjects(self):
        """Un Grado con tabla resumen pero 0 asignaturas detalladas es INCOMPLETO."""
        deg = {
            "titulo": "Grado en Historia",
            "nivel_academico": "Grado",
            "plan_estudios": {
                "resumen_creditos": {"Formación Básica": 60, "Obligatorias": 120, "Créditos Totales": 240},
                "total_elementos": 0,
                "elementos_curriculares": []
            }
        }
        self.assertFalse(is_curriculum_complete(deg))
        status = get_curriculum_completeness_status(deg)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["total_ects_obtained"], 0.0)
        self.assertEqual(status["status"], "solo_resumen")

    def test_04_grado_medicina_360_ects(self):
        """Grado en Medicina requiere 360 ECTS oficiales."""
        req = get_required_degree_credits("Grado", "Grado en Medicina")
        self.assertEqual(req, 360.0)

        # 50 asignaturas x 6 ECTS = 300 ECTS (< 360) -> Incompleto
        elementos_300 = [{"nombre_elemento": f"Asig {i}", "creditos_ects": 6.0} for i in range(50)]
        deg_300 = {
            "titulo": "Grado en Medicina",
            "nivel_academico": "Grado",
            "plan_estudios": {"elementos_curriculares": elementos_300}
        }
        self.assertFalse(is_curriculum_complete(deg_300))

        # 60 asignaturas x 6 ECTS = 360 ECTS (>= 360) -> Completo
        elementos_360 = [{"nombre_elemento": f"Asig {i}", "creditos_ects": 6.0} for i in range(60)]
        deg_360 = {
            "titulo": "Grado en Medicina",
            "nivel_academico": "Grado",
            "plan_estudios": {"elementos_curriculares": elementos_360}
        }
        self.assertTrue(is_curriculum_complete(deg_360))

    def test_05_grado_especiales_300_ects(self):
        """Veterinaria, Odontología, Farmacia, Arquitectura y Dobles Grados requieren 300 ECTS."""
        for tit in ["Grado en Odontología", "Grado en Farmacia", "Grado en Veterinaria", "Grado en Fundamentos de la Arquitectura", "Doble Grado en ADE y Derecho"]:
            req = get_required_degree_credits("Grado", tit)
            self.assertEqual(req, 300.0, f"Fallo en {tit}")

    def test_06_master_habilitante_120_ects(self):
        """Másteres de Ingeniería tradicional (Industrial, Caminos, etc.) requieren 120 ECTS."""
        req = get_required_degree_credits("Máster Universitario", "Máster Universitario en Ingeniería Industrial")
        self.assertEqual(req, 120.0)

        elementos_90 = [{"nombre_elemento": f"Asig {i}", "creditos_ects": 6.0} for i in range(15)]
        deg_90 = {
            "titulo": "Máster Universitario en Ingeniería Industrial",
            "nivel_academico": "Máster Universitario",
            "plan_estudios": {"elementos_curriculares": elementos_90}
        }
        self.assertFalse(is_curriculum_complete(deg_90))

        elementos_120 = [{"nombre_elemento": f"Asig {i}", "creditos_ects": 6.0} for i in range(20)]
        deg_120 = {
            "titulo": "Máster Universitario en Ingeniería Industrial",
            "nivel_academico": "Máster Universitario",
            "plan_estudios": {"elementos_curriculares": elementos_120}
        }
        self.assertTrue(is_curriculum_complete(deg_120))

    def test_07_master_habilitante_90_ects(self):
        """Máster en Abogacía y Psicología General Sanitaria requieren 90 ECTS."""
        req_abog = get_required_degree_credits("Máster Universitario", "Máster Universitario en Abogacía y Procura")
        self.assertEqual(req_abog, 90.0)

        req_psi = get_required_degree_credits("Máster Universitario", "Máster Universitario en Psicología General Sanitaria")
        self.assertEqual(req_psi, 90.0)

    def test_08_master_standard_60_ects(self):
        """Másteres generales de especialización requieren 60 ECTS mínimos."""
        req = get_required_degree_credits("Máster Universitario", "Máster Universitario en Inteligencia Artificial")
        self.assertEqual(req, 60.0)

        elementos_60 = [{"nombre_elemento": f"Asig {i}", "creditos_ects": 6.0} for i in range(10)]
        deg_60 = {
            "titulo": "Máster Universitario en Inteligencia Artificial",
            "nivel_academico": "Máster Universitario",
            "plan_estudios": {"elementos_curriculares": elementos_60}
        }
        self.assertTrue(is_curriculum_complete(deg_60))

    def test_09_doctorado_structural_validation(self):
        """Los Doctorados (RD 99/2011) son completos estructuralmente sin asignaturas ECTS."""
        deg_doc = {
            "titulo": "Programa de Doctorado en Ciencias de la Computación",
            "nivel_academico": "Doctorado - RD 99/2011",
            "plan_estudios": {
                "tipo_estructura": "programa_doctorado_investigacion",
                "normativa": "Real Decreto 99/2011",
                "resumen_creditos": {"Tutela Académica Anual": "60 ECTS Equiv."}
            }
        }
        self.assertTrue(is_curriculum_complete(deg_doc))
        status = get_curriculum_completeness_status(deg_doc)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "doctorado_estructural")

    def test_10_missing_plan_returns_false(self):
        """Titulaciones con plan_estudios = None devuelven False y status 'sin_plan'."""
        deg_empty = {
            "titulo": "Grado en Física",
            "nivel_academico": "Grado",
            "plan_estudios": None
        }
        self.assertFalse(is_curriculum_complete(deg_empty))
        status = get_curriculum_completeness_status(deg_empty)
        self.assertFalse(status["is_complete"])
        self.assertEqual(status["status"], "sin_plan")

    def test_11_parse_degree_detail_html_contextual_priority(self):
        """Verifica que el parser HTML priorice los fieldsets de Plan de Estudios y Correcciones frente al Acuerdo de Consejo de Ministros."""
        sample_html = """
        <html>
          <body>
            <fieldset>
              <legend>Fechas y Enlaces a BOE</legend>
              <label>Fecha de publicación del Acuerdo de Consejo de Ministros en el BOE:</label>
              <a href="http://www.boe.es/boe/dias/2021/05/10/pdfs/BOE-A-2021-9999.pdf">BOE 10/05/2021</a>
              <label>Publicación Plan Estudios en el BOE:</label>
              <a href="http://www.boe.es/boe/dias/2010/08/02/pdfs/BOE-A-2010-12409.pdf">BOE 02/08/2010</a>
            </fieldset>
            <fieldset>
              <legend>Fechas de Corrección Plan Estudio</legend>
              <table>
                <tr><th>Correcciones</th></tr>
                <tr><td><a href="http://www.boe.es/boe/dias/2019/04/26/pdfs/BOE-A-2019-6255.pdf">BOE 26/04/2019</a></td></tr>
                <tr><td><a href="http://www.boe.es/boe/dias/2020/07/10/pdfs/BOE-A-2020-7713.pdf">BOE 10/07/2020</a></td></tr>
              </table>
            </fieldset>
          </body>
        </html>
        """
        res = parse_degree_detail_html(sample_html)
        self.assertFalse(res["is_extinct"])
        
        # El enlace más prioritario debe ser la corrección más reciente (2020-07-10)
        self.assertEqual(res["latest_boe_url"], "https://www.boe.es/boe/dias/2020/07/10/pdfs/BOE-A-2020-7713.pdf")
        self.assertEqual(res["boe_date"], "2020-07-10")

        # Comprobar el orden estricto de los candidatos:
        # 1. Corrección 2020 (Prioridad 100)
        # 2. Corrección 2019 (Prioridad 100)
        # 3. Plan Inicial 2010 (Prioridad 90)
        # 4. Acuerdo Consejo Ministros 2021 (Prioridad 10 - al final pese a tener fecha 2021)
        candidates = res["all_boe_candidates"]
        self.assertEqual(len(candidates), 4)
        self.assertEqual(candidates[0]["boe_date"], "2020-07-10")
        self.assertEqual(candidates[0]["priority"], 100)
        self.assertEqual(candidates[1]["boe_date"], "2019-04-26")
        self.assertEqual(candidates[1]["priority"], 100)
        self.assertEqual(candidates[2]["boe_date"], "2010-08-02")
        self.assertEqual(candidates[2]["priority"], 90)
        self.assertEqual(candidates[3]["boe_date"], "2021-05-10")
        self.assertEqual(candidates[3]["priority"], 10)

    def test_12_parse_degree_detail_html_safe_fallback(self):
        """Verifica que una página sin fieldsets estándar ordene todos los BOEs válidos de forma segura por fecha."""
        raw_html = """
        <html>
          <body>
            <div>
              <a href="http://www.boe.es/boe/dias/2015/05/21/pdfs/BOE-A-2015-5628.pdf">BOE 21/05/2015</a>
              <a href="http://www.boe.es/boe/dias/2018/03/18/pdfs/BOE-A-2018-2918.pdf">BOE 18/03/2018</a>
            </div>
          </body>
        </html>
        """
        res = parse_degree_detail_html(raw_html)
        self.assertEqual(res["latest_boe_url"], "https://www.boe.es/boe/dias/2018/03/18/pdfs/BOE-A-2018-2918.pdf")
        self.assertEqual(res["boe_date"], "2018-03-18")
        self.assertEqual(len(res["all_boe_links"]), 2)

    def test_13_parse_universities_from_html_fallback(self):
        """Verifica que si RUCT retorna una tabla HTML de universidades en lugar de XLS, se parsee sin errores."""
        import tempfile
        html_content = """
        <html>
          <body>
            <table>
              <tr><th>Código</th><th>Universidad</th><th>Tipo</th><th>Comunidad Autónoma</th><th>Municipio</th><th>Provincia</th><th>URL</th></tr>
              <tr><td>005</td><td>Universidad de Cádiz</td><td>Pública</td><td>Andalucía</td><td>Cádiz</td><td>Cádiz</td><td>https://www.uca.es</td></tr>
              <tr><td>089</td><td>CUNEF Universidad</td><td>Privada</td><td>Comunidad de Madrid</td><td>Madrid</td><td>Madrid</td><td>https://www.cunef.edu</td></tr>
            </table>
          </body>
        </html>
        """
        with tempfile.NamedTemporaryFile("w", suffix=".xls", delete=False, encoding="utf-8") as tf:
            tf.write(html_content)
            temp_path = tf.name
        try:
            from parsers import parse_universities_xls
            univs = parse_universities_xls(temp_path)
            self.assertEqual(len(univs), 2)
            self.assertEqual(univs[0]["codigo"], "005")
            self.assertEqual(univs[0]["tipo"], "Pública")
            self.assertEqual(univs[1]["codigo"], "089")
            self.assertEqual(univs[1]["tipo"], "Privada")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_14_parse_degrees_from_html_fallback(self):
        """Verifica que si RUCT retorna una tabla HTML de titulaciones en lugar de XLS, se parsee y filtre sin errores."""
        import tempfile
        html_content = """
        <html>
          <body>
            <table>
              <tr><th>Código</th><th>Título</th><th>Nivel académico</th><th>Estado</th></tr>
              <tr><td>2500001</td><td>Grado en Ingeniería Informática</td><td>Grado</td><td>Vigente</td></tr>
              <tr><td>2500002</td><td>Grado en Medicina</td><td>Grado</td><td>Extinguida</td></tr>
            </table>
          </body>
        </html>
        """
        with tempfile.NamedTemporaryFile("w", suffix=".xls", delete=False, encoding="utf-8") as tf:
            tf.write(html_content)
            temp_path = tf.name
        try:
            from parsers import parse_degrees_xls
            degrees = parse_degrees_xls(temp_path)
            self.assertEqual(len(degrees), 1)
            self.assertEqual(degrees[0]["codigo_estudio"], "2500001")
            self.assertEqual(degrees[0]["titulo"], "Grado en Ingeniería Informática")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main(verbosity=2)
