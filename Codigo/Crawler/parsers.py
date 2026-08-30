"""
Fachada de Compatibilidad hacia Atrás para Parsers de la Fase 1.
Re-exporta de forma transparente todas las funciones desde los nuevos módulos especializados:
- sanitizers.py (saneamiento de texto y normalización lingüística)
- curriculum_validator.py (validación curricular y créditos ECTS)
- ruct_xls_parser.py (catálogos y fichas del RUCT)
- boe_pdf_parser.py (extracción de resoluciones del BOE)
"""

from config import (
    SPANISH_STOP_WORDS,
    UMBRELLA_BRANCH_WORDS
)

from sanitizers import (
    detect_academic_language,
    unreverse_text,
    sanitize_string_value,
    sanitize_subject_name,
    curriculum_element_key,
    is_spurious_or_administrative_subject,
    is_valid_curricular_table,
    normalize_cuatrimestre,
    normalize_curso,
    classify_subject_caracter,
    extract_subjects_from_card_blocks,
    RE_MULTIPLE_SPACES
)

from curriculum_validator import (
    is_doctorate_program,
    get_required_degree_credits,
    compute_curriculum_total_ects,
    is_curriculum_complete,
    get_curriculum_completeness_status
)

from ruct_xls_parser import (
    clean_excel_code,
    parse_universities_xls,
    parse_degrees_xls,
    parse_degree_detail_html,
    extract_link_context_priority
)

from boe_pdf_parser import (
    extract_degree_core_keywords,
    is_section_matching,
    parse_boe_pdf,
    parse_header_schema,
    parse_boe_text_curriculum_dynamic,
    RE_CREDIT_SUMMARY,
    RE_DEGREE_SECTION_MARKERS,
    RE_PREAMBLE_REJECTION,
    RE_SUMMARY_LABEL,
    RE_HEADER_GARBAGE,
    RE_TABLE_HEADER_NOISE,
    RE_ECTS_NUMBER,
    _RE_DYNAMIC_TIPO_FIRST,
    _RE_DYNAMIC_CRED_FIRST
)
