"""Pruebas unitarias para poda de URLs hipotéticas ciegas y prevención de errores HTTP 404."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from pipelines.parte4_asignaturas import resolve_candidate_subject_guide_urls


class TestGuidePruningAnti404(unittest.TestCase):
    """Verifica que no se generen decenas de URLs a subdominios inexistentes sin evidencia."""

    def test_prunes_blind_subdomains_without_evidence(self):
        elem = {
            "codigo_asignatura": "700101",
            "nombre_elemento": "Estructuras de Datos",
        }
        # Universidad sin subdominios descubiertos: solo portal canónico
        candidates = resolve_candidate_subject_guide_urls(
            elem=elem,
            u_code="001",
            u_web="https://www.uned.es",
            d_code="2500123",
            academic_year="2025-2026",
            discovery_index=None,
        )

        cand_str = " ".join(candidates)
        # NO debe contener subdominios ciegos hipotéticos como secretaria.uned.es, guiasdocentes.uned.es, cv1.cpd.uned.es, sia.uned.es
        self.assertNotIn("secretaria.uned.es", cand_str)
        self.assertNotIn("cv1.cpd.uned.es", cand_str)
        self.assertNotIn("guiasdocentes.uned.es", cand_str)
        self.assertNotIn("sia.uned.es", cand_str)
        # SÍ debe contener rutas en el dominio verificado
        self.assertTrue(any("uned.es" in c for c in candidates))

    def test_allows_subdomains_present_in_discovery_index(self):
        elem = {
            "codigo_asignatura": "800202",
            "nombre_elemento": "Física Cuántica",
        }
        # Índice de descubrimiento que contiene guias.ucm.es
        discovery_index = {
            "records": [
                {"url": "https://guias.ucm.es/catalogo/index.html"},
            ]
        }
        candidates = resolve_candidate_subject_guide_urls(
            elem=elem,
            u_code="002",
            u_web="https://www.ucm.es",
            d_code="2500456",
            academic_year="2025-2026",
            discovery_index=discovery_index,
        )
        cand_str = " ".join(candidates)
        # Debe haber generado URLs sobre guias.ucm.es porque fue descubierta
        self.assertIn("guias.ucm.es", cand_str)
        # Pero NO debe haber generado sobre sia.ucm.es ni cv1.cpd.ucm.es
        self.assertNotIn("sia.ucm.es", cand_str)
        self.assertNotIn("cv1.cpd.ucm.es", cand_str)


if __name__ == "__main__":
    unittest.main()
