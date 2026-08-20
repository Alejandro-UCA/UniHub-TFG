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

if __name__ == "__main__":
    unittest.main(verbosity=2)
