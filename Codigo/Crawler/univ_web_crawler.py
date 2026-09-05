"""
Fachada de Compatibilidad hacia Atrás para el Crawler Web de Universidades (Fase 1 Parte 2).
Re-exporta todo el motor de rastreo desde fase1_parte2_web_crawler.py.
"""

from fase1_parte2_web_crawler import (
    UniversityWebCrawler,
    score_academic_candidate_url,
    is_valid_curricular_table,
    is_spurious_or_administrative_subject,
    ensure_https_url,
    parse_price_value,
    build_html_curriculum_payload,
    is_html_page_matching_degree,
    is_source_url_level_compatible,
    is_valid_web_url,
    is_same_or_subdomain,
    is_spider_trap_or_spurious_url,
    is_dynamic_academic_hub,
    extract_breadcrumb_parent_hubs,
    extract_hydration_payload_degrees,
    extract_form_select_academic_options,
    extract_js_event_links,
    extract_html_subjects,
    extract_private_university_pricing,
    propagate_interuniversity_and_shared_boe_plans,
    run_phase1_part2
)
