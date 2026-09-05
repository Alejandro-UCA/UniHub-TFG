import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Crawler')))

from core.config import (
    MEMORIA_VERIFICADA_KEYWORDS,
    HUB_ACADEMIC_KEYWORDS,
    HUB_AND_SPOKE_MAX_HUBS,
    HUB_AND_SPOKE_MAX_DEPTH,
    HUB_AND_SPOKE_MAX_HOPS,
    WEB_SEARCH_SUBPAGES_LIMIT
)
from pipelines.parte2_web_crawler import score_academic_candidate_url


class TestMemoriaVerificadaCrawler(unittest.TestCase):
    """
    Batería de pruebas unitarias para la priorización y rescate de
    Memorias Verificadas de Planes de Estudio (ANECA / AQU / ACCUA / SGIC).
    """

    def test_configuration_parameters_expanded(self):
        """Verifica que los parámetros de anchura y profundidad estén debidamente ampliados."""
        self.assertGreaterEqual(HUB_AND_SPOKE_MAX_HUBS, 40)
        self.assertGreaterEqual(HUB_AND_SPOKE_MAX_DEPTH, 7)
        self.assertGreaterEqual(HUB_AND_SPOKE_MAX_HOPS, 6)
        self.assertGreaterEqual(WEB_SEARCH_SUBPAGES_LIMIT, 10)
        self.assertIn("calidad", HUB_ACADEMIC_KEYWORDS)
        self.assertIn("verificacion", HUB_ACADEMIC_KEYWORDS)

    def test_memoria_verificada_keywords_present(self):
        """Comprueba que las palabras clave de acreditación y calidad incluyan términos clave."""
        essential_keywords = ["memoria", "verificad", "autoinforme", "acreditac", "sgic", "calidad"]
        for kw in essential_keywords:
            self.assertIn(kw, MEMORIA_VERIFICADA_KEYWORDS)

    def test_score_boost_memoria_verificada_urls(self):
        """Comprueba que los enlaces a Memorias Verificadas reciban puntuación prioritaria máxima (>= 95)."""
        test_cases = [
            ("https://ciencias.uca.es/wp-content/uploads/2023_G_Matematicas_MNS_Memoria_completa.pdf", "Memoria Completa Grado", "Grado"),
            ("https://www.upv.es/entidades/ETSIT/info/Memoria_GITT.pdf", "Memoria del Plan de Estudios", "Grado"),
            ("https://medicina.usal.es/calidad/memoria-de-verificacion/", "Memoria de Verificación ANECA", "Grado"),
            ("https://www.uclm.es/albacete/enfermeria/sgic/memoria-verificada", "Sistema SGIC Memoria Verificada", "Grado"),
            ("https://www.usc.es/sites/plan/memoria_dg_quimica_bioloxia_modificacion_2025.pdf", "Modificación Memoria", "Máster"),
            ("https://vrcalidad.unex.es/plan1704-memoriaplan.pdf", "Memoria Plan de Estudios", "Grado"),
            ("https://filosofia.uca.es/Autoinforme-EE.II-definitivo.pdf", "Autoinforme de Acreditación", "Grado"),
            ("https://facultad.ub.cat/calitat/verificacio-grau-informatica.pdf", "Verificació Grau", "Grado")
        ]

        for url, text, level in test_cases:
            score = score_academic_candidate_url(url, text, level, ["matematicas", "quimica", "informatica", "medicina"])
            self.assertGreaterEqual(score, 95, f"La URL '{url}' con texto '{text}' debería tener score >= 95, obtenido: {score}")

    def test_multilingual_quality_scoring(self):
        """Verifica que términos en lenguas cooficiales (qualitat, kalitatea, verificacio) otorguen prioridad alta."""
        score_cat = score_academic_candidate_url("https://www.uab.cat/qualitat/memoria-grau.pdf", "Qualitat Docent", "Grado")
        score_eus = score_academic_candidate_url("https://www.ehu.eus/kalitatea/txostena.pdf", "Kalitatea eta Memoria", "Grado")
        
        self.assertGreaterEqual(score_cat, 95)
        self.assertGreaterEqual(score_eus, 95)


if __name__ == '__main__':
    unittest.main()
