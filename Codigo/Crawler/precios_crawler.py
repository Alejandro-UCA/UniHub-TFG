"""
Fachada de Compatibilidad hacia Atrás para el Crawler de Precios y Tasas Universitarias (Fase 1 Parte 3).
Re-exporta todo el motor de cálculo de precios desde fase1_parte3_precios.py.
"""

from fase1_parte3_precios import (
    compute_degree_price,
    normalize_ccaa_name,
    is_public_university,
    load_precios_ccaa,
    apply_price_info_to_degree,
    run_phase1_part3
)
