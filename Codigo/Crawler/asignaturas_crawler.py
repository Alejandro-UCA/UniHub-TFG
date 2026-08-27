"""
Fachada de Compatibilidad hacia Atrás para el Crawler de Guías Docentes y Temarios (Fase 1 Parte 4).
Re-exporta todo el motor de guías docentes desde fase1_parte4_asignaturas.py.
"""

import fase1_parte4_asignaturas as _implementation

from fase1_parte4_asignaturas import (
    SubjectGuideCache,
    generate_subject_slug,
    resolve_candidate_subject_guide_urls,
    parse_uca_subject_guide,
    parse_generic_eees_subject_guide,
    parse_subject_guide_pdf_stream,
    parse_subject_guide,
)

PLANES_DIR = _implementation.PLANES_DIR


def run_phase1_part4(*args, **kwargs):
    """Delega en la Parte 4 conservando el punto de parcheo histórico."""
    previous_planes_dir = _implementation.PLANES_DIR
    _implementation.PLANES_DIR = PLANES_DIR
    try:
        return _implementation.run_phase1_part4(*args, **kwargs)
    finally:
        _implementation.PLANES_DIR = previous_planes_dir
