import unittest
import sys
import os
import json
import tempfile
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers.boe_pdf import (
    detect_curricular_table_header,
    _extract_rows_from_table,
    extract_credit_summary,
    _normalise_dynamic_curricular_line,
    _RE_DYNAMIC_TIPO_FIRST,
    _RE_DYNAMIC_CRED_FIRST,
)
from utils.sanitizers import extract_subjects_from_card_blocks, normalize_cuatrimestre, classify_subject_caracter
from pipelines.parte2_web_crawler import (
    UniversityWebCrawler,
    extract_html_subjects,
    is_valid_curricular_table,
    _is_relevant_title_candidate,
    is_html_page_matching_degree,
)
from pipelines.parte3_precios import compute_degree_price, classify_degree_experimental_tier
from extractors.subject_guides import rank_discovered_guide_urls, _STRONG_GUIDE_MARKERS
from quality.curriculum_validator import get_required_degree_credits, get_curriculum_completeness_status
from pipelines.parte4_asignaturas import (
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

    def test_split_parallel_pdf_cells_after_separated_table_header(self):
        """Recupera filas cuando el PDF separa cabecera y celdas multilínea."""
        columns = {"subject": 0, "ects": 1}
        rows = [[
            "Álgebra Lineal.\nCálculo Diferencial.\nFísica I.",
            "6\n6\n6",
        ]]
        extracted = _extract_rows_from_table(rows, initial_columns=columns)
        self.assertEqual([item["nombre_elemento"] for item in extracted], [
            "Álgebra Lineal", "Cálculo Diferencial", "Física I",
        ])
        self.assertEqual([item["creditos_ects"] for item in extracted], [6.0, 6.0, 6.0])

    def test_recovers_shifted_rows_and_replacement_headers_from_pdfplumber(self):
        header = ["", "C�digo", "", "", "Asignatura", "", "", "Cr�ditos", "Car�cter", "", "", "Semestre", ""]
        self.assertEqual(
            {"subject": 4, "ects": 7, "caracter": 8, "cuatrimestre": 11},
            detect_curricular_table_header(header),
        )
        extracted = _extract_rows_from_table(
            [header, ["16302", None, None, "QU�MICA", None, None, "12", None, "FB", None, "Anual", None, None]]
        )
        self.assertEqual([item["nombre_elemento"] for item in extracted], ["QU�MICA"])
        self.assertEqual(extracted[0]["creditos_ects"], 12.0)

    def test_dynamic_parser_accepts_full_character_and_pdf_leaders(self):
        """Acepta etiquetas completas y puntos de relleno de tablas BOE sin bordes."""
        line = "Entornos avanzados de producción de software . . . . . 3 Optativa."
        normalized = _normalise_dynamic_curricular_line(line)
        match = _RE_DYNAMIC_CRED_FIRST.match(normalized)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("ects"), "3")
        self.assertEqual(match.group("car"), "Optativa")

    def test_credit_summary_ignores_subject_rows_and_pdf_footer_codes(self):
        """No confunde etiquetas singulares de asignaturas con el resumen ECTS."""
        summary = extract_credit_summary(
            "Obligatorias .......................... 15\n"
            "Optativas ............................ 39\n"
            "Trabajo fin de máster ................... 6\n"
            "Total.............................. 60\n"
            "Una materia 6 Obligatoria.\n"
            "47701-1102-A-EOB"
        )
        self.assertEqual(summary["Obligatorias"], "15")
        self.assertEqual(summary["Optativas"], "39")
        self.assertEqual(summary["Trabajo Fin de Grado / Máster"], "6")
        self.assertEqual(summary["Créditos Totales"], "60")

    def test_module_materia_header_is_a_valid_curricular_schema(self):
        """Conserva planes que publican materias como unidad curricular."""
        header = detect_curricular_table_header(["Módulo", "Materia", "Carácter", "ECTS"])
        self.assertEqual(header["subject"], header["materia"])
        extracted = _extract_rows_from_table(
            [["Materia", "Créditos ECTS"], ["Módulo troncal", "6"]]
        )
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["nombre_elemento"], "Módulo troncal")

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

    def test_normative_total_with_optional_alternatives_preserves_complete_plan(self):
        """Un total oficial y una tabla completa pueden incluir optativas ofertadas como alternativas."""
        elements = [
            {"nombre_elemento": f"Obligatoria {i}", "creditos_ects": 6.0, "caracter": "OB"}
            for i in range(10)
        ] + [
            {"nombre_elemento": f"Optativa {i}", "creditos_ects": 6.0, "caracter": "OP"}
            for i in range(10)
        ]
        payload = {
            "nivel_academico": "Máster",
            "titulo": "Máster Universitario en Sistemas",
            "plan_estudios": {
                "resumen_creditos": {"Créditos Totales": "60"},
                "elementos_curriculares": elements,
            },
        }
        status = get_curriculum_completeness_status(payload)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "completo_normativo")

    def test_partial_source_does_not_block_later_complete_source(self):
        """Una primera ficha parcial no debe impedir probar otra fuente del mismo dominio."""
        partial_html = """
        <html><h1>Máster en Ciencia de Datos Aplicados</h1><table>
          <tr><th>Asignatura</th><th>ECTS</th></tr>
          <tr><td>Fundamentos</td><td>6</td></tr>
          <tr><td>Modelos</td><td>6</td></tr>
          <tr><td>Proyecto</td><td>6</td></tr>
        </table></html>
        """
        complete_rows = "".join(
            f"<tr><td>Asignatura {i}</td><td>6</td></tr>" for i in range(10)
        )
        complete_html = f"""
        <html><h1>Máster en Ciencia de Datos</h1><table>
          <tr><th>Asignatura</th><th>ECTS</th></tr>{complete_rows}
        </table></html>
        """
        urls = {
            "https://example.edu/ciencia-datos-aplicados-plan",
            "https://example.edu/ciencia-datos-plan",
        }
        downloader = MagicMock()

        def fetch(url):
            if url.endswith("ciencia-datos-aplicados-plan"):
                return partial_html
            if url.endswith("ciencia-datos-plan"):
                return complete_html
            return "<html><body></body></html>"

        downloader.fetch_text.side_effect = fetch
        crawler = UniversityWebCrawler()
        crawler.ledger = MagicMock()
        crawler.extract_sitemap_candidate_urls = MagicMock(return_value=urls)
        crawler._build_academic_catalog_map = MagicMock(return_value={})
        degree = {
            "codigo_estudio": "TEST1",
            "titulo": "Máster en Ciencia de Datos",
            "nivel_academico": "Máster",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "degree.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                json.dump({"plan_estudios": None}, handle)
            with patch(
                "pipelines.parte2_web_crawler.find_plan_filepath",
                return_value=plan_path,
            ):
                stats = crawler._crawl_university_degrees(
                    downloader,
                    "999",
                    "Universidad de Prueba",
                    "https://example.edu",
                    [degree],
                    {
                        "resolved_degrees_count": 0,
                        "missing_degrees_count": 1,
                    },
                )
            with open(plan_path, encoding="utf-8") as handle:
                saved = json.load(handle)

        self.assertEqual(stats["resolved_degrees_count"], 1)
        self.assertEqual(
            saved["web_fuente_directa_url"],
            "https://example.edu/ciencia-datos-plan",
        )
        self.assertEqual(
            len(saved["plan_estudios"]["elementos_curriculares"]),
            10,
        )

    def test_partial_direct_page_above_threshold_follows_linked_curriculum(self):
        """Una ficha parcialmente suficiente debe seguir su fuente curricular enlazada."""
        partial_rows = "".join(
            f"<tr><td>Base {i}</td><td>6</td></tr>" for i in range(7)
        )
        complete_rows = "".join(
            f"<tr><td>Asignatura {i}</td><td>6</td></tr>" for i in range(10)
        )
        partial_html = f"""
        <html><h1>Máster en Ciencia de Datos</h1>
          <a href="/ciencia-datos-plan">Plan de estudios completo</a>
          <table><tr><th>Asignatura</th><th>ECTS</th></tr>{partial_rows}</table>
        </html>
        """
        complete_html = f"""
        <html><h1>Máster en Ciencia de Datos</h1><table>
          <tr><th>Asignatura</th><th>ECTS</th></tr>{complete_rows}
        </table></html>
        """
        downloader = MagicMock()
        downloader.fetch_text.side_effect = lambda url: (
            partial_html
            if url.endswith("/ficha")
            else complete_html
            if url.endswith("/ciencia-datos-plan")
            else "<html><body></body></html>"
        )
        crawler = UniversityWebCrawler()
        crawler.ledger = MagicMock()
        crawler._build_academic_catalog_map = MagicMock(return_value={})
        degree = {
            "codigo_estudio": "TEST2",
            "titulo": "Máster en Ciencia de Datos",
            "nivel_academico": "Máster",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = os.path.join(temp_dir, "degree.json")
            with open(plan_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "plan_estudios": None,
                        "web_fuente_directa_url": "https://example.edu/ficha",
                    },
                    handle,
                )
            with patch(
                "pipelines.parte2_web_crawler.find_plan_filepath",
                return_value=plan_path,
            ):
                stats = crawler._crawl_university_degrees(
                    downloader,
                    "999",
                    "Universidad de Prueba",
                    "https://example.edu",
                    [degree],
                    {
                        "resolved_degrees_count": 0,
                        "missing_degrees_count": 1,
                    },
                )
            with open(plan_path, encoding="utf-8") as handle:
                saved = json.load(handle)

        self.assertEqual(stats["resolved_degrees_count"], 1)
        self.assertEqual(
            saved["web_fuente_directa_url"],
            "https://example.edu/ciencia-datos-plan",
        )
        self.assertEqual(
            len(saved["plan_estudios"]["elementos_curriculares"]),
            10,
        )

    def test_fills_missing_ects_from_explicit_uniform_page_statement(self):
        """Completa ECTS omitidos en tablas cuando la prosa fija la carga común."""
        soup = BeautifulSoup(
            """
            <html><body>
              <h1>Grado en Sistemas</h1>
              <p>Todas las asignaturas tienen 6 créditos ECTS, salvo las prácticas.</p>
              <table>
                <tr><th>Asignatura</th><th>Tipo</th></tr>
                <tr><td>Fundamentos de Sistemas</td><td>Obligatoria</td></tr>
                <tr><td>Arquitectura de Computadores</td><td>Obligatoria</td></tr>
              </table>
            </body></html>
            """,
            "html.parser",
        )
        elements = extract_html_subjects(soup, "https://example.edu/grados/sistemas/plan-de-estudios")
        credits_by_name = {item["nombre_elemento"]: item.get("creditos_ects") for item in elements}
        self.assertEqual(credits_by_name["Fundamentos de Sistemas"], "6")
        self.assertEqual(credits_by_name["Arquitectura de Computadores"], "6")
        self.assertNotIn("Todas las asignaturas tienen", credits_by_name)

    def test_extracts_parallel_html_subject_columns(self):
        """No pierde el segundo bloque de una tabla curricular en paralelo."""
        soup = BeautifulSoup(
            """
            <html><body>
              <h1>Grado en Sistemas</h1>
              <p>Todas las asignaturas tienen 6 créditos ECTS.</p>
              <table>
                <tr><td>Distribución temporal del plan</td></tr>
                <tr><th>Asignatura</th><th>Tipo</th><th>Dpto</th>
                    <th>Asignatura</th><th>Tipo</th><th>Dpto</th></tr>
                <tr><td>Fundamentos de Sistemas</td><td>FB</td><td>A</td>
                    <td>Arquitectura de Computadores</td><td>OB</td><td>B</td></tr>
              </table>
            </body></html>
            """,
            "html.parser",
        )
        elements = extract_html_subjects(soup, "https://example.edu/grados/sistemas/plan-de-estudios")
        names = {item["nombre_elemento"] for item in elements}
        self.assertEqual(names, {"Fundamentos de Sistemas", "Arquitectura de Computadores"})
        self.assertEqual({item["creditos_ects"] for item in elements}, {"6"})

    def test_marks_table_rows_as_optional_when_section_has_no_character_column(self):
        """Propaga un encabezado optativo explícito cuando la tabla no tiene tipo."""
        soup = BeautifulSoup(
            """
            <html><body>
              <h1>Grado en Sistemas</h1>
              <h2>Primer curso</h2>
              <table>
                <tr><th>Asignatura</th><th>Créditos</th></tr>
                <tr><td>Fundamentos de Sistemas</td><td>6</td></tr>
              </table>
              <h2>Optional Subjects</h2>
              <table>
                <tr><th>Subject</th><th>Credits</th></tr>
                <tr><td>Analítica Aplicada</td><td>6</td></tr>
                <tr><td>Seguridad de Sistemas</td><td>6</td></tr>
              </table>
              <h2>Segundo curso</h2>
              <table>
                <tr><th>Asignatura</th><th>Créditos</th></tr>
                <tr><td>Arquitectura de Sistemas</td><td>6</td></tr>
              </table>
            </body></html>
            """,
            "html.parser",
        )
        elements = extract_html_subjects(soup, "https://example.edu/grados/sistemas/plan")
        by_name = {item["nombre_elemento"]: item for item in elements}
        self.assertEqual(by_name["Fundamentos de Sistemas"]["caracter"], "OB")
        self.assertEqual(by_name["Analítica Aplicada"]["caracter"], "OP")
        self.assertEqual(by_name["Seguridad de Sistemas"]["caracter"], "OP")
        self.assertEqual(by_name["Arquitectura de Sistemas"]["caracter"], "OB")

        degree = {
            "nivel_academico": "Grado",
            "titulo": "Grado en Sistemas",
            "plan_estudios": {
                "elementos_curriculares": elements,
                "resumen_creditos": {"Créditos Totales": 240},
            },
        }
        status = get_curriculum_completeness_status(degree)
        self.assertEqual(status["total_ects_optativos_ofertados"], 12.0)

    def test_accepts_explicit_large_optional_offer_with_reduced_fixed_core(self):
        """Acepta un núcleo oficial suficiente cuando la oferta optativa está separada."""
        fixed_rows = "".join(
            f"<tr><td>Materia obligatoria {index}</td><td>6</td></tr>"
            for index in range(26)
        )
        optional_rows = "".join(
            f"<tr><td>Materia optativa {index}</td><td>6</td></tr>"
            for index in range(24)
        )
        soup = BeautifulSoup(
            f"""
            <html><body>
              <h1>Grado en Sistemas</h1>
              <h2>Plan obligatorio</h2>
              <table><tr><th>Asignatura</th><th>Créditos</th></tr>
                {fixed_rows}
              </table>
              <h2>Asignaturas optativas</h2>
              <table><tr><th>Asignatura</th><th>Créditos</th></tr>
                {optional_rows}
              </table>
            </body></html>
            """,
            "html.parser",
        )
        elements = extract_html_subjects(soup, "https://example.edu/grados/sistemas/plan")
        status = get_curriculum_completeness_status(
            {
                "nivel_academico": "Grado",
                "titulo": "Grado en Sistemas",
                "plan_estudios": {"elementos_curriculares": elements},
            }
        )
        self.assertEqual(status["total_ects_fijos"], 156.0)
        self.assertEqual(status["total_ects_optativos_ofertados"], 144.0)
        self.assertTrue(status["is_complete"])
        self.assertEqual(status["status"], "completo_optatividad_inferida")

    def test_specialized_curriculum_page_can_use_thematic_url_identity(self):
        """Acepta un portal docente corto solo cuando la ruta aporta el núcleo del título."""
        soup = BeautifulSoup(
            """
            <html><head><title>PLAN</title></head><body>
              <table><tr><th>Asignatura</th><th>ECTS</th></tr>
                <tr><td>Seguridad aplicada</td><td>6</td></tr>
                <tr><td>Auditoría de sistemas</td><td>6</td></tr>
                <tr><td>Trabajo final</td><td>10</td></tr>
              </table>
            </body></html>
            """,
            "html.parser",
        )
        page_url = "https://master-datos.example.edu/planestudios.html"
        self.assertTrue(
            is_html_page_matching_degree(
                soup,
                "Máster Universitario en Datos",
                "Universidad de Prueba",
                page_url,
                allow_curriculum_url_identity=True,
            )
        )
        self.assertFalse(
            is_html_page_matching_degree(
                soup,
                "Máster Universitario en Física",
                "Universidad de Prueba",
                page_url,
                allow_curriculum_url_identity=True,
            )
        )

    def test_extracts_split_mandatory_and_elective_credit_columns(self):
        """Suma créditos divididos por carácter solo cuando la cabecera lo declara."""
        soup = BeautifulSoup(
            """
            <table>
              <tr><th>Materia</th><th>Créditos Obligatorios</th><th>Créditos Optativos</th></tr>
              <tr><td>Seguridad aplicada</td><td>10,5</td><td>3</td></tr>
              <tr><td>Proyecto integrador</td><td>10</td><td></td></tr>
            </table>
            """,
            "html.parser",
        )
        elements = extract_html_subjects(soup, "https://portal.example.edu/planestudios.html")
        self.assertEqual(2, len(elements))
        self.assertEqual({"13.5", "10"}, {e["creditos_ects"] for e in elements})

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
