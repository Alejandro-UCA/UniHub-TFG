import unittest
import os
import sys
import tempfile
import io
import sqlite3
import inspect
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from bs4 import BeautifulSoup
import pypdf
import fase1_parte4_asignaturas as phase4

from asignaturas_crawler import (
    parse_tabular_subject_guide,
    parse_generic_eees_subject_guide,
    parse_subject_guide,
    parse_subject_guide_pdf_stream,
    resolve_candidate_subject_guide_urls,
    generate_subject_slug,
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

    def test_limited_plan_selection_prioritizes_usable_verified_curriculum(self):
        items = [
            {"data": {"codigo_estudio": "SPARSE", "estado_fuente": "sin_plan_actual_sin_dato"}},
            {
                "data": {
                    "codigo_estudio": "VERIFIED",
                    "estado_fuente": "verificada",
                    "plan_estudios": {
                        "plan_completo": True,
                        "elementos_curriculares": [
                            {"nombre_elemento": "Álgebra"},
                            {"nombre_elemento": "Cálculo"},
                        ],
                    },
                }
            },
        ]

        selected, skipped = phase4._select_plan_items_for_limit(items, 1)

        self.assertEqual(selected[0]["data"]["codigo_estudio"], "VERIFIED")
        self.assertEqual(skipped, 1)

    def test_limited_plan_selection_prefers_curricular_candidate_over_sparse_record(self):
        items = [
            {"data": {"codigo_estudio": "SPARSE", "estado_fuente": "sin_plan_actual_sin_dato"}},
            {
                "data": {
                    "codigo_estudio": "CANDIDATE",
                    "candidato_plan_estudios": {
                        "elementos_curriculares": [{"nombre_elemento": "Historia"}]
                    },
                }
            },
        ]

        selected, skipped = phase4._select_plan_items_for_limit(items, 1)

        self.assertEqual(selected[0]["data"]["codigo_estudio"], "CANDIDATE")
        self.assertEqual(skipped, 1)

    def test_unlimited_plan_selection_preserves_all_items(self):
        items = [{"data": {"codigo_estudio": "A"}}, {"data": {"codigo_estudio": "B"}}]

        selected, skipped = phase4._select_plan_items_for_limit(items, None)

        self.assertEqual([item["data"]["codigo_estudio"] for item in selected], ["A", "B"])
        self.assertEqual(skipped, 0)

    def test_guide_request_failures_classify_http_statuses(self):
        stats = {"guide_http_404": 0, "guide_http_other": 0, "guide_request_errors": 0}

        phase4._record_guide_request_failure(stats, RuntimeError("HTTP 404 para 'https://uni.es/guide'"))
        phase4._record_guide_request_failure(stats, RuntimeError("HTTP 403 para 'https://uni.es/guide'"))
        phase4._record_guide_request_failure(stats, RuntimeError("Connection reset by peer"))

        self.assertEqual(stats, {"guide_http_404": 1, "guide_http_other": 1, "guide_request_errors": 1})

    def test_domain_metrics_are_generic_and_mergeable(self):
        stats = {}
        phase4._domain_metrics(stats, "https://Portal.Example/guia/1")["http_200"] += 1
        phase4._domain_metrics(stats, "https://portal.example/guia/2")["http_404"] += 2
        merged = {}
        phase4._merge_domain_metrics(merged, stats["by_domain"])

        self.assertEqual(merged["portal.example"]["http_200"], 1)
        self.assertEqual(merged["portal.example"]["http_404"], 2)

    def test_generate_subject_slug(self):
        self.assertEqual(generate_subject_slug("Álgebra Lineal y Geometría"), "Algebra-Lineal-y-Geometria")
        self.assertEqual(generate_subject_slug("Programación Orientada a Objetos"), "Programacion-Orientada-a-Objetos")
        self.assertEqual(generate_subject_slug("Cálculo I (Grado)"), "Calculo-I-Grado")

    def test_resolve_candidate_subject_guide_urls(self):
        elem = {
            "nombre_elemento": "Álgebra Lineal",
            "codigo_asignatura": "350000",
            "url_guia_docente": "https://www.uah.es/es/estudios/asignatura/Algebra-Lineal-350000/"
        }
        urls = resolve_candidate_subject_guide_urls(elem, u_code="002", u_web="https://www.uah.es", d_code="G350")
        self.assertTrue(len(urls) >= 1)
        self.assertIn("https://www.uah.es/es/estudios/asignatura/Algebra-Lineal-350000/", urls)
        self.assertTrue(any("350000" in u for u in urls))

    def test_explicit_evidence_reduces_heuristic_candidate_budget(self):
        urls = resolve_candidate_subject_guide_urls(
            {
                "nombre_elemento": "Álgebra Lineal",
                "codigo_asignatura": "350000",
                "url_guia_docente": "https://www.uah.es/guia/350000",
            },
            u_code="002",
            u_web="https://www.uah.es",
        )
        self.assertLessEqual(len(urls), 4)

    def test_no_evidence_keeps_generic_candidate_budget_bounded(self):
        urls = resolve_candidate_subject_guide_urls(
            {
                "nombre_elemento": "Álgebra Lineal",
                "codigo_asignatura": "350000",
            },
            u_code="002",
            u_web="https://portal.example",
        )

        self.assertLessEqual(len(urls), 4)

    def test_url_resolver_has_no_university_code_branches(self):
        source = inspect.getsource(resolve_candidate_subject_guide_urls)

        self.assertNotIn("u_code_padded ==", source)
        self.assertNotIn("u_code_padded in", source)
        self.assertNotIn("sevius.us.es", source)
        self.assertNotIn("secretariavirtual.", source)

    def test_parse_tabular_subject_guide(self):
        soup = BeautifulSoup(SAMPLE_UCA_HTML, "html.parser")
        res = parse_tabular_subject_guide(soup, "https://portal.example/2025-26/21714009")

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

    def test_unified_html_parser_selects_strategy_by_content_not_domain(self):
        content = SAMPLE_UCA_HTML.encode("utf-8")
        from_native_domain = parse_subject_guide(
            "https://portal.example/guia/21714009", content, "text/html"
        )

        self.assertEqual(from_native_domain["codigo_asignatura"], "21714009")
        self.assertEqual(from_native_domain["creditos"]["total_ects"], 6.0)
        self.assertEqual(len(from_native_domain["temario"]), 2)

    def test_parse_generic_eees_guide(self):
        soup = BeautifulSoup(SAMPLE_GENERIC_EEES_HTML, "html.parser")
        res = parse_generic_eees_subject_guide(soup, "https://fib.upc.edu/eda")

        self.assertEqual(res["nombre_asignatura"], "Estructura de Dades i Algorismes")
        self.assertEqual(len(res["temario"]), 3)
        self.assertIn("Tema 1. Anàlisi de complexitat", res["temario"][0]["titulo"])
        self.assertIn("Avaluació continuada", res["criterios_evaluacion"])
        self.assertEqual(len(res["profesorado"]), 2)
        self.assertEqual(len(res["bibliografia"]), 2)

    def test_parse_generic_guide_recovers_heterogeneous_metadata_and_outcomes(self):
        html = """
        <html><head><meta property="og:title" content="Sistemas Distribuidos" /></head><body>
          <table class="facts">
            <tr><th>Código</th><td> SD1234 </td></tr>
            <tr><th>Créditos ECTS</th><td>6</td></tr>
            <tr><th>Departamento</th><td>Ingeniería Informática</td></tr>
            <tr><th>Idioma</th><td>Castellano e inglés</td></tr>
          </table>
          <h2>Contenidos</h2><ul><li>Arquitecturas distribuidas</li><li>Consistencia y replicación</li></ul>
          <h2>Evaluación</h2><table><tr><th>Examen final</th><td>60%</td></tr></table>
          <h2>Resultados de aprendizaje</h2><ul><li>RA1 - Diseñar sistemas distribuidos tolerantes a fallos</li></ul>
        </body></html>
        """
        res = parse_generic_eees_subject_guide(
            BeautifulSoup(html, "html.parser"),
            "https://universidad.example/guia/sd1234",
        )

        self.assertEqual(res["nombre_asignatura"], "Sistemas Distribuidos")
        self.assertEqual(res["codigo_asignatura"], "SD1234")
        self.assertEqual(res["creditos"]["total_ects"], 6.0)
        self.assertEqual(res["departamento"], "Ingeniería Informática")
        self.assertEqual(res["idioma"], "Castellano e inglés")
        self.assertEqual(len(res["temario"]), 2)
        self.assertEqual(res["sistema_evaluacion"][0]["ponderacion_porcentaje"], 60.0)
        self.assertEqual(res["resultados_aprendizaje"][0]["codigo"], "RA1")

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

            # 1. Recuperar por URL exacta
            cached = cache.get(url=url)
            self.assertIsNotNone(cached)
            self.assertEqual(cached["codigo"], "21714009")
            self.assertEqual(len(cached["temario"]), 2)

            # 2. Recuperar por clave compuesta (universidad + código de asignatura)
            cached_by_code = cache.get(u_code="025", asig_code="21714009")
            self.assertIsNotNone(cached_by_code)
            self.assertEqual(cached_by_code["codigo"], "21714009")

            # URL no existente devuelve None
            self.assertIsNone(cache.get("https://asignaturas.uca.es/2025-26/99999999"))
        finally:
            try:
                if os.path.exists(db_path):
                    os.remove(db_path)
            except Exception:
                pass

    def test_subject_guide_cache_isolates_same_subject_code_by_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = SubjectGuideCache(db_path=os.path.join(directory, "guides.db"))
            try:
                cache.set(
                    "https://uni.es/plan-a/asig-1234",
                    {"codigo_asignatura": "1234", "nombre_asignatura": "Álgebra A"},
                    u_code="099", asig_code="1234", degree_code="PLAN-A",
                    academic_year="2025-26", language="es",
                )
                cache.set(
                    "https://uni.es/plan-b/asig-1234",
                    {"codigo_asignatura": "1234", "nombre_asignatura": "Álgebra B"},
                    u_code="099", asig_code="1234", degree_code="PLAN-B",
                    academic_year="2025-26", language="es",
                )
                self.assertEqual(
                    cache.get(u_code="099", asig_code="1234", degree_code="PLAN-A", academic_year="2025-26", language="es")["nombre_asignatura"],
                    "Álgebra A",
                )
                self.assertEqual(
                    cache.get(u_code="099", asig_code="1234", degree_code="PLAN-B", academic_year="2025-26", language="es")["nombre_asignatura"],
                    "Álgebra B",
                )
            finally:
                cache.close()

    def test_subject_guide_cache_migrates_legacy_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "legacy.db")
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE guias_docentes (url_hash TEXT PRIMARY KEY, url TEXT NOT NULL, "
                "universidad_codigo TEXT, codigo_asignatura TEXT, nombre TEXT, datos_json TEXT NOT NULL, "
                "fecha_extraccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            connection.commit()
            connection.close()
            cache = SubjectGuideCache(db_path=db_path)
            try:
                connection = sqlite3.connect(db_path)
                try:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(guias_docentes)")}
                finally:
                    connection.close()
                self.assertTrue({"codigo_estudio", "curso_academico", "idioma"}.issubset(columns))
                cache.set("https://uni.es/guide", {"nombre_asignatura": "Historia"}, "099", "1234", "Historia", degree_code="PLAN-A", academic_year="2025-26", language="es")
                self.assertEqual(cache.get(u_code="099", asig_code="1234", degree_code="PLAN-A", academic_year="2025-26", language="es")["nombre_asignatura"], "Historia")
            finally:
                cache.close()

    def test_subject_guide_cache_expires_persisted_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "guides.db")
            cache = SubjectGuideCache(db_path=db_path)
            cache.set(
                "https://uni.es/guide/1234",
                {"codigo_asignatura": "1234", "nombre_asignatura": "Historia"},
                u_code="099", asig_code="1234", degree_code="PLAN-A",
                academic_year="2025-26", language="es",
            )
            cache.close()

            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "UPDATE guias_docentes SET fecha_extraccion = ?",
                    ("2000-01-01 00:00:00",),
                )
                connection.commit()
            finally:
                connection.close()

            with patch.object(phase4, "SUBJECT_GUIDE_CACHE_TTL_SECONDS", 60):
                expired_cache = SubjectGuideCache(db_path=db_path)
                try:
                    self.assertIsNone(expired_cache.get(url="https://uni.es/guide/1234"))
                    self.assertIsNone(
                        expired_cache.get(
                            u_code="099", asig_code="1234", degree_code="PLAN-A",
                            academic_year="2025-26", language="es",
                        )
                    )
                finally:
                    expired_cache.close()

    def test_normalize_evaluation_breakdown(self):
        from fase1_parte4_asignaturas import _normalize_evaluation_breakdown
        guide = {
            "sistema_evaluacion": [
                {"tarea": "Examen final escrito", "instrumentos": "Prueba objetiva", "ponderacion_porcentaje": 60.0},
                {"tarea": "Prácticas de laboratorio", "instrumentos": "Informes semanales", "ponderacion_porcentaje": 30.0},
                {"tarea": "Evaluación continua y participación", "instrumentos": "Cuestionarios", "ponderacion_porcentaje": 10.0},
            ]
        }
        breakdown = _normalize_evaluation_breakdown(guide)
        self.assertEqual(breakdown["examen_final_porcentaje"], 60.0)
        self.assertEqual(breakdown["practicas_porcentaje"], 30.0)
        self.assertEqual(breakdown["evaluacion_continua_porcentaje"], 10.0)

    def test_infer_subject_guide_language(self):
        from fase1_parte4_asignaturas import _infer_subject_guide_language
        ca_guide = {
            "nombre_asignatura": "Estructures de Dades i Algorismes",
            "temario": [{"titulo": "Pla docent i continguts de lassignatura", "contenidos": []}],
            "criterios_evaluacion": "Avaluacio continuada i criteris davaluacio",
        }
        self.assertEqual(_infer_subject_guide_language(ca_guide), "Català")

        es_guide = {
            "nombre_asignatura": "Estructura de Datos y Algoritmos",
            "temario": [{"titulo": "Contenidos teóricos y prácticos", "contenidos": []}],
            "criterios_evaluacion": "Examen final y evaluación continua",
        }
        self.assertEqual(_infer_subject_guide_language(es_guide), "Castellano")


if __name__ == "__main__":
    unittest.main()
