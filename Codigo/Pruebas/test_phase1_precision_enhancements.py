import unittest
import sys
import os
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from boe_pdf_parser import detect_curricular_table_header, _extract_rows_from_table, _RE_DYNAMIC_TIPO_FIRST, _RE_DYNAMIC_CRED_FIRST
from sanitizers import extract_subjects_from_card_blocks, normalize_cuatrimestre, classify_subject_caracter
from fase1_parte2_web_crawler import (
    extract_html_subjects,
    is_valid_curricular_table,
    _is_relevant_title_candidate,
    is_html_page_matching_degree,
)
from fase1_parte3_precios import compute_degree_price, classify_degree_experimental_tier
from subject_guide_discovery import rank_discovered_guide_urls, _STRONG_GUIDE_MARKERS
from curriculum_validator import get_required_degree_credits, get_curriculum_completeness_status
from fase1_parte4_asignaturas import (
    _normalize_evaluation_breakdown,
    parse_generic_eees_subject_guide,
    _subject_guide_identity_matches,
)


class TestPhase1PrecisionEnhancements(unittest.TestCase):

    def test_multiline_subject_continuation_uppercase(self):
        """Valida que una fila secundaria sin créditos que empieza en mayúscula se una a la anterior."""
        rows = [
            ["Asignatura", "Créditos", "Carácter", "Curso"],
            ["Ingeniería del Software", "6", "OB", "2"],
            ["Avanzada", "", "", ""],
            ["Estructuras de Datos y", "6", "OB", "1"],
            ["Algoritmos II", "", "", ""],
            ["Derecho Constitucional", "6", "FB", "1"],
            ["I", "", "", ""],
        ]
        extracted = _extract_rows_from_table(rows)
        self.assertEqual(len(extracted), 3)
        self.assertEqual(extracted[0]["nombre_elemento"], "Ingeniería del Software Avanzada")
        self.assertEqual(extracted[1]["nombre_elemento"], "Estructuras de Datos y Algoritmos II")
        self.assertEqual(extracted[2]["nombre_elemento"], "Derecho Constitucional I")

    def test_card_extraction_unprefixed_modern_html(self):
        """Valida la extracción de asignaturas en tarjetas HTML modernas sin código numérico prefijado."""
        html = """
        <div class="curriculum-container">
            <div class="subject-card">
                <h3>Álgebra Lineal</h3>
                <span class="badge">6 ECTS</span>
                <span class="type">Formación Básica</span>
                <span class="year">1º Curso</span>
            </div>
            <div class="subject-card">
                <h3>Fundamentos de Programación</h3>
                <p>6 Créditos - Obligatoria - 1º Curso - 1C</p>
            </div>
            <div class="subject-card">
                <h3>Sistemas Operativos</h3>
                <div>6 ECTS | 2º Curso | 1C | Obligatoria</div>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        subjects = extract_subjects_from_card_blocks(soup)
        self.assertEqual(len(subjects), 3)
        names = [s["nombre_elemento"] for s in subjects]
        self.assertIn("Álgebra Lineal", names)
        self.assertIn("Fundamentos de Programación", names)
        self.assertIn("Sistemas Operativos", names)
        
        for s in subjects:
            self.assertEqual(s["creditos"], 6.0)

    def test_table_course_context_inheritance(self):
        """Valida que tablas consecutivas hereden el curso del encabezado o contenedor padre."""
        html = """
        <div>
            <h2>Primer Curso</h2>
            <table>
                <tr><th>Asignatura</th><th>Créditos</th><th>Tipo</th></tr>
                <tr><td>Cálculo</td><td>6</td><td>FB</td></tr>
                <tr><td>Física</td><td>6</td><td>FB</td></tr>
            </table>
            <h2>Segundo Curso</h2>
            <table>
                <tr><th>Asignatura</th><th>Créditos</th><th>Tipo</th></tr>
                <tr><td>Bases de Datos</td><td>6</td><td>OB</td></tr>
                <tr><td>Redes de Computadores</td><td>6</td><td>OB</td></tr>
            </table>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        subjects = extract_html_subjects(soup)
        self.assertEqual(len(subjects), 4)
        
        calc = next(s for s in subjects if s["nombre_elemento"] == "Cálculo")
        self.assertEqual(calc["curso"], "1")
        
        bd = next(s for s in subjects if s["nombre_elemento"] == "Bases de Datos")
        self.assertEqual(bd["curso"], "2")

    def test_experimental_pricing_tiers(self):
        """Valida que los precios autonómicos discriminen por Grado de Experimentalidad."""
        # En Comunitat Valenciana:
        # Enfermería (Salud) -> 17.34 €/ECTS
        # Telecomunicaciones (Ingeniería) -> 15.10 €/ECTS
        # ADE (Sociales) -> 12.79 €/ECTS
        val_enf = compute_degree_price("Comunitat Valenciana", "Pública", "Grado", "Grado en Enfermería")
        val_tel = compute_degree_price("Comunitat Valenciana", "Pública", "Grado", "Grado en Ingeniería de Telecomunicación")
        val_ade = compute_degree_price("Comunitat Valenciana", "Pública", "Grado", "Grado en Administración y Dirección de Empresas")

        self.assertEqual(val_enf["precio_credito_ects"], 17.34)
        self.assertEqual(val_tel["precio_credito_ects"], 15.10)
        self.assertEqual(val_ade["precio_credito_ects"], 12.79)

        # En Galicia:
        # Medicina (Salud) -> 13.93 €/ECTS
        # Derecho (Sociales) -> 11.89 €/ECTS
        gal_med = compute_degree_price("Galicia", "Pública", "Grado", "Grado en Medicina")
        gal_der = compute_degree_price("Galicia", "Pública", "Grado", "Grado en Derecho")
        self.assertEqual(gal_med["precio_credito_ects"], 13.93)
        self.assertEqual(gal_der["precio_credito_ects"], 11.89)

    def test_regulated_master_detection(self):
        """Valida la correcta detección de Másteres Habilitantes oficiales."""
        m_abogacia = compute_degree_price("Andalucía", "Pública", "Máster", "Máster Universitario en Abogacía y Procura")
        m_profesorado = compute_degree_price("Andalucía", "Pública", "Máster", "Máster en Profesorado de Educación Secundaria")
        m_industrial = compute_degree_price("Andalucía", "Pública", "Máster", "Máster en Ingeniería Industrial")
        m_libre = compute_degree_price("Andalucía", "Pública", "Máster", "Máster en Inteligencia Artificial Avanzada")

        self.assertEqual(m_abogacia["precio_credito_ects"], 13.68)
        self.assertEqual(m_profesorado["precio_credito_ects"], 13.68)
        self.assertEqual(m_industrial["precio_credito_ects"], 13.68)
        self.assertIsNotNone(m_libre["precio_credito_ects"])

    def test_guide_discovery_single_token_subject(self):
        """Valida que una asignatura de un solo término clave (ej. Microbiología) empareje su guía."""
        records = [
            {
                "url": "https://guias.uca.es/2024/microbiologia.html",
                "anchor_text": "Guía Docente de Microbiología",
                "path_segments": ["2024", "microbiologia.html"]
            },
            {
                "url": "https://guias.uca.es/2024/fisica.html",
                "anchor_text": "Guía Docente de Física",
                "path_segments": ["2024", "fisica.html"]
            }
        ]
        ranked = rank_discovered_guide_urls(records, subject_name="Microbiología")
        self.assertTrue(len(ranked) > 0)
        self.assertEqual(ranked[0], "https://guias.uca.es/2024/microbiologia.html")

    def test_double_master_credit_requirement(self):
        """Valida que un Doble Máster no exija erróneamente 300 ECTS de Doble Grado."""
        req_double_master = get_required_degree_credits("Máster Universitario", "Doble Máster Universitario en Abogacía y Asesoría Fiscal")
        self.assertEqual(req_double_master, 120.0)

        # Plan con 120 ECTS de Doble Máster debe ser completo
        status = get_curriculum_completeness_status({
            "nivel_academico": "Máster Universitario",
            "titulo": "Doble Máster Universitario en Ingeniería Industrial y ADE",
            "plan_estudios": {
                "elementos_curriculares": [
                    {"nombre_elemento": f"Asignatura {i}", "creditos_ects": 6.0} for i in range(20)
                ]
            }
        })
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "completo")

    def test_normalize_cuatrimestre_precision(self):
        """Valida que la presencia del número de curso no confunda el cuatrimestre."""
        # Curso 2, Semestre 1 -> Debe ser 1C (no 2C por contener '2')
        self.assertEqual(normalize_cuatrimestre("Curso 2 - Semestre 1"), "1C")
        self.assertEqual(normalize_cuatrimestre("2º Curso / 1er Cuatrimestre"), "1C")
        self.assertEqual(normalize_cuatrimestre("Curso 1 - Semestre 2"), "2C")
        self.assertEqual(normalize_cuatrimestre("1er Curso / 2º Semestre"), "2C")
        self.assertEqual(normalize_cuatrimestre("Anual"), "Anual")
        self.assertEqual(normalize_cuatrimestre("1-2"), "Anual")
        self.assertEqual(normalize_cuatrimestre("2. lauhilekoa"), "2C")
        self.assertEqual(normalize_cuatrimestre("1. lauhilekoa"), "1C")

    def test_coofficial_boe_dynamic_parsing(self):
        """Valida el reconocimiento de acrónimos cooficiales (MAL, KAN, TR, COMP) en regex dinámico."""
        m_mal = _RE_DYNAMIC_TIPO_FIRST.match("Gradu Amaierako Lana MAL 12")
        self.assertIsNotNone(m_mal)
        self.assertEqual(m_mal.group("car").upper(), "MAL")
        self.assertEqual(classify_subject_caracter(m_mal.group("car")), "TFG/TFM")

        m_kan = _RE_DYNAMIC_CRED_FIRST.match("Kanpoko Praktikak 6 KAN")
        self.assertIsNotNone(m_kan)
        self.assertEqual(m_kan.group("car").upper(), "KAN")
        self.assertEqual(classify_subject_caracter(m_kan.group("car")), "PE")

        m_comp = _RE_DYNAMIC_TIPO_FIRST.match("Algorithms and Complexity COMP 6")
        self.assertIsNotNone(m_comp)
        self.assertEqual(m_comp.group("car").upper(), "COMP")
        self.assertEqual(classify_subject_caracter(m_comp.group("car")), "OB")

    def test_coofficial_guide_discovery_markers(self):
        """Valida que los marcadores de guías autonómicas e internacionales puntúen sitemaps."""
        self.assertIn("pla-docent", _STRONG_GUIDE_MARKERS)
        self.assertIn("guia-docent", _STRONG_GUIDE_MARKERS)
        self.assertIn("irakasgaiak", _STRONG_GUIDE_MARKERS)
        self.assertIn("course-syllabus", _STRONG_GUIDE_MARKERS)

        records = [
            {
                "url": "https://web.ub.edu/estudis/grau-informatica/pla-docent/fonaments-programacio",
                "anchor_text": "Pla Docent de Fonaments de Programació",
                "path_segments": ["estudis", "grau-informatica", "pla-docent", "fonaments-programacio"]
            }
        ]
        ranked = rank_discovered_guide_urls(records, subject_name="Fonaments de Programació")
        self.assertEqual(len(ranked), 1)
        self.assertIn("pla-docent", ranked[0])

    def test_multilingual_evaluation_breakdown(self):
        """Valida el desglose de evaluación en gallego, euskera e inglés."""
        guide_multilingual = {
            "sistema_evaluacion": [
                {"tarea": "Amaierako azterketa", "ponderacion_porcentaje": 60.0},
                {"tarea": "Laborategiko praktikak", "ponderacion_porcentaje": 20.0},
                {"tarea": "Etengabeko ebaluazioa", "ponderacion_porcentaje": 20.0},
            ]
        }
        breakdown = _normalize_evaluation_breakdown(guide_multilingual)
        self.assertEqual(breakdown["examen_final_porcentaje"], 60.0)
        self.assertEqual(breakdown["practicas_porcentaje"], 20.0)
        self.assertEqual(breakdown["evaluacion_continua_porcentaje"], 20.0)

        guide_galician = {
            "sistema_evaluacion": [
                {"tarea": "Exame final escrito", "ponderacion_porcentaje": 50.0},
                {"tarea": "Prácticas de laboratorio e obradoiro", "ponderacion_porcentaje": 20.0},
                {"tarea": "Avaliación continua e seguimento", "ponderacion_porcentaje": 30.0},
            ]
        }
        breakdown_gal = _normalize_evaluation_breakdown(guide_galician)
        self.assertEqual(breakdown_gal["examen_final_porcentaje"], 50.0)
        self.assertEqual(breakdown_gal["practicas_porcentaje"], 20.0)
        self.assertEqual(breakdown_gal["evaluacion_continua_porcentaje"], 30.0)

    def test_regulated_master_maritime_and_chemical(self):
        """Valida que los másteres regulados marítimos y de ingeniería química reciban tarifa habilitante."""
        p_nautica = compute_degree_price("Galicia", "Pública", "Máster", "Máster Universitario en Náutica y Transporte Marítimo")
        self.assertEqual(p_nautica["precio_credito_ects"], 13.50)

        p_quimica = compute_degree_price("Andalucía", "Pública", "Máster", "Máster en Ingeniería Química")
        self.assertEqual(p_quimica["precio_credito_ects"], 13.68)

    def test_generic_eees_requisitos_and_professor_email(self):
        """Valida la captura de requisitos previos e incompatibilidades y emails de profesores en guías EEES."""
        html = """
        <html>
            <body>
                <h1>Sistemas Distribuidos</h1>
                <h2>Requisitos Previos</h2>
                <ul>
                    <li>Haber superado Redes de Computadores y Sistemas Operativos.</li>
                </ul>
                <h2>Profesorado</h2>
                <ul>
                    <li>Dr. Juan Pérez (<a href="mailto:juan.perez@uca.es">juan.perez@uca.es</a>)</li>
                    <li>Dra. María Gómez maria.gomez@uca.es</li>
                </ul>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        guide = parse_generic_eees_subject_guide(soup, "https://uca.es/guia/101")
        self.assertIn("Haber superado Redes de Computadores y Sistemas Operativos.", guide["requisitos_previos"])
        self.assertEqual(len(guide["profesorado"]), 2)
        self.assertEqual(guide["profesorado"][0]["email"], "juan.perez@uca.es")
        self.assertEqual(guide["profesorado"][1]["email"], "maria.gomez@uca.es")

    def test_headerless_table_validation_and_guardrails(self):
        """Valida que tablas curriculares sin <th> explícito pero bajo encabezado de curso se acepten, y las de tasas se rechacen."""
        valid_html = """
        <div>
            <h3>Primer Curso</h3>
            <table>
                <tr><td>Álgebra Lineal</td><td>6</td><td>FB</td></tr>
                <tr><td>Cálculo</td><td>6</td><td>FB</td></tr>
                <tr><td>Física</td><td>6</td><td>FB</td></tr>
            </table>
        </div>
        """
        soup_valid = BeautifulSoup(valid_html, "html.parser")
        table_valid = soup_valid.find("table")
        self.assertTrue(is_valid_curricular_table(table_valid))

        fee_html = """
        <div>
            <h3>Precios Administrativos</h3>
            <table>
                <tr><td>Tasa de matrícula</td><td>15.50</td></tr>
                <tr><td>Tasas de secretaría</td><td>6.00</td></tr>
            </table>
        </div>
        """
        soup_fee = BeautifulSoup(fee_html, "html.parser")
        table_fee = soup_fee.find("table")
        self.assertFalse(is_valid_curricular_table(table_fee))

    def test_coofficial_academic_marker_relevance(self):
        """Valida que URLs con lemas catalanes/gallegos/vascos/ingleses sean consideradas candidatas académicas relevantes."""
        self.assertTrue(_is_relevant_title_candidate("https://ub.edu/estudis/graus/quimica", "Química", ["quimica"]))
        self.assertTrue(_is_relevant_title_candidate("https://ehu.eus/gradua-informatika", "Informatika", ["informatika"]))
        self.assertTrue(_is_relevant_title_candidate("https://usc.gal/estudos/grao/matematicas", "Matemáticas", ["matematicas"]))

    def test_engineering_banner_distinction(self):
        """Valida que un grado de ciencias no sea rechazado por estar alojado en una Escuela de Ingeniería, pero sí distinga Ingeniería Química."""
        math_html = """
        <html>
            <body>
                <h1>Grado en Matemáticas</h1>
                <h2>Escuela Técnica Superior de Ingeniería</h2>
            </body>
        </html>
        """
        soup_math = BeautifulSoup(math_html, "html.parser")
        self.assertTrue(is_html_page_matching_degree(soup_math, "Grado en Matemáticas", "Universidad de Prueba"))

        chem_eng_html = """
        <html>
            <body>
                <h1>Grado en Ingeniería Química</h1>
            </body>
        </html>
        """
        soup_chem_eng = BeautifulSoup(chem_eng_html, "html.parser")
        self.assertFalse(is_html_page_matching_degree(soup_chem_eng, "Grado en Química", "Universidad de Prueba"))

    def test_single_token_subject_guide_identity_matches(self):
        """Valida que asignaturas de una sola palabra hagan match con variantes cortas (<= 3 tokens) pero rechacen cursos lejanos."""
        self.assertTrue(_subject_guide_identity_matches("Física", "101", {"nombre_asignatura": "Física General", "codigo_asignatura": "101"}))
        self.assertTrue(_subject_guide_identity_matches("Química", "", {"nombre_asignatura": "Química I", "codigo_asignatura": ""}))
        self.assertFalse(_subject_guide_identity_matches("Derecho", "", {"nombre_asignatura": "Derecho Procesal Penal Internacional Especializado", "codigo_asignatura": ""}))

    def test_completo_normativo_with_summary_and_core_subjects(self):
        """Valida que un grado con 228 ECTS (36 asignaturas) y resumen de 240 ECTS sea completo_normativo, y uno de 120 ECTS sea incompleto."""
        elements_228 = [{"nombre_elemento": f"Asignatura {i}", "creditos_ects": "6.0", "caracter": "OB"} for i in range(38)]
        plan_228 = {
            "nivel_academico": "Grado",
            "titulo": "Grado en Derecho",
            "plan_estudios": {
                "resumen_creditos": {"Total": "240"},
                "elementos_curriculares": elements_228
            }
        }
        status_228 = get_curriculum_completeness_status(plan_228)
        self.assertTrue(status_228["is_complete"])
        self.assertEqual(status_228["status"], "completo_normativo")

        elements_120 = [{"nombre_elemento": f"Asignatura {i}", "creditos_ects": "6.0", "caracter": "OB"} for i in range(20)]
        plan_120 = {
            "nivel_academico": "Grado",
            "titulo": "Grado en Derecho",
            "plan_estudios": {
                "resumen_creditos": {"Total": "240"},
                "elementos_curriculares": elements_120
            }
        }
        status_120 = get_curriculum_completeness_status(plan_120)
        self.assertFalse(status_120["is_complete"])
        self.assertEqual(status_120["status"], "incompleto_parcial")

    def test_dom_tab_extraction_and_extinction_filter(self):
        """Valida la resolución de curso desde disparadores de pestañas y el descarte de planes en extinción."""
        html = """
        <div>
            <ul class="nav-tabs">
                <li><a href="#tab-c2">2º Curso</a></li>
                <li><a href="#tab-ext">Plan en Extinción</a></li>
            </ul>
            <div id="tab-c2" class="tab-pane">
                <table>
                    <tr><td>Estructura de Datos</td><td>6</td><td>OB</td></tr>
                    <tr><td>Sistemas Operativos</td><td>6</td><td>OB</td></tr>
                </table>
            </div>
            <div id="tab-ext" class="tab-pane">
                <h3>Plan 2009 en extinción</h3>
                <table>
                    <tr><td>Antigua Asignatura Obsoleta</td><td>6</td><td>OB</td></tr>
                    <tr><td>Antigua Asignatura Dos</td><td>6</td><td>OB</td></tr>
                </table>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        subjects = extract_html_subjects(soup)
        names = [s["nombre_elemento"] for s in subjects]
        self.assertIn("Estructura de Datos", names)
        self.assertNotIn("Antigua Asignatura Obsoleta", names)
        for s in subjects:
            if s["nombre_elemento"] == "Estructura de Datos":
                self.assertEqual(s["curso"], "2")


if __name__ == "__main__":
    unittest.main()
