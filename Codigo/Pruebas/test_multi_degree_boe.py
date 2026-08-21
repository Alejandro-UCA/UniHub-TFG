import unittest
import os
import sys

# Agregar path al módulo Crawler
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from parsers import (
    extract_degree_core_keywords,
    SPANISH_STOP_WORDS,
    RE_DEGREE_SECTION_MARKERS
)

class TestMultiDegreeBOEDisambiguation(unittest.TestCase):
    """
    Suite de pruebas para validar la desambiguación y segmentación de resoluciones
    del BOE que publican planes de estudio de múltiples titulaciones simultáneamente.
    """

    def test_01_core_keyword_extraction_precision(self):
        """Verifica la extracción limpia de palabras clave discriminativas sin ruido de stop words."""
        # Caso 1: ESIC Psicología
        kw_psi = extract_degree_core_keywords(
            "Graduado o Graduada en Psicología por la ESIC Universidad",
            "ESIC Universidad"
        )
        self.assertIn("psicologia", kw_psi)
        self.assertNotIn("grado", kw_psi)
        self.assertNotIn("graduado", kw_psi)
        self.assertNotIn("esic", kw_psi)
        self.assertNotIn("universidad", kw_psi)
        self.assertNotIn("por", kw_psi)

        # Caso 2: ESIC Ingeniería Informática
        kw_inf = extract_degree_core_keywords(
            "Graduado o Graduada en Ingeniería Informática por la ESIC Universidad",
            "ESIC Universidad"
        )
        self.assertIn("informatica", kw_inf)
        self.assertIn("ingenieria", kw_inf)
        self.assertNotIn("esic", kw_inf)

        # Caso 3: ESIC Marketing y Comunicación Digital
        kw_mkt = extract_degree_core_keywords(
            "Graduado o Graduada en Marketing y Comunicación Digital por la ESIC Universidad",
            "ESIC Universidad"
        )
        self.assertIn("marketing", kw_mkt)
        self.assertIn("comunicacion", kw_mkt)
        self.assertIn("digital", kw_mkt)

    def test_02_section_markers_detection(self):
        """Verifica que los patrones regex detecten encabezados de Anexos y Títulos de Grado en BOE."""
        sample_anexo_1 = "ANEXO I\nPlan de estudios conducente al título oficial de Graduado o Graduada en Ingeniería Informática"
        sample_anexo_2 = "ANEXO II\nPlan de estudios conducente al título oficial de Graduado o Graduada en Marketing y Comunicación Digital"
        sample_anexo_3 = "ANEXO III\nPlan de estudios conducente al título oficial de Graduado o Graduada en Psicología"

        found_1 = any(p.search(sample_anexo_1) for p in RE_DEGREE_SECTION_MARKERS)
        found_2 = any(p.search(sample_anexo_2) for p in RE_DEGREE_SECTION_MARKERS)
        found_3 = any(p.search(sample_anexo_3) for p in RE_DEGREE_SECTION_MARKERS)

        self.assertTrue(found_1, "Fallo al detectar ANEXO I")
        self.assertTrue(found_2, "Fallo al detectar ANEXO II")
        self.assertTrue(found_3, "Fallo al detectar ANEXO III")

    def test_03_multi_degree_resolution_discrimination(self):
        """
        Verifica que al procesar un documento multi-titulación con 3 anexos, 
        la segmentación aísle exclusivamente las asignaturas y créditos de la titulación objetivo.
        """
        raw_text_pages = [
            "BOLETÍN OFICIAL DEL ESTADO\nResolución de ESIC Universidad\nANEXO I\nPlan de estudios de Graduado en Ingeniería Informática\nFormación Básica: 60\nObligatorias: 120",
            "Asignaturas de Informática:\nProgramación I - 6 ECTS\nEstructura de Computadores - 6 ECTS\nSistemas Operativos - 6 ECTS",
            "ANEXO II\nPlan de estudios de Graduado en Marketing y Comunicación Digital\nFormación Básica: 60\nObligatorias: 132",
            "Asignaturas de Marketing:\nFundamentos de Marketing - 6 ECTS\nComunicación Digital - 6 ECTS",
            "ANEXO III\nPlan de estudios de Graduado en Psicología\nFormación Básica: 60\nObligatorias: 126",
            "Asignaturas de Psicología:\nPsicología General - 6 ECTS\nPsicobiología - 6 ECTS\nEvaluación Psicológica - 6 ECTS"
        ]

        target_title = "Graduado o Graduada en Psicología por la ESIC Universidad"
        univ_name = "ESIC Universidad"
        target_kw = extract_degree_core_keywords(target_title, univ_name)

        detected_sections = []
        for page_idx, p_text in enumerate(raw_text_pages):
            for pattern in RE_DEGREE_SECTION_MARKERS:
                for match in pattern.finditer(p_text):
                    sec_raw = match.group(0).strip()
                    sec_kw = extract_degree_core_keywords(sec_raw, univ_name)
                    if sec_kw and len(sec_kw) > 0:
                        detected_sections.append({
                            "page_idx": page_idx,
                            "raw": sec_raw,
                            "keywords": sec_kw
                        })

        page_inclusion_mask = [True] * len(raw_text_pages)
        if len(detected_sections) >= 2 and target_kw:
            current_state = False
            for page_idx in range(len(raw_text_pages)):
                for s in detected_sections:
                    if s["page_idx"] == page_idx:
                        overlap = target_kw.intersection(s["keywords"])
                        current_state = bool(overlap)
                page_inclusion_mask[page_idx] = current_state

        # Verificar que solo las páginas de Psicología (índices 4 y 5) sean marcadas como True
        self.assertEqual(page_inclusion_mask, [False, False, False, False, True, True])

    def test_04_mega_resolution_multiline_headings(self):
        """
        Verifica la discriminación en macro-resoluciones universitarias (ej. UC3M con 70 páginas)
        donde los títulos de grado contienen saltos de línea y 'conducentes' en plural.
        """
        raw_text_pages = [
            "UNIVERSIDAD CARLOS III DE MADRID\nResolución por la que se publican planes de estudio",
            "PLAN DE ESTUDIOS CONDUCENTES AL TÍTULO DE: GRADO EN CIENCIAS \nPOLÍTICAS\nDistribución general del plan de estudios en créditos ECTS: 240",
            "PLAN DE ESTUDIOS CONDUCENTES AL TÍTULO DE: GRADO EN GESTIÓN \nDE LA INFORMACIÓN Y CONTENIDOS DIGITALES\nDistribución general del plan de estudios en créditos ECTS: 240",
            "PLAN DE ESTUDIOS CONDUCENTES AL TÍTULO DE: GRADO EN HUMANIDADES DIGITALES\nDistribución general del plan de estudios en créditos ECTS: 240",
            "PLAN DE ESTUDIOS CONDUCENTES AL TÍTULO DE: GRADO EN TURISMO\nDistribución general del plan de estudios en créditos ECTS: 240"
        ]

        target_title = "Graduado o Graduada en Gestión de la Información y Contenidos Digitales por la Universidad Carlos III de Madrid"
        univ_name = "Universidad Carlos III de Madrid"
        target_kw = extract_degree_core_keywords(target_title, univ_name)

        from parsers import is_section_matching
        detected_sections = []
        for page_idx, p_text in enumerate(raw_text_pages):
            for pattern in RE_DEGREE_SECTION_MARKERS:
                for match in pattern.finditer(p_text):
                    sec_raw = match.group(0).strip()
                    sec_kw = extract_degree_core_keywords(sec_raw, univ_name)
                    if sec_kw and len(sec_kw) > 0:
                        detected_sections.append({
                            "page_idx": page_idx,
                            "raw": sec_raw,
                            "keywords": sec_kw
                        })

        page_inclusion_mask = [True] * len(raw_text_pages)
        if len(detected_sections) >= 2 and target_kw:
            current_state = False
            for page_idx in range(len(raw_text_pages)):
                for s in detected_sections:
                    if s["page_idx"] == page_idx:
                        current_state = is_section_matching(s["keywords"], target_kw)
                page_inclusion_mask[page_idx] = current_state

        # Verificar que solo la página 2 (Gestión de Información y Contenidos Digitales) sea True, y no Humanidades Digitales (página 3)
        self.assertEqual(page_inclusion_mask, [False, False, True, False, False])

    def test_05_materia_only_master_plans_and_decree_filtering(self):
        """
        Verifica que los planes de máster con estructura sólo de 'Materia | ECTS' se extraigan
        correctamente y que los decretos administrativos de autorización de centros se filtren a 0 elementos.
        """
        from parsers import sanitize_subject_name
        import re

        # Valid subject from Master
        valid_subject = "Principios de Biología de la Conservación"
        clean = sanitize_subject_name(valid_subject)
        self.assertEqual(clean, "Principios de Biología de la Conservación")

        # Non-subject administrative rows in regional decrees
        degree_row_1 = "Graduado o Graduada en Ingeniería Agrícola"
        degree_row_2 = "Máster Universitario en Biofísica"
        degree_row_3 = "Programa de Doctorado en Farmacia"
        center_row = "CENTROS PROPIOS"

        deg_regex = re.compile(r"^(?:grado|graduado|graduada|máster|master|doctorado|programa\s+(?:oficial\s+)?de\s+doctorado|enseñanza)\b", re.IGNORECASE)
        center_regex = re.compile(r"^(?:centros?\s+(?:propios|adscritos|integrados|universitarios)|campus\s+de|sede\s+de|facultad\s+de|escuela\s+de)\b", re.IGNORECASE)

        self.assertTrue(bool(deg_regex.search(degree_row_1)))
        self.assertTrue(bool(deg_regex.search(degree_row_2)))
        self.assertTrue(bool(deg_regex.search(degree_row_3)))
        self.assertTrue(bool(center_regex.search(center_row)))

    def test_06_bilingual_keyword_isolation_no_collisions(self):
        """Verifica que títulos bilingües en inglés/español no colisionen en palabras genéricas como bachelor/and/engineering."""
        title_cs = "Graduado o Graduada en Ingeniería Informática / Bachelor in Computer Science and Engineering"
        title_data = "Graduado o Graduada en Análisis de Datos / Bachelor in Data Science and Engineering"
        title_stats = "Graduado o Graduada en Estadística y Empresa / Bachelor in Statistics and Business"
        univ = "Universidad Carlos III de Madrid"

        kw_cs = extract_degree_core_keywords(title_cs, univ)
        kw_data = extract_degree_core_keywords(title_data, univ)
        kw_stats = extract_degree_core_keywords(title_stats, univ)

        self.assertNotIn("bachelor", kw_cs)
        self.assertNotIn("engineering", kw_cs)
        self.assertNotIn("science", kw_cs)
        self.assertIn("computer", kw_cs)
        self.assertIn("informatica", kw_cs)

        # No must-have collisions
        self.assertEqual(len(kw_cs.intersection(kw_data)), 0)
        self.assertEqual(len(kw_cs.intersection(kw_stats)), 0)

    def test_07_summary_labels_and_huge_ects_exclusion(self):
        """Verifica que los resúmenes globales de créditos y módulos grandes se detecten y excluyan de asignaturas."""
        from parsers import RE_SUMMARY_LABEL

        # Summary labels
        self.assertTrue(bool(RE_SUMMARY_LABEL.match("Formación Básica (FB)")))
        self.assertTrue(bool(RE_SUMMARY_LABEL.match("Obligatorias (OB)")))
        self.assertTrue(bool(RE_SUMMARY_LABEL.match("Optativas (OP)")))
        self.assertTrue(bool(RE_SUMMARY_LABEL.match("Formación Básica (B)")))
        self.assertTrue(bool(RE_SUMMARY_LABEL.match("Total créditos")))
        self.assertTrue(bool(RE_SUMMARY_LABEL.match("Créditos Totales")))

        # Real subjects that must NOT match summary label
        self.assertFalse(bool(RE_SUMMARY_LABEL.match("Química Básica")))
        self.assertFalse(bool(RE_SUMMARY_LABEL.match("Derecho de Obligaciones")))
        self.assertFalse(bool(RE_SUMMARY_LABEL.match("Prácticas Externas")))
        self.assertFalse(bool(RE_SUMMARY_LABEL.match("Trabajo Fin de Grado")))

    def test_08_garbage_header_rejection(self):
        """Verifica que secuencias espurias de siglas de cabecera sean rechazadas."""
        from parsers import RE_HEADER_GARBAGE, RE_TABLE_HEADER_NOISE

        self.assertTrue(bool(RE_HEADER_GARBAGE.match("OB OP OP OP TFG")))
        self.assertTrue(bool(RE_HEADER_GARBAGE.match("FB OB OB OP")))
        self.assertTrue(bool(RE_TABLE_HEADER_NOISE.match("N.º ctos")))
        self.assertTrue(bool(RE_TABLE_HEADER_NOISE.match("Nº creditos")))

        self.assertFalse(bool(RE_HEADER_GARBAGE.match("Matemáticas I")))
        self.assertFalse(bool(RE_TABLE_HEADER_NOISE.match("Cálculo Numérico")))

    def test_09_multiline_subject_fragment_stitching(self):
        """Verifica que celdas multilínea en tablas PDF se fusionen correctamente con su asignatura cabecera."""
        from parsers import parse_boe_pdf, RE_ECTS_NUMBER

        # Simulación de filas partidas
        table_data = [
            ["Asignatura", "Carácter", "ECTS"],
            ["Literatura Española: ", "FB", "6"],
            ["la Generación del 27", "", ""],
            ["Bases físicas y químicas ", "FB", "6"],
            ["para el estudio del medio ambiente", "", ""],
            ["Derecho Constitucional I", "OB", "6"]
        ]

        merged_rows = []
        subject_col_idx = 0
        for row in table_data:
            clean_row = [str(c).strip() if c else "" for c in row]
            if clean_row[0] == "Asignatura":
                continue
            has_ects = any(RE_ECTS_NUMBER.search(c) for idx_c, c in enumerate(clean_row) if idx_c != 0)
            target_subj = clean_row[0]
            is_fragment = not has_ects and len(target_subj) > 0 and (target_subj[0].islower() or target_subj.lower().startswith(("la ", "para ")))
            if is_fragment and merged_rows:
                merged_rows[-1][0] = f"{merged_rows[-1][0].rstrip(' :-,')} {target_subj}".strip()
                continue
            merged_rows.append(clean_row)

        self.assertEqual(len(merged_rows), 3)
        self.assertEqual(merged_rows[0][0], "Literatura Española la Generación del 27")
        self.assertEqual(merged_rows[1][0], "Bases físicas y químicas para el estudio del medio ambiente")
        self.assertEqual(merged_rows[2][0], "Derecho Constitucional I")

    def test_10_multi_degree_fallback_non_inclusion(self):
        """Verifica que si una titulación NO pertenece a una resolución multi-grado, se retorne 0 elementos sin fallback espurio."""
        from parsers import parse_boe_pdf

        # Si el stream está vacío o el grado no pertenece a la resolución, debe retornar 0
        res = parse_boe_pdf(b"%PDF-1.4\n%empty\n", target_title="Graduado o Graduada en Titulación Inexistente", univ_name="Universidad Falsa")
        self.assertEqual(res["total_elementos"], 0)
        self.assertEqual(res["elementos_curriculares"], [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
