import os
import sys
import re
import json
import time
import gzip
import logging
import threading
import heapq
import itertools
import requests
import urllib.parse
import warnings
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import concurrent.futures
import unicodedata
from datetime import datetime
from collections import defaultdict, deque

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger("unihub_web_crawler")


def _persist_canonical_university_url(university_code: str, previous_url: str, canonical_url: str) -> None:
    """Conserva la URL registrada y guarda la URL canónica descubierta."""
    previous = str(previous_url or "").rstrip("/")
    canonical = str(canonical_url or "").rstrip("/")
    if not canonical or canonical.lower() == previous.lower() or not os.path.exists(UNIVERSIDADES_JSON):
        return
    try:
        with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as handle:
            universities = json.load(handle)
        changed = False
        for university in universities if isinstance(universities, list) else []:
            if str(university.get("codigo") or "").zfill(3) != str(university_code or "").zfill(3):
                continue
            university.setdefault("web_url_registrada", previous_url)
            university["web"] = canonical_url
            university["web_canonica_descubierta"] = True
            university["web_canonica_fecha"] = datetime.now().isoformat()
            changed = True
            break
        if changed:
            atomic_json_dump(universities, UNIVERSIDADES_JSON)
            logger.info("[FUENTE CANÓNICA] URL institucional actualizada: %s -> %s", previous_url, canonical_url)
    except (OSError, TypeError, ValueError) as error:
        logger.warning("No se pudo guardar la URL canónica institucional: %s", error)


def _annotate_plan_source_status(
    degrees: list,
    university_code: str,
    status: str,
    university_name: str = "",
) -> None:
    """Registra por qué se conserva un plan anterior durante una revalidación."""
    checked_at = datetime.now().isoformat()
    for degree in degrees or []:
        if not isinstance(degree, dict):
            continue
        d_code = str(degree.get("codigo_estudio") or "").strip()
        if not d_code:
            continue
        path = find_plan_filepath(university_code, d_code)
        data = load_json_safe(path, default=None)
        if not isinstance(data, dict):
            data = {}
        # Una actualización de estado nunca puede convertir el registro en un
        # JSON esquelético. La identidad procede del catálogo RUCT y se repone
        # incluso cuando la búsqueda web no encontró contenido curricular.
        identity = {
            "codigo_estudio": d_code,
            "titulo": str(degree.get("titulo") or "").strip(),
            "nivel_academico": str(degree.get("nivel_academico") or "").strip(),
            "universidad_codigo": str(university_code or "").zfill(3),
            "universidad_nombre": str(
                degree.get("universidad_nombre") or university_name or ""
            ).strip(),
        }
        for key, value in identity.items():
            if value and not str(data.get(key) or "").strip():
                data[key] = value
        data.setdefault("plan_estudios", None)
        data["estado_fuente"] = status if data.get("plan_estudios") else status.replace("conservando_anterior", "sin_dato")
        data["fecha_ultima_comprobacion_fuente"] = checked_at
        atomic_json_dump(data, path)

from config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    get_plan_filepath,
    find_plan_filepath,
    USER_AGENT,
    REQUEST_DELAY,
    HTTP_TIMEOUT,
    WEB_ROBOTS_FALLBACK_DELAY,
    SITEMAP_FETCH_TIMEOUT,
    WEB_CONNECTIVITY_TIMEOUT,
    WEB_CONTENT_TIMEOUT,
    WEB_DEGREE_TIMEOUT_SECONDS,
    WEB_PROBE_DELAY,
    WEB_SEARCH_SUBPAGES_LIMIT,
    PRIVATE_ECTS_MIN,
    PRIVATE_ECTS_MAX,
    PRIVATE_ANNUAL_MIN,
    PRIVATE_ANNUAL_MAX,
    WEB_CRAWLER_WORKERS,
    ROBOTS_CACHE_TTL_SECONDS,
    ROBOTS_DENIED_RETRY_TTL_SECONDS,
    LAZY_SCANNED_PAGES_CACHE_LIMIT,
    ROBOTS_CHECK_TIMEOUT,
    HUB_AND_SPOKE_MAX_HUBS,
    HUB_AND_SPOKE_MAX_DEPTH,
    HUB_AND_SPOKE_MAX_HOPS,
    HUB_AND_SPOKE_MIN_PRIORITY,
    HUB_AND_SPOKE_MAX_INDEXED_URLS,
    HUB_AND_SPOKE_MAX_LINKS_PER_TOKEN,
    DYNAMIC_HUB_MIN_SIBLINGS,
    DYNAMIC_HUB_MIN_TITLE_WORDS,
    DYNAMIC_HUB_MAX_TITLE_WORDS,
    SPIDER_TRAP_PATH_MARKERS,
    HUB_ACADEMIC_KEYWORDS,
    MEMORIA_VERIFICADA_KEYWORDS,
    ACADEMIC_SUBPAGE_KEYWORDS,
    INVALID_METADATA_LABELS,
    ACADEMIC_SUBDOMAIN_PREFIXES,
    NON_ACADEMIC_DEMOTION_MARKERS,



    MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV,
    ORGANIC_AFFILIATED_HUB_KEYWORDS,
    EUROPEAN_ALLIANCES_KEYWORDS,
    ORGANIC_EXTERNAL_DOMAIN_DENYLIST,
    SPA_SUBPAGE_FETCH_TIMEOUT,
    WEB_CANDIDATES_PER_DEGREE,
    WEB_SEARCH_RETRY_DELAY,
    WIKIPEDIA_API_URL,
    WIKIDATA_API_URL,
    HEADER_KEYWORDS,
    INVALID_SUBJECT_KEYWORDS,
    TITLE_STOPWORDS,
    CV_EXCLUSION_MARKERS,
    NON_OFFICIAL_COURSE_MARKERS,
    INSTITUTIONAL_PORTAL_KEYWORDS,
    FULL_REVALIDATION,
    REDISCOVER_URLS_EVERY_RUN,
    TARGET_UNIVERSITY_CODES,
    MAX_PDF_PAGES_EXTRACT,
    WEB_SEARCH_DISCOVERY_MAX_QUERIES,
    WEB_SEARCH_DISCOVERY_MAX_RESULTS,
    ACADEMIC_DISCOVERY_EVIDENCE_TTL_SECONDS,
)
_MAX_PDF_PAGES_EXTRACT = MAX_PDF_PAGES_EXTRACT

from downloader import RUCTDownloader, SkipUniversityException, is_same_or_subdomain as downloader_is_same_or_subdomain, normalize_url, is_valid_http_url
from web_source_recovery import currentness_score, is_explicitly_historical
from curriculum_recovery import (
    extract_prose_curriculum,
    extract_structured_curriculum,
    extract_hydration_payload,
    extract_curriculum_from_json_tree,
    generic_curriculum_path_candidates,
    infer_declared_total_ects,
    is_summary_curriculum_name,
    matches_academic_level,
    merge_curriculum_elements,
    discover_related_academic_origins,
    discover_linked_curriculum_documents,
    discover_linked_curriculum_pages,
    discover_course_partitioned_subpages,
    matches_boe_credit_distribution,
)
from curriculum_validator import get_curriculum_completeness_status
from subject_guide_discovery import parse_sitemap_locations
from web_search_discovery import discover_institutional_origins, discover_search_candidates
from robots_policy import RobotsPolicy
from crawl_ledger import CrawlLedger
from ruct_xls_parser import extract_participating_universities
from data_quality import (
    apply_plan_quality,
    assess_plan_quality,
    promote_verified_candidate,
    source_record,
)
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump, load_json_safe
from phase_common import iter_plan_files, normalize_text
from parsers import (
    parse_boe_pdf,
    classify_subject_caracter,
    sanitize_subject_name,
    sanitize_string_value,
    curriculum_element_key,
    is_spurious_or_administrative_subject,
    is_curriculum_complete,
    compute_curriculum_total_ects,
    get_required_degree_credits,
    is_doctorate_program,
    extract_degree_core_keywords,
    is_section_matching,
    extract_subjects_from_card_blocks,
    detect_academic_language,
    normalize_curso,
    normalize_cuatrimestre,
    RE_SUMMARY_LABEL
)


def needs_web_resolution(plan_file: str, force: bool = False) -> bool:
    """Indica si la Parte 2 debe recuperar una titulación tras la Parte 1.

    Un plan solo se considera resuelto cuando está completo y la Parte 1 ha
    confirmado su fuente en la ejecución actual. Un plan histórico completo
    se conserva como respaldo, pero no evita el intento de recuperación si la
    fuente actual falló.
    """
    if force or not os.path.exists(plan_file):
        return True
    try:
        plan_data = load_json_safe(plan_file)
        return not (
            is_curriculum_complete(plan_data)
            and str(plan_data.get("estado_fuente", "")).strip().lower() == "verificada"
        )
    except Exception:
        return True

try:
    import lxml
    BS4_PARSER = "lxml"
except ImportError:
    BS4_PARSER = "html.parser"

_RE_SUMMARY_ROW_MARKERS = re.compile(
    r"^(?:totals?|totales?|total\s+cr[eé]ditos?|[1-6][º°a-z]*\s+(?:curs|curso|ano|año)|[1-6]r?\s+i\s+[1-6]t?\s+cursos?|formaci[oó]\s+b[aà]sica|optatives?|optativas?|menci[oó]\s+en\s+.*|itinerario\s+.*|menci[oó]n\s+.*)$",
    re.IGNORECASE
)

# Algunas universidades separan las asignaturas optativas en una sección
# explícita y omiten la columna de carácter. Estos marcadores son globales y
# se aplican solo al encabezado significativo más próximo a cada tabla.
_OPTIONAL_SECTION_MARKERS = (
    "optativa",
    "optatividad",
    "optatives",
    "optional subject",
    "optional credit",
    "elective",
    "electives",
    "aukerako",
)


def _is_optional_curriculum_section(text: str) -> bool:
    """Detecta una sección de oferta optativa en cualquier idioma soportado."""
    normalized = normalize_text(text or "")
    return bool(normalized) and any(marker in normalized for marker in _OPTIONAL_SECTION_MARKERS)


def _table_has_optional_context(table) -> bool:
    """Indica si la tabla pertenece al encabezado curricular optativo más cercano."""
    caption = table.find("caption")
    if caption and _is_optional_curriculum_section(caption.get_text(" ", strip=True)):
        return True
    for heading in table.find_all_previous(
        ["h1", "h2", "h3", "h4", "h5", "h6", "legend", "button", "summary"]
    ):
        text = heading.get_text(" ", strip=True)
        if not text:
            continue
        return _is_optional_curriculum_section(text)
    return False


# Lista ampliada de palabras clave y sinónimos para portales académicos y planes de estudio (ES / CA / GL / EU / EN)
ACADEMIC_KEYWORDS = [
    # Español
    "grado", "grados", "máster", "másteres", "master", "masteres",
    "doctorado", "doctorados", "titulación", "titulaciones", "estudio", "estudios",
    "enseñanza", "enseñanzas", "oferta-academica", "oferta_academica", "oferta-formativa",
    "plan-de-estudios", "plan_estudios", "plan-estudios", "planes-de-estudio",
    "guia-docente", "guias-docentes", "asignaturas", "programas", "curriculo",
    "currículo", "pensum", "malla-curricular", "titulos-oficiales", "estudios-oficiales",
    # Català / Valencià / Balear (UAB, UB, UPC, UPF, UV, UPV, UIB, etc.)
    "grau", "graus", "graus-i-dobles-graus", "dobles-graus", "estudis-de-grau",
    "pla-destudis", "pla-estudis", "plans-destudi", "assignatures", "guia-docent",
    "guies-docents", "titulacions-oficials", "doctorat", "programes-de-doctorat",
    # Galego (USC, UDC, UVigo)
    "grao", "graos", "graos-e-dobres-graos", "estudos-de-grao", "estudos",
    "plano-de-estudos", "posgrao", "doutoramento", "programas-de-doutoramento",
    # Euskara (UPV/EHU, Deusto, Mondragon)
    "gradua", "graduak", "gradu-bikoitzak", "ikasketak", "ikasketa-plana",
    "irakasgaiak", "irakaskuntza", "eskaintza-akademikoa", "masterra", "masterrak",
    "unibertsitate-masterra", "graduondokoa", "doktoregoa", "doktorego-programak",
    # English (UC3M, UPF, IE, Navarra, bilingual degrees)
    "bachelor", "bachelors", "undergraduate", "degrees", "double-degrees",
    "study-plan", "study-plans", "curriculum", "syllabus", "courses", "subjects",
    "postgraduate", "graduate", "master-degrees", "phd", "doctorate", "doctoral-programmes"
]


def score_academic_candidate_url(url: str, link_text: str, academic_level: str, title_keywords: list = None) -> int:
    """
    Calcula la prioridad semántica multilingüe de una URL candidata (0-100+):
    - Soporta Español, Catalán/Valenciano/Balear, Gallego, Euskera e Inglés.
    - Prioridad Alta (80-100): Portales de catálogo oficiales según el nivel académico (grados, másteres, doctorados).
    - Prioridad Media (40-60): Portales de oferta académica general y planes de estudio.
    - Prioridad Baja (1-10): Rutas administrativas o de servicios (nunca descartadas, pero evaluadas al final si no hay alternativa).
    """
    u_low = url.lower()
    t_low = (link_text or "").lower()
    level_low = (academic_level or "").lower()
    score = 10  # Puntuación base para cualquier enlace interno alcanzable

    # Las páginas históricas o de extinción no deben ganar a un plan vigente
    # solo por contener muchas coincidencias de palabras clave.
    if any(marker in u_low for marker in ("extingu", "ext-plan", "historico", "historical", "archivo")):
        score -= 120
    if any(marker in u_low for marker in ("objetivos", "career-options", "por-que-estudiar", "como-es-el-grado")):
        score -= 25
    
    # 1. Portales de catálogo específicos según el nivel académico (Prioridad Máxima 90-100)
    if "grado" in level_low or "grau" in level_low or "grao" in level_low or "gradua" in level_low or "bachelor" in level_low:
        grado_url_patterns = [
            # Español
            "grados-y-dobles-grados", "dobles-grados", "oferta-de-grados", "/grados", "/grado/", "/estudios/grado", "oferta-academica/grados", "oferta-formativa/grados", "grado-",
            # Català / Valencià
            "graus-i-dobles-graus", "dobles-graus", "oferta-de-graus", "/graus", "/grau/", "/estudis/grau", "oferta-formativa/graus", "estudis-de-grau", "grau-",
            # Galego
            "graos-e-dobres-graos", "dobres-graos", "oferta-de-graos", "/graos", "/grao/", "/estudos/grao", "estudos-de-grao", "grao-",
            # Euskara
            "gradu-bikoitzak", "/graduak", "/gradua/", "gradu-ikasketak", "gradua-",
            # English
            "bachelor-degree", "bachelor-degrees", "/undergraduate", "/bachelor/", "study-plans", "/degrees/", "bachelor-"
        ]
        grado_text_patterns = [
            "grado", "grados", "grau", "graus", "grao", "graos", "gradua", "graduak", "bachelor", "undergraduate"
        ]
        if any(kw in u_low for kw in grado_url_patterns):
            score += 90
        elif any(kw in t_low for kw in grado_text_patterns):
            score += 70

    elif "master" in level_low or "máster" in level_low or "màster" in level_low or "masterra" in level_low:
        master_url_patterns = [
            # Español
            "masteres-universitarios", "masteres-oficiales", "/masteres", "/master/", "/posgrado", "/postgrado",
            # Català / Valencià
            "masters-universitaris", "estudis-de-master", "/masters", "/postgrau",
            # Galego
            "estudos-de-posgrao", "/posgrao",
            # Euskara
            "unibertsitate-masterra", "/masterrak", "/graduondokoa",
            # English
            "master-degrees", "master-programs", "/masters/", "/postgraduate/", "/graduate/"
        ]
        master_text_patterns = [
            "master", "máster", "màster", "masteres", "másteres", "màsters", "posgrado", "postgrado", "postgrau", "posgrao", "masterra", "masterrak", "postgraduate"
        ]
        if any(kw in u_low for kw in master_url_patterns):
            score += 90
        elif any(kw in t_low for kw in master_text_patterns):
            score += 70

    elif "doctor" in level_low or "doutor" in level_low or "doktor" in level_low or "phd" in level_low:
        doctor_url_patterns = [
            "programas-de-doctorado", "/doctorado", "/doctorados", "/escuela-doctorado",
            "programes-de-doctorat", "/doctorat", "/doctorats", "escola-de-doctorat",
            "programas-de-doutoramento", "/doutoramento", "escola-de-doutoramento",
            "doktorego-programak", "/doktoregoa", "doktorego-eskola",
            "doctoral-programmes", "doctoral-programs", "/doctorate", "/phd/"
        ]
        doctor_text_patterns = [
            "doctorado", "doctor", "doctorat", "doutoramento", "doktoregoa", "phd", "doctorate"
        ]
        if any(kw in u_low for kw in doctor_url_patterns):
            score += 90
        elif any(kw in t_low for kw in doctor_text_patterns):
            score += 70

    # 2. Portales generales de oferta académica y planes de estudio multilingües (Prioridad Media 40-50)
    general_url_patterns = [
        "oferta-academica", "oferta_academica", "oferta-formativa", "planes-de-estudio", "plan_estudios",
        "pla-destudis", "pla-estudis", "plans-destudi", "plano-de-estudos", "ikasketa-plana",
        "titulos-oficiales", "estudios-oficiales", "estudis-oficials", "titulacions-oficials", "titulacions",
        "malla-curricular", "academic-offer", "academic-programs", "curriculum", "syllabus"
    ]
    general_text_patterns = [
        "oferta académica", "oferta academica", "oferta formativa", "planes de estudio", "pla d'estudis",
        "plano de estudos", "ikasketa plana", "titulaciones oficiales", "estudios oficiales", "study plans", "academic programs"
    ]
    if any(kw in u_low for kw in general_url_patterns):
        score += 50
    if any(kw in t_low for kw in general_text_patterns):
        score += 40

    # 2.5. Memorias Verificadas y Documentos Oficiales de Calidad / Acreditación ANECA / SGIC (Prioridad Máxima 95-100)
    if any(kw in u_low for kw in MEMORIA_VERIFICADA_KEYWORDS) or any(kw in t_low for kw in MEMORIA_VERIFICADA_KEYWORDS):
        score += 95

    # 3. Coincidencia con palabras clave específicas del título de la titulación (Multilingüe: raíz/stemming)
    if title_keywords:
        for kw in title_keywords:
            kw_low = kw.lower()
            kw_stem = kw_low[:4] if len(kw_low) >= 4 else kw_low
            if kw_low in u_low or kw_low in t_low or (len(kw_stem) >= 4 and (kw_stem in u_low or kw_stem in t_low)):
                score += 50
                break

    # El ranking debe favorecer páginas que puedan contener detalle
    # curricular, no solo una ficha promocional coincidente.
    if any(marker in u_low for marker in ("plan-de-estudios", "plan_estudio", "asignaturas", "subjects", "curriculum", "syllabus")):
        score += 20

    # 4. Rutas administrativas, legales, de cookies o servicios generales: PRIORIDAD MÁS BAJA (Multilingüe: No se eliminan, se evalúan al final)
    admin_service_patterns = [
        # Legal, cookies, privacidad y webmaster
        "/cookies", "politica-de-cookies", "politica-cookies", "aviso-legal", "avis-legal",
        "privacidad", "privadesa", "proteccion-de-datos", "proteccio-de-dades", "accesibilidad",
        "accessibilitat", "mapa-web", "mapa-del-sitio", "contactar", "contacto", "contacte",
        "buzon", "sugerencias", "transparencia", "actas", "normativa", "sede-electronica", "web-institucional",
        # Mínors, microcredenciales y formación permanente (no son grados ni másteres oficiales)
        "/minors", "/minor", "minors/", "minor/", "/microcredenciales", "/microcredencials", "/formacion-continua", "/formacio-continua",
        # Español
        "/administracion", "/oficina-del-estudiante", "/servicios", "/alojamiento", "/transporte", "/seguro-escolar", "/becas", "/pau", "/noticias", "/prensa", "/eventos", "/actividades", "/categoria", "/wp-content", "/galeria", "/agenda",
        # Català
        "/administracio", "/oficina-de-lestudiant", "/serveis", "/allotjament", "/beques",
        # Galego
        "/oficina-do-estudante", "/servizos", "/aloxamento", "/bolsas",
        # Euskara
        "/administrazioa", "/ikaslearen-bulegoa", "/zerbitzuak", "/ostatua", "/bekak",
        # English
        "/administration", "/student-office", "/services", "/accommodation", "/scholarships", "/news", "/press", "/events"
    ]
    if any(p in u_low for p in admin_service_patterns):
        score = max(1, score - 120)

    return score + currentness_score(url, link_text)


def _candidate_title_match_count(url: str, link_text: str, title_keywords: list | None) -> int:
    """Cuenta términos distintivos del título presentes en una candidata.

    Las páginas de una misma universidad comparten palabras como «grado» o
    «ingeniería». El índice Hub-and-Spoke también suele enlazar esas páginas
    desde un mismo catálogo, por lo que una sola coincidencia produce falsos
    positivos y obliga a rastrear subportales enteros. Se normalizan acentos y
    plurales simples para conservar el comportamiento multilingüe existente.
    """
    if not title_keywords:
        return 0

    haystack = unicodedata.normalize(
        "NFKD", f"{url or ''} {link_text or ''}"
    ).encode("ASCII", "ignore").decode("utf-8").lower()
    matches = set()
    for raw_keyword in title_keywords:
        keyword = unicodedata.normalize("NFKD", str(raw_keyword or ""))\
            .encode("ASCII", "ignore").decode("utf-8").lower().strip()
        if len(keyword) < 4:
            continue
        stem = keyword[:4]
        if keyword in haystack or stem in haystack:
            matches.add(keyword)
    return len(matches)


def _is_relevant_title_candidate(url: str, link_text: str, title_keywords: list | None) -> bool:
    """Evita explorar candidatos de otra titulación con un nombre parecido."""
    if not title_keywords:
        return True
    academic_markers = (
        "plan", "estudio", "grado", "master", "máster", "titulacion", "título",
        "docencia", "asignatura", "curriculum", "programa", "degree", "programme",
        "postgrado", "posgrado", "oferta-academica", "guia-docente", "malla",
        "estudis", "estudos", "grau", "graus", "grao", "graos", "gradua", "graduak",
        "ikasketa", "ikasketak", "bachelor", "undergraduate", "syllabus", "courses",
    )
    normalized_context = unicodedata.normalize(
        "NFKD", f"{url or ''} {link_text or ''}"
    ).encode("ASCII", "ignore").decode("utf-8").lower()
    if not any(marker in normalized_context for marker in academic_markers):
        return False
    GENERIC_LEVEL_WORDS = {"grado", "grados", "master", "masters", "máster", "másteres", "doctor", "doctorado", "doctorados", "titulo", "titulacion", "titulaciones", "estudio", "estudios"}
    substantive_kws = [
        kw for kw in title_keywords
        if str(kw or "").lower() not in GENERIC_LEVEL_WORDS and len(str(kw or "")) >= 4
    ]
    required = min(2, len(substantive_kws)) if substantive_kws else 1
    return _candidate_title_match_count(url, link_text, title_keywords) >= max(1, required)


def merge_persisted_discovery_evidence(
    catalog_map: dict,
    evidence: list[dict] | None,
    *,
    max_indexed_urls: int = HUB_AND_SPOKE_MAX_INDEXED_URLS,
    max_links_per_token: int = HUB_AND_SPOKE_MAX_LINKS_PER_TOKEN,
) -> int:
    """Integra en el índice vivo las evidencias académicas persistidas.

    El ledger es un índice de descubrimiento, no una fuente de datos. Sus
    URLs sólo entran como candidatas y vuelven a pasar por robots, descarga,
    identidad y validación de completitud en el llamador. Las cotas se aplican
    también aquí para que una campaña anterior no pueda hacer crecer el mapa
    sin límite. Las entradas persistidas se anteponen a las nuevas para que
    un enlace curricular ya conocido no quede oculto tras enlaces genéricos.
    """
    if not isinstance(catalog_map, dict) or not evidence:
        return 0
    try:
        url_limit = max(1, int(max_indexed_urls))
    except (TypeError, ValueError):
        url_limit = 12000
    try:
        token_limit = max(1, int(max_links_per_token))
    except (TypeError, ValueError):
        token_limit = 96

    seen_urls = set()
    for entries in catalog_map.values():
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, (tuple, list)) and entry:
                seen_urls.add(str(entry[0]).rstrip("/"))
            elif entry:
                seen_urls.add(str(entry).rstrip("/"))

    indexed = 0
    for record in evidence:
        if len(seen_urls) >= url_limit or not isinstance(record, dict):
            break
        url = str(record.get("url") or "").strip()
        if not url or not is_valid_web_url(url) or is_explicitly_historical(url):
            continue
        normalized_url = url.rstrip("/")
        if normalized_url in seen_urls:
            continue
        title = " ".join(
            str(record.get(field) or "").strip()
            for field in ("title", "anchor_text", "heading")
            if str(record.get(field) or "").strip()
        )
        raw_tokens = re.findall(
            r"\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}\b",
            f"{title} {url}",
        )
        tokens = set()
        for word in raw_tokens:
            word_low = word.lower()
            word_norm = (
                unicodedata.normalize("NFKD", word_low)
                .encode("ASCII", "ignore")
                .decode("utf-8")
            )
            tokens.add(word_low)
            tokens.add(word_norm)
            if word_norm.endswith("s") and len(word_norm) > 4:
                tokens.add(word_norm[:-1])
            if word_norm.endswith("es") and len(word_norm) > 5:
                tokens.add(word_norm[:-2])
        if not tokens:
            continue
        entry = (url, title)
        seen_urls.add(normalized_url)
        indexed += 1
        for token in tokens:
            entries = catalog_map.setdefault(token, [])
            entries[:] = [
                existing for existing in entries
                if str(existing[0] if isinstance(existing, (tuple, list)) else existing).rstrip("/")
                != normalized_url
            ]
            entries.insert(0, entry)
            del entries[token_limit:]
    return indexed


def merge_bounded_catalog_map(
    catalog_map: dict,
    discovered_map: dict | None,
    *,
    max_indexed_urls: int = HUB_AND_SPOKE_MAX_INDEXED_URLS,
    max_links_per_token: int = HUB_AND_SPOKE_MAX_LINKS_PER_TOKEN,
) -> int:
    """Agrega un índice de descubrimiento manteniendo una cota global.

    Cada portal académico relacionado puede producir su propio índice local.
    Si se concatenan sin límite, la cota por portal deja de proteger la RAM y
    los primeros recorridos desplazan indefinidamente a los siguientes. Este
    helper aplica la cota sobre el mapa agregado, deduplica URLs y conserva el
    orden de prioridad que ya haya establecido el llamador.
    """
    if not isinstance(catalog_map, dict) or not isinstance(discovered_map, dict):
        return 0
    try:
        url_limit = max(1, int(max_indexed_urls))
    except (TypeError, ValueError):
        url_limit = 12000
    try:
        token_limit = max(1, int(max_links_per_token))
    except (TypeError, ValueError):
        token_limit = 96

    known_urls = set()
    for entries in catalog_map.values():
        for entry in entries if isinstance(entries, list) else []:
            url = entry[0] if isinstance(entry, (tuple, list)) and entry else entry
            if url:
                known_urls.add(str(url).rstrip("/"))

    added_urls = 0
    for token, entries in discovered_map.items():
        if not isinstance(entries, list):
            continue
        target_entries = catalog_map.setdefault(token, [])
        existing_for_token = {
            str(item[0] if isinstance(item, (tuple, list)) and item else item).rstrip("/")
            for item in target_entries
            if item
        }
        for entry in entries:
            if isinstance(entry, (tuple, list)) and entry:
                url = str(entry[0]).strip()
                normalized_entry = tuple(entry)
            else:
                url = str(entry).strip()
                normalized_entry = (url, "")
            normalized_url = url.rstrip("/")
            if not normalized_url or normalized_url in existing_for_token:
                continue
            if normalized_url not in known_urls:
                if len(known_urls) >= url_limit:
                    continue
                known_urls.add(normalized_url)
                added_urls += 1
            target_entries.append(normalized_entry)
            existing_for_token.add(normalized_url)
            if len(target_entries) > token_limit:
                del target_entries[token_limit:]
        if len(target_entries) > token_limit:
            del target_entries[token_limit:]
    return added_urls


def is_valid_curricular_table(table_tag) -> bool:
    """Verifica que una tabla HTML sea verdaderamente curricular (reutiliza sanitizers centralizado)."""
    from sanitizers import is_valid_curricular_table as sanitizers_is_valid_table
    return sanitizers_is_valid_table(table_tag)


def ensure_https_url(url: str) -> str:
    """Fuerza protocolo HTTPS en cualquier URL web universitaria."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("http://"):
        return "https://" + u[7:]
    elif not u.startswith("https://"):
        return "https://" + u
    return u


def http_protocol_fallback_url(url: str) -> str:
    """Devuelve el mismo origen por HTTP para resolver certificados heredados.

    Algunos dominios institucionales antiguos conservan una redirección HTTP
    válida pero presentan un certificado HTTPS que ya no corresponde al host
    legado. El fallback se usa sólo después de que la comprobación de robots
    del origen inicial haya fallado al conectar; nunca desactiva TLS ni acepta
    un destino fuera del dominio validado.
    """
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return urllib.parse.urlunsplit(("http", parsed.netloc, parsed.path or "/", "", ""))


def stored_academic_origins(degrees: list, base_url: str, university_code: str = "") -> list[str]:
    """Obtiene orígenes académicos ya evidenciados por el propio expediente.

    El dominio principal de una institución puede tener una política de
    robots.txt distinta de la de su subportal académico. Reutilizar únicamente
    URLs oficiales ya guardadas, y aceptar sólo el mismo dominio organizativo,
    permite continuar la recuperación sin inventar hosts ni relajar robots.
    """
    origins = []
    base_origin = urllib.parse.urlunsplit(
        urllib.parse.urlsplit(ensure_https_url(base_url))._replace(path="", query="", fragment="")
    ).rstrip("/")
    for degree in degrees or []:
        if not isinstance(degree, dict):
            continue
        path = find_plan_filepath(
            str(university_code or degree.get("universidad_codigo") or "").zfill(3),
            str(degree.get("codigo_estudio") or "").strip(),
        ) if (university_code or degree.get("universidad_codigo")) else ""
        data = load_json_safe(path, default={}) if path else {}
        candidates = []
        if isinstance(data, dict):
            candidates.append(data.get("web_fuente_directa_url"))
            candidates.extend(
                item.get("url")
                for item in (data.get("fuentes") or [])
                if isinstance(item, dict)
            )
        for raw_url in candidates:
            candidate = ensure_https_url(str(raw_url or "").strip())
            if (
                not is_valid_web_url(candidate)
                or is_explicitly_historical(candidate)
                or not downloader_is_same_or_subdomain(candidate, base_url)
            ):
                continue
            parsed = urllib.parse.urlsplit(candidate)
            origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
            if origin and origin != base_origin and origin not in origins:
                origins.append(origin)
    return origins


def parse_price_value(val_str: str, min_val: float, max_val: float) -> float | None:
    """Convierte cadenas numéricas europeas o estándar a float y valida que se encuentren en el rango esperado."""
    if not val_str:
        return None
    s = str(val_str).strip()
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.match(r'^\d{1,3}\.\d{3}$', s):
        s = s.replace(".", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        val_num = float(s)
        if min_val <= val_num <= max_val:
            return round(val_num, 2)
    except ValueError:
        pass
    return None


def build_html_curriculum_payload(
    elementos_html: list,
    degree_title: str,
    declared_total_ects: float | None = None,
) -> dict:
    """Construye la estructura estándar de plan de estudios a partir de asignaturas extraídas de HTML."""
    total_ects = sum(
        float(str(e.get("creditos_ects", 0)).replace(",", "."))
        for e in elementos_html
        if e.get("creditos_ects") not in (None, "")
    )
    summary = {}
    if declared_total_ects is not None:
        summary["Créditos Totales"] = f"{declared_total_ects:g} ECTS"
    return {
        "resumen_creditos": summary,
        "origen": "Web Oficial Universidad",
        "total_elementos": len(elementos_html),
        "total_creditos_extraidos": round(total_ects, 2),
        "elementos_curriculares": elementos_html,
        "is_partial": total_ects < 120.0
    }


PRICING_FIELDS = (
    "precio_credito_ects",
    "precio_credito_2",
    "precio_credito_3",
    "precio_credito_4",
    "precio_estimado_anual",
    "fuente_precio",
)


def merge_preserved_pricing(
    target: dict,
    recovered: dict | None = None,
    catalog: dict | None = None,
) -> dict:
    """Fusiona precios sin borrar evidencia económica ya recolectada.

    La fuente curricular puede no publicar precios. Por eso cada campo usa la
    evidencia nueva, después el catálogo y finalmente el registro existente.
    La operación muta y devuelve ``target`` para integrarse con las escrituras
    atómicas existentes.
    """
    if not isinstance(target, dict):
        return target
    recovered = recovered if isinstance(recovered, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    for field in PRICING_FIELDS:
        for candidate in (recovered.get(field), catalog.get(field), target.get(field)):
            if candidate is not None and candidate != "":
                target[field] = candidate
                break
    return target


def adaptive_hub_budget(pending_degree_count: int, configured_max: int) -> int:
    """Calcula una cota de hubs proporcional a la cohorte pendiente.

    El preindexado de una universidad no debe consumir el mismo presupuesto
    para una sola titulación que para cientos. Se conserva un suelo suficiente
    para portales con varios niveles de navegación y se respeta siempre el
    máximo configurado por el operador.
    """
    try:
        pending = max(0, int(pending_degree_count))
        maximum = max(1, int(configured_max))
    except (TypeError, ValueError):
        return 0
    if pending == 0:
        return 0
    # Una cohorte pequeña no necesita abrir decenas de hubs antes de probar
    # sitemap, evidencia persistida y rutas curriculares directas. Mantener
    # ese suelo alto hacía que una sola titulación pudiera consumir todo el
    # presupuesto temporal y de memoria de la campaña. La cota crece de forma
    # lineal con la cohorte, con un único hub inicial para una titulación y
    # manteniendo el máximo configurado para campañas grandes.
    return min(maximum, max(1, 1 + (pending // 2)))


RE_LEVEL_GRADO = re.compile(r"\b(?:grado|grados|graduado|graduada|graduados|graduadas|grau|graus|grao|graos|gradua|graduak|bachelor|undergraduate|llistat-de-graus|estudis-de-grau)\b", re.IGNORECASE)
RE_LEVEL_MASTER = re.compile(r"\b(?:master|masters|máster|másteres|màster|màsters|masterra|masterrak|postgrado|posgrado|postgrau|posgrao|postgraduate)\b", re.IGNORECASE)
RE_LEVEL_DOCTOR = re.compile(r"\b(?:doctor|doctora|doctorado|doctorados|doctorat|doctorats|doutoramento|doktoregoa|doctorate|doctoral|phd)\b", re.IGNORECASE)
RE_ENGINEERING_MARKER = re.compile(r"\b(?:ingenier[ií]a|ingeniero|ingeniera|enginyeria|engineering)\b", re.IGNORECASE)
RE_DOUBLE_DEGREE_MARKER = re.compile(r"\b(?:doble|simultaneidad|pceo|double)\b", re.IGNORECASE)


def is_source_url_level_compatible(page_url: str, academic_level: str) -> bool:
    """Rechaza URLs cuyo propio recorrido identifica otro nivel académico.

    El encabezado de una página puede incluir menús completos de la
    institución y hacer que una ficha de grado parezca relacionada con un
    máster (o al revés). Los segmentos explícitos de la ruta son una señal
    negativa fuerte y se aplican de forma uniforme, sin conocer universidades
    ni titulaciones concretas.
    """
    path = unicodedata.normalize(
        "NFKD", urllib.parse.urlsplit(str(page_url or "")).path
    ).encode("ASCII", "ignore").decode("ascii").lower()
    level = unicodedata.normalize("NFKD", str(academic_level or "")) \
        .encode("ASCII", "ignore").decode("ascii").lower()
    if not path or not level:
        return True

    route_levels = {
        "grado": r"(?:grado|grados|grau|graus|grao|graos|bachelor|undergraduate)",
        "master": r"(?:master|masters|posgrado|postgrado|postgrau|postgrao|postgraduate)",
        "doctorado": r"(?:doctorado|doctorados|doctorat|doctorats|doutoramento|doctorate|phd)",
    }
    target_level = (
        "doctorado" if RE_LEVEL_DOCTOR.search(level)
        else "master" if RE_LEVEL_MASTER.search(level)
        else "grado" if RE_LEVEL_GRADO.search(level)
        else ""
    )
    if not target_level:
        return True

    route_text = path.replace("_", "-")
    for other_level, pattern in route_levels.items():
        if other_level == target_level:
            continue
        if re.search(rf"(?:^|/|-){pattern}(?:/|-|$)", route_text):
            return False
    return True


def _degree_identity_title(title: str) -> str:
    """Quita el sufijo de universidades asociadas del nombre del programa.

    Los títulos cooperativos pueden enumerar varias instituciones y países
    después de la denominación académica. Esos nombres no deben convertirse
    en palabras distintivas para identificar una página curricular.
    """
    text = str(title or "").strip()
    if not text:
        return ""
    affiliation = re.search(
        r"\s+(?:por|by|per|par|pela|pelo)\s+(?:la|el|las|los|the|l[aeiou])?\s*"
        r"(?:universidad|university|universitat|universidade)\b",
        text,
        flags=re.IGNORECASE,
    )
    return text[:affiliation.start()].strip() if affiliation else text


def is_html_page_matching_degree(
    soup: BeautifulSoup,
    target_title: str,
    univ_name: str,
    page_url: str = "",
    allow_curriculum_url_identity: bool = False,
) -> bool:
    """
    Verifica que la página HTML pertenezca realmente a la titulación objetivo y no a otra titulación distinta.
    Comprueba:
    1. Que no sea una subpágina de cursos de extensión, títulos propios o formularios no oficiales.
    2. Consistencia estricta de Nivel Académico (3 niveles independientes: Grado, Máster y Doctorado).
    3. Distinción estricta de Ingeniería vs Ciencia/Salud en el título principal.
    4. Distinción estricta de Grado Simple vs Doble Grado.
    5. Validación semántica del núcleo temático con lematización multilingüe y filtro de adjetivos genéricos.
    """
    if not target_title or not soup:
        return False

    target_low = target_title.lower()
    url_low = (page_url or "").lower()

    # 1. Descartar cursos de extensión, títulos propios no oficiales y formularios administrativos
    if any(m in url_low for m in NON_OFFICIAL_COURSE_MARKERS):
        return False

    # 2. Extraer título principal y encabezados secundarios
    primary_title_candidates = []
    for h1 in soup.find_all("h1"):
        h1_txt = h1.get_text(separator=" ", strip=True)
        if h1_txt:
            primary_title_candidates.append(h1_txt)
    for meta in soup.find_all("meta", attrs={"property": "og:title"}):
        if meta.get("content"):
            primary_title_candidates.append(meta["content"])
    for meta in soup.find_all("meta", attrs={"name": "title"}):
        if meta.get("content"):
            primary_title_candidates.append(meta["content"])
    if soup.title and soup.title.string:
        primary_title_candidates.append(soup.title.string)

    primary_title_str = " ".join(primary_title_candidates).lower()

    page_texts = list(primary_title_candidates)
    for h in soup.find_all(["h2", "h3"]):
        h_text = h.get_text(separator=" ", strip=True)
        if h_text and len(h_text) > 3:
            page_texts.append(h_text)

    if page_url:
        page_texts.append(page_url.replace("/", " ").replace("-", " ").replace("_", " "))

    combined_page_header = " ".join(page_texts).lower()

    # 3. Validación de consistencia de Nivel Académico (3 niveles independientes)
    is_target_grado = bool(RE_LEVEL_GRADO.search(target_low))
    is_target_master = bool(RE_LEVEL_MASTER.search(target_low))
    is_target_doctor = bool(RE_LEVEL_DOCTOR.search(target_low))

    is_page_grado = bool(RE_LEVEL_GRADO.search(combined_page_header))
    is_page_master = bool(RE_LEVEL_MASTER.search(combined_page_header))
    is_page_doctor = bool(RE_LEVEL_DOCTOR.search(combined_page_header))

    if is_target_grado and not is_page_grado and (is_page_master or is_page_doctor):
        return False
    if is_target_master and not is_page_master and (is_page_grado or is_page_doctor):
        return False
    if is_target_doctor and not is_page_doctor and (is_page_grado or is_page_master):
        return False

    # 4. Distinción estricta de Ingeniería vs Ciencia/Salud Pura en el título principal
    is_target_eng = bool(RE_ENGINEERING_MARKER.search(target_low))
    eval_eng_text = primary_title_str if primary_title_str else combined_page_header
    is_page_eng = bool(RE_ENGINEERING_MARKER.search(eval_eng_text))
    if is_target_eng != is_page_eng and primary_title_str:
        return False

    # 5. Distinción estricta de Grado Simple vs Doble Grado (sobre el título principal o URL de la ficha, no widgets laterales)
    is_target_double = bool(RE_DOUBLE_DEGREE_MARKER.search(target_low))
    eval_double_text = f"{primary_title_str} {page_url or ''}".lower()
    is_page_double = bool(RE_DOUBLE_DEGREE_MARKER.search(eval_double_text))
    if not is_target_double and is_page_double:
        return False

    # 6. Validación semántica del núcleo temático
    target_kw = extract_degree_core_keywords(
        _degree_identity_title(target_title),
        univ_name,
    )
    if not target_kw:
        return True

    page_kw = extract_degree_core_keywords(combined_page_header, univ_name)
    if allow_curriculum_url_identity and (
        not page_kw or not is_section_matching(page_kw, target_kw)
    ):
        # Algunos portales docentes usan una marca corta en el HTML (p. ej.
        # el acrónimo del programa) y reservan el nombre completo para la
        # ficha institucional que enlazó el portal. En ese contexto acotado,
        # el host/ruta temática aporta identidad suficiente junto con el
        # umbral de elementos curriculares aplicado por el llamador.
        page_kw = extract_degree_core_keywords(page_url, univ_name)
        url_context = unicodedata.normalize(
            "NFKD", str(page_url or "")
        ).encode("ASCII", "ignore").decode("ascii").lower()
        target_stems = {
            str(keyword).lower()[:5]
            for keyword in target_kw
            if len(str(keyword)) >= 5
        }
        url_stem_matches = {
            stem for stem in target_stems
            if stem in url_context
        }
        # La URL sólo puede suplir la identidad del encabezado cuando aporta
        # suficiente contexto discriminativo. Una única coincidencia amplia
        # (por ejemplo, «social» dentro de una sección institucional) no
        # demuestra que la página pertenezca al programa objetivo y había
        # permitido aceptar planes de otra titulación del mismo portal.
        minimum_url_stems = 1 if len(target_stems) <= 1 else 2
        if len(url_stem_matches) >= minimum_url_stems:
            page_kw = target_kw
    if not page_kw:
        return False

    return is_section_matching(page_kw, target_kw)


def are_degree_titles_compatible(first_title: str, second_title: str, univ_name: str = "") -> bool:
    """Comprueba que dos titulaciones puedan compartir una fuente curricular.

    Una URL puede ser legítimamente común a versiones cooperativas o
    lingüísticas de un plan, pero no a dos especialidades distintas. La
    comparación es simétrica y usa las mismas palabras núcleo que el filtro
    de páginas; exigir ambas direcciones evita que la palabra genérica
    «ingeniería» haga compatibles «Ingeniería Web» e «Ingeniería Mecatrónica».
    """
    first = extract_degree_core_keywords(first_title, univ_name)
    second = extract_degree_core_keywords(second_title, univ_name)
    if not first or not second:
        return False
    return is_section_matching(first, second) and is_section_matching(second, first)


_EXTERNAL_AFFILIATION_MARKERS = (
    "centro adscrito", "centros adscritos", "centro asociado", "centros asociados",
    "escuela adscrita", "escuelas adscritas", "instituto adscrito",
    "facultad asociada", "facultades asociadas", "partner institution",
    "partner university", "institutional partner", "academic partner",
    "escola superior", "escuela superior", "instituto superior", "institut superior",
    "college", "school of", "faculty of", "facultad de", "facultat de",
    "escola", "escuela",
)
_EXTERNAL_ALLIANCE_MARKERS = (
    "erasmus mundus", "joint master", "joint degree", "european university",
    "european alliance", "sea-eu", "eunice", "charmeu", "arqus", "civica",
    "civis", "eut+", "neurotecheu", "circle u", "unite!", "enlight",
    "4eu+", "una europa", "eureca-pro", "ingenium",
)


def is_authorized_external_academic_hub(url: str, anchor_text: str = "") -> bool:
    """Acepta una fuente externa solo con evidencia relacional explícita.

    Un enlace externo a una institución o a una red social no demuestra que
    sea un centro colaborador. La autorización se basa en el contexto visible
    del enlace y en marcadores de alianzas académicas, no en una universidad
    concreta ni en una lista de dominios institucionales.
    """
    parsed = urllib.parse.urlparse(str(url or ""))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or any(host == denied or host.endswith("." + denied) for denied in ORGANIC_EXTERNAL_DOMAIN_DENYLIST):
        return False
    context = unicodedata.normalize(
        "NFKD", f"{anchor_text or ''} {parsed.path or ''} {parsed.query or ''}"
    ).encode("ASCII", "ignore").decode("ascii").lower()
    return any(marker in context for marker in _EXTERNAL_AFFILIATION_MARKERS + _EXTERNAL_ALLIANCE_MARKERS)


def is_valid_web_url(href) -> bool:
    """Valida que un enlace sea HTTP/HTTPS y no un esquema especial (mailto, javascript, tel, ancla)."""
    if not href or not isinstance(href, str):
        return False
    h = href.strip().lower()
    if h.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:", "ftp:", "data:")):
        return False
    if h.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(href)
        if not parsed.netloc or not parsed.netloc.strip():
            return False
    return True


def is_same_or_subdomain(target_url: str, base_url: str) -> bool:
    """Reutiliza la política centralizada de dominios del descargador."""
    return downloader_is_same_or_subdomain(target_url, base_url)


def is_spider_trap_or_spurious_url(url: str, text: str = "") -> bool:
    """
    Filtro defensivo para descartar calendarios, agendas, noticias, blogs, tags, feeds,
    avisos legales y trampas de rastreo infinitas que no son catálogos académicos.
    """
    url_low = url.lower()
    text_low = text.lower().strip()
    
    # 1. Marcadores de ruta de spider traps
    if any(trap in url_low for trap in SPIDER_TRAP_PATH_MARKERS):
        return True
        
    # 2. Parámetros de ordenación/filtro de calendarios
    parsed = urllib.parse.urlparse(url_low)
    qs = parsed.query
    if any(p in qs for p in ["month=", "year=", "calendar=", "event_date=", "view_mode="]):
        return True
        
    # 3. Textos genéricos no académicos de 1 sola palabra
    if text_low in {"inicio", "home", "twitter", "facebook", "instagram", "linkedin", "youtube", "rss", "feed", "aviso legal", "privacidad", "cookies", "login", "acceder", "contacto", "mapa web"}:
        return True
        
    return False


def is_dynamic_academic_hub(
    soup: BeautifulSoup, 
    link_tag, 
    full_url: str, 
    base_univ_url: str
) -> bool:
    """
    Motor Heurístico Autónomo de 6 Capas para clasificar si un enlace interno es un HUB de catálogo:
    1. Filtro anti-spider traps.
    2. Pertenencia a contenedor de navegación semántica DOM (<nav>, <header>, role="navigation").
    3. Heurística de Uniformidad de Enlaces Hermanos (Sibling Link Uniformity >= 6 enlaces con misma ruta padre).
    4. Criterio de longitud del texto del enlace (2 a 10 palabras representativas de ramas/estudios).
    """
    if is_spider_trap_or_spurious_url(full_url, link_tag.get_text(strip=True)):
        return False
        
    if not is_same_or_subdomain(full_url, base_univ_url):
        return False
        
    text = link_tag.get_text(strip=True)
    words = text.split()
    
    # Capa 1: ¿Está dentro de un landmark de navegación semántica DOM?
    nav_parent = link_tag.find_parent(["nav", "header"])
    if nav_parent or link_tag.find_parent(attrs={"role": lambda r: r and "navigation" in r}):
        if 1 <= len(words) <= 8 and not is_spurious_or_administrative_subject(text):
            return True

    # Capa 2: Uniformidad de Enlaces Hermanos en listas/tablas (Sibling Uniformity)
    parent_container = link_tag.find_parent(["ul", "ol", "div", "tbody"])
    if parent_container:
        siblings = parent_container.find_all("a", href=True)
        valid_academic_siblings = 0
        parsed_target = urllib.parse.urlparse(full_url)
        target_parent_path = "/".join(parsed_target.path.strip("/").split("/")[:-1])
        
        for sib in siblings:
            sib_href = sib["href"].strip()
            sib_full = urllib.parse.urljoin(full_url, sib_href)
            sib_text = sib.get_text(strip=True)
            sib_words = sib_text.split()
            if (
                DYNAMIC_HUB_MIN_TITLE_WORDS <= len(sib_words) <= DYNAMIC_HUB_MAX_TITLE_WORDS
                and not is_spider_trap_or_spurious_url(sib_full, sib_text)
                and not is_spurious_or_administrative_subject(sib_text)
            ):
                sib_parsed = urllib.parse.urlparse(sib_full)
                sib_parent_path = "/".join(sib_parsed.path.strip("/").split("/")[:-1])
                if sib_parent_path == target_parent_path or len(sib_words) >= 3:
                    valid_academic_siblings += 1
                    
        if valid_academic_siblings >= DYNAMIC_HUB_MIN_SIBLINGS:
            return True
            
    # Capa 3: Fallback semántico (soporta palabras clave si están presentes, sin depender exclusivamente de ellas)
    t_low = text.lower()
    h_low = full_url.lower()
    if any(k in t_low or k in h_low for k in HUB_ACADEMIC_KEYWORDS):
        return True
        
    return False


def extract_breadcrumb_parent_hubs(soup: BeautifulSoup, current_url: str, base_univ_url: str) -> list:
    """
    Capa 3: Ascenso Jerárquico por Migas de Pan (Breadcrumbs).
    Extrae los nodos padre y abuelo en <ol class="breadcrumb"> o <nav aria-label="breadcrumb">.
    """
    discovered_hubs = []
    bc_container = soup.find(attrs={"class": lambda c: c and "breadcrumb" in c.lower()}) or soup.find(attrs={"aria-label": lambda a: a and "breadcrumb" in a.lower()})
    if bc_container:
        for a in bc_container.find_all("a", href=True):
            h = a["href"].strip()
            full_link = urllib.parse.urljoin(current_url, h)
            if is_same_or_subdomain(full_link, base_univ_url) and not is_spider_trap_or_spurious_url(full_link, a.get_text(strip=True)):
                if full_link.rstrip("/") != current_url.rstrip("/") and full_link.rstrip("/") != base_univ_url.rstrip("/"):
                    discovered_hubs.append(full_link)
    return discovered_hubs


def extract_hydration_payload_degrees(soup: BeautifulSoup, current_url: str) -> list:
    """
    Capa 4: Extracción de Cargas de Hidratación Embebidas (JSON-LD / Next.js __NEXT_DATA__).
    Permite recuperar catálogos de grados en SPAs sin renderizado de navegador.
    """
    results = []
    # 1. JSON-LD (Schema.org)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or script.get_text()
            if not raw:
                continue
            data = json.loads(raw)
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("itemListElement") or data.get("hasCourse") or data.get("subEvent") or [data]
                
            for it in items:
                if isinstance(it, dict):
                    name = it.get("name") or it.get("item", {}).get("name")
                    url = it.get("url") or it.get("item", {}).get("url") or it.get("item", {}).get("@id")
                    if name and url:
                        full_u = urllib.parse.urljoin(current_url, str(url))
                        results.append((full_u, str(name).strip()))
        except Exception as exc:
            logger.debug(f"Excepción controlada en crawling: {exc}")
            continue
            
    # 2. Next.js __NEXT_DATA__
    next_data_script = soup.find("script", id="__NEXT_DATA__")
    if next_data_script and next_data_script.string:
        try:
            data = json.loads(next_data_script.string)
            page_props = data.get("props", {}).get("pageProps", {})
            for k, v in page_props.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            title = item.get("title") or item.get("name") or item.get("nombre")
                            slug = item.get("slug") or item.get("url") or item.get("path")
                            if title and slug:
                                full_u = urllib.parse.urljoin(current_url, str(slug))
                                results.append((full_u, str(title).strip()))
        except Exception as exc:
            logger.debug(f"Excepción controlada en crawling: {exc}")
            pass
            
    return results


def extract_form_select_academic_options(soup: BeautifulSoup, current_url: str) -> list:
    """
    Capa 5: Extractor de Desplegables de Formularios (<select> & <option>).
    Resuelve portales basados en formularios interactivos donde las carreras están en <option>.
    """
    results = []
    for select in soup.find_all("select"):
        options = select.find_all("option")
        if len(options) >= 5:
            s_name = (select.get("name") or select.get("id") or "").lower()
            parent_form = select.find_parent("form")
            action_url = current_url
            if parent_form and parent_form.get("action"):
                action_url = urllib.parse.urljoin(current_url, parent_form["action"])
                
            for opt in options:
                val = opt.get("value", "").strip()
                label = opt.get_text(strip=True)
                words = label.split()
                if val and DYNAMIC_HUB_MIN_TITLE_WORDS <= len(words) <= DYNAMIC_HUB_MAX_TITLE_WORDS:
                    if not any(stop in label.lower() for stop in ["seleccione", "selecciona", "todos los", "todas las", "elegir"]):
                        param_name = s_name or "asig"
                        sep = "&" if "?" in action_url else "?"
                        target_url = f"{action_url}{sep}{param_name}={urllib.parse.quote(val)}"
                        results.append((target_url, label))
    return results


def extract_js_event_links(soup: BeautifulSoup, current_url: str) -> list:
    """
    Capa 6: Desofuscador de Eventos JavaScript (onclick, data-url, data-href).
    """
    results = []
    for elem in soup.find_all(attrs={"onclick": True}):
        oc = elem["onclick"]
        m = re.search(r"(?:location\.href\s*=\s*['\"]|window\.open\(['\"]|['\"])(/[^'\"]+|https?://[^'\"]+)", oc)
        if m:
            target_h = m.group(1).strip()
            full_u = urllib.parse.urljoin(current_url, target_h)
            txt = elem.get_text(strip=True)
            if txt and len(txt) >= 4:
                results.append((full_u, txt))
                
    for elem in soup.find_all(lambda tag: tag.has_attr("data-url") or tag.has_attr("data-href") or tag.has_attr("data-link")):
        target_h = elem.get("data-url") or elem.get("data-href") or elem.get("data-link")
        if target_h:
            full_u = urllib.parse.urljoin(current_url, str(target_h).strip())
            txt = elem.get_text(strip=True)
            if txt and len(txt) >= 4:
                results.append((full_u, txt))
                
    return results


from parsers.html_tables import (
    _extract_parallel_html_row,
    _extract_subject_cell_text,
    _fill_explicit_uniform_curricular_ects,
    _infer_uniform_curricular_ects,
    _is_html_metadata_subject,
    extract_html_subjects,
)
from parsers.dynamic_widgets import extract_dynamic_widget_subjects
from extractors.doctoral_programs import (
    DOCTORAL_LINE_DISQUALIFIERS,
    RE_DOCTORAL_ACTIVIDADES_HEADER,
    RE_DOCTORAL_ESCUELA_PATTERNS,
    RE_DOCTORAL_LINEAS_HEADER,
    SUBPAGE_DOCTORAL_LINEAS_KW,
    extract_doctoral_activities_from_soup,
    extract_doctoral_lines_from_soup,
    extract_doctoral_school_name,
    extract_generic_doctoral_program,
    is_valid_doctoral_line,
)
from extractors.private_pricing import (
    extract_private_university_pricing,
    parse_price_value,
)


class UniversityWebCrawler:
    """
    Fase 1 - Parte 2: Crawling paralelo de las webs oficiales de las universidades
    para obtener planes de estudio de las titulaciones que carecen de información en RUCT/BOE.
    """
    _robots_cache = {}
    _robots_cache_ttl = ROBOTS_CACHE_TTL_SECONDS
    _robots_lock = threading.Lock()

    def __init__(self, user_agent=USER_AGENT, timeout=HTTP_TIMEOUT, metrics_tracker=None, ledger=None):
        self.user_agent = user_agent
        self.timeout = timeout
        self.metrics_tracker = metrics_tracker
        self.ledger = ledger or CrawlLedger()
        self.logger = ErrorLogger()
        self.checkpoint = CheckpointManager()
        self.univ_file_lock = threading.Lock()
        self.organic_lock = threading.Lock()
        self.organic_affiliated_hubs = defaultdict(dict)
        self.organic_affiliated_cache = {}
        self.web_search_cache = {}
        self.web_search_lock = threading.Lock()

    def _try_parse_candidate_pdf(self, downloader: RUCTDownloader, pdf_url: str, d_code: str, d_title: str, u_name: str) -> dict | None:
        """Descarga, analiza con parse_boe_pdf, valida la identidad semántica sobre la totalidad del PDF y limpia el archivo temporal."""
        pdf_url_low = pdf_url.lower()
        if any(bad in pdf_url_low for bad in CV_EXCLUSION_MARKERS):
            return None
        if any(bad in pdf_url_low for bad in NON_OFFICIAL_COURSE_MARKERS):
            return None

        temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
        try:
            downloader.download_file(pdf_url, temp_pdf, is_pdf=True)
            parsed = parse_boe_pdf(temp_pdf, target_title=d_title, univ_name=u_name)
            if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
                # Verificación de identidad: comprobar contra la totalidad del PDF y su URL
                target_kw = extract_degree_core_keywords(d_title, u_name)
                url_clean = pdf_url.replace("/", " ").replace("-", " ").replace("_", " ")
                pdf_kw = extract_degree_core_keywords(url_clean, u_name)
                
                if not is_section_matching(pdf_kw, target_kw):
                    # Extraer texto de la totalidad de páginas del documento PDF (sin límites de páginas)
                    pdf_text_full = ""
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(temp_pdf)
                        if len(reader.pages) > _MAX_PDF_PAGES_EXTRACT:
                            logger.warning("PDF en %s excede límite de %d páginas (%d), truncando.", pdf_url, _MAX_PDF_PAGES_EXTRACT, len(reader.pages))
                        pdf_text_full = " ".join([page.extract_text() or "" for page in reader.pages[:_MAX_PDF_PAGES_EXTRACT]])
                    except Exception as exc:
                        logger.debug(f"Excepción controlada en crawling: {exc}")
                        pass

                    # Comprobar si alguna sección o anexo en cualquier página del PDF contiene la titulación objetivo
                    from parsers import RE_DEGREE_SECTION_MARKERS, RE_PREAMBLE_REJECTION
                    found_match_in_doc = False
                    for pattern in RE_DEGREE_SECTION_MARKERS:
                        for match in pattern.finditer(pdf_text_full):
                            sec_raw = match.group(0).strip()
                            if RE_PREAMBLE_REJECTION.search(sec_raw):
                                continue
                            sec_kw = extract_degree_core_keywords(sec_raw, u_name)
                            if is_section_matching(sec_kw, target_kw):
                                found_match_in_doc = True
                                break
                        if found_match_in_doc:
                            break

                    if not found_match_in_doc:
                        pdf_full_kw = extract_degree_core_keywords(pdf_text_full + " " + url_clean, u_name)
                        if not is_section_matching(pdf_full_kw, target_kw):
                            return None
                return parsed
        except Exception as exc:
            logger.debug(f"Excepción controlada en crawling: {exc}")
            pass
        finally:
            if os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except Exception as exc:
                    logger.debug(f"Excepción controlada en crawling: {exc}")
                    pass
        return None

    def _score_academic_hub_link(self, full_link: str, text: str) -> int:
        """Calcula la prioridad semántica de un enlace para la cola de hubs de catálogo."""
        u_low = full_link.lower()
        t_low = text.lower()

        # 1. Penalizar departamentos, noticias, páginas administrativas y títulos propios no oficiales
        if any(m in u_low for m in NON_ACADEMIC_DEMOTION_MARKERS):
            return -50

        score = 0
        parsed = urllib.parse.urlparse(full_link)
        clean_path = parsed.path.rstrip("/")
        is_leaf_degree = bool(re.search(r"/(?:grado|grau|master|postgrado)-[a-z0-9_-]+", clean_path.lower()))

        # 2. Bonificación máxima para catálogos maestros y portales de oferta oficial de grados/másteres (no fichas individuales)
        master_catalog_patterns = [
            "/estudios/grado", "/estudios/master", "/grados", "/graus", "/titulaciones",
            "/oferta-academica", "/estudis/graus", "/estudis/masters", "/titulacions",
            "/oferta-formativa", "/estudios-ofertados", "/planes-de-estudio", "/titulaciones-oficiales"
        ]
        if not is_leaf_degree and any(clean_path.lower().endswith(p) or p in clean_path.lower() for p in master_catalog_patterns):
            score += 80
        elif is_leaf_degree:
            score += 15

        # 3. Bonificación por subdominios especializados en gestión docente
        if any(sp in u_low for sp in ACADEMIC_SUBDOMAIN_PREFIXES):
            score += 50

        # 4. Bonificación por catálogos maestros y planes de estudio generales
        for k in HUB_ACADEMIC_KEYWORDS:
            if k in u_low:
                score += 15
            if k in t_low:
                score += 10

        # 5. Bonificación por facultades y centros
        if any(k in u_low or k in t_low for k in ["facultad", "facultat", "facultade", "eskola", "escuela", "centro", "centre"]):
            score += 10

        # 6. Bonificación por términos directos de titulación / currículo
        if any(k in u_low or k in t_low for k in ["plan-de-estudios", "plan-estudios", "estructura", "malla", "asignaturas", "grau", "grado", "master", "máster"]):
            score += 20

        # 7. Preferir rutas cortas y limpias sin parámetros de ordenación/paginación
        if "?" in full_link:
            score -= 25

        path_segs = [p for p in clean_path.split("/") if p]
        if len(path_segs) <= 2:
            score += 5

        return score

    @staticmethod
    def _has_explicit_academic_hub_signal(full_link: str, text: str) -> bool:
        """Evita que la detección estructural convierta la navegación global en hubs."""
        context = unicodedata.normalize(
            "NFKD", f"{full_link or ''} {text or ''}"
        ).encode("ASCII", "ignore").decode("ascii").lower()
        markers = tuple(HUB_ACADEMIC_KEYWORDS) + tuple(ACADEMIC_SUBPAGE_KEYWORDS) + (
            "curricul", "curriculo", "programme", "programa", "degree", "course",
            "catalog", "catalogo", "catalogue", "titul",
        )
        return any(marker in context for marker in markers)

    def _build_academic_catalog_map(
        self, 
        downloader: RUCTDownloader, 
        web_url: str, 
        max_depth: int = HUB_AND_SPOKE_MAX_DEPTH, 
        max_hubs: int = HUB_AND_SPOKE_MAX_HUBS,
        max_hops: int = HUB_AND_SPOKE_MAX_HOPS
    ) -> dict:
        """
        Patrón Hub-and-Spoke Catalog Indexing Autónomo con Priority Queue Semántico y descubrimiento de subdominios.
        Descarga de forma secuencial y cortés (respetando REQUEST_DELAY y robots.txt)
        los catálogos maestros y sub-hubs descubiertos dinámicamente mediante topología DOM,
        priorizando portales académicos y subdominios docentes sobre departamentos y páginas administrativas.
        """
        catalog_map = defaultdict(list)
        seen_hubs = {web_url.rstrip("/")}
        seen_deg_urls = set()
        seen_organic_domains = set()
        organic_hubs = {}
        try:
            max_indexed_urls = max(1, int(HUB_AND_SPOKE_MAX_INDEXED_URLS))
        except (TypeError, ValueError):
            max_indexed_urls = 12000
        try:
            max_links_per_token = max(1, int(HUB_AND_SPOKE_MAX_LINKS_PER_TOKEN))
        except (TypeError, ValueError):
            max_links_per_token = 96

        def index_catalog_link(url: str, title: str, priority: int = 0) -> bool:
            """Indexa un enlace una sola vez y con cotas de memoria explícitas."""
            if not url or len(seen_deg_urls) >= max_indexed_urls:
                return False
            normalized = url.rstrip("/")
            if normalized in seen_deg_urls:
                return False
            seen_deg_urls.add(normalized)
            raw_tokens = re.findall(
                r"\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}\b",
                f"{title or ''} {url}",
            )
            all_tokens = set()
            for word in raw_tokens:
                word_low = word.lower()
                all_tokens.add(word_low)
                word_norm = unicodedata.normalize("NFKD", word_low).encode("ASCII", "ignore").decode("utf-8")
                all_tokens.add(word_norm)
                if word_norm.endswith("s") and len(word_norm) > 4:
                    all_tokens.add(word_norm[:-1])
                if word_norm.endswith("es") and len(word_norm) > 5:
                    all_tokens.add(word_norm[:-2])
            for token in all_tokens:
                entries = catalog_map[token]
                if len(entries) >= max_links_per_token:
                    continue
                entry = (url, title)
                if priority >= 20:
                    entries.insert(0, entry)
                else:
                    entries.append(entry)
            return True
        
        # Priority Queue: tuplas de (-puntuacion_prioridad, nivel_salto, contador_insercion, url_hub, salto_actual)
        pq = []
        insertion_counter = 0
        heapq.heappush(pq, (-100, 0, insertion_counter, web_url, 0))
        visited_hubs_count = 0

        while pq and visited_hubs_count < max_hubs:
            neg_prio, current_hop, _, current_hub, _ = heapq.heappop(pq)
            visited_hubs_count += 1
            
            try:
                html_content = downloader.fetch_text(current_hub)
                if not html_content:
                    continue
                is_xml = html_content.lstrip().startswith("<?xml")
                parser_type = "xml" if is_xml else "html.parser"
                try:
                    soup = BeautifulSoup(html_content, parser_type)
                except Exception:
                    soup = BeautifulSoup(html_content, "html.parser")
                
                # Capa 3: Ascenso Jerárquico por Migas de Pan (Breadcrumbs)
                if current_hop < max_hops:
                    for bc_hub in extract_breadcrumb_parent_hubs(soup, current_hub, web_url):
                        norm_bc = bc_hub.rstrip("/")
                        if norm_bc not in seen_hubs and len(seen_hubs) < max_hubs * 2:
                            seen_hubs.add(norm_bc)
                            insertion_counter += 1
                            bc_prio = self._score_academic_hub_link(bc_hub, "")
                            heapq.heappush(pq, (-max(bc_prio, 10), current_hop + 1, insertion_counter, bc_hub, current_hop + 1))

                # Capa 4, 5 y 6: Extracción de fuentes dinámicas (JSON-LD, Formularios Select y Eventos JS)
                dynamic_candidates = []
                dynamic_candidates.extend(extract_hydration_payload_degrees(soup, current_hub))
                dynamic_candidates.extend(extract_form_select_academic_options(soup, current_hub))
                dynamic_candidates.extend(extract_js_event_links(soup, current_hub))

                for dyn_url, dyn_title in dynamic_candidates:
                    norm_dyn = dyn_url.rstrip("/")
                    if is_valid_web_url(dyn_url) and is_same_or_subdomain(dyn_url, web_url):
                        index_catalog_link(dyn_url, dyn_title)

                # Capa 1 y 2: Enlaces hipertexto estándar con evaluación heurística de HUB y Priority Queue
                for a in soup.find_all("a", href=True):
                    h = a["href"].strip()
                    if not is_valid_web_url(h):
                        continue
                    
                    full_link = urllib.parse.urljoin(current_hub, h)
                    norm_link = full_link.rstrip("/")
                    t_text = a.get_text(strip=True)
                    t_low = t_text.lower()
                    h_low = h.lower()
                    
                    if not is_same_or_subdomain(full_link, web_url):
                        # Descubrimiento orgánico de Centros Adscritos y Alianzas Europeas
                        if full_link.startswith("http") and any(k in t_low or k in h_low for k in ORGANIC_AFFILIATED_HUB_KEYWORDS):
                            parsed_ext = urllib.parse.urlparse(full_link)
                            external_root = parsed_ext.netloc.lower().removeprefix("www.")
                            if (
                                external_root in ORGANIC_EXTERNAL_DOMAIN_DENYLIST
                                or not is_authorized_external_academic_hub(full_link, t_text)
                            ):
                                continue
                            ext_domain = f"{parsed_ext.scheme}://{parsed_ext.netloc}"
                            if ext_domain not in seen_organic_domains and len(organic_hubs) < MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV:
                                seen_organic_domains.add(ext_domain)
                                hub_name = t_text.strip() if len(t_text.strip()) >= 3 else parsed_ext.netloc
                                organic_hubs[ext_domain] = (full_link, hub_name)
                        continue
                        
                    # 1. Detección dinámica y encolado prioritario de Sub-HUBs de catálogo
                    link_priority = self._score_academic_hub_link(full_link, t_text)
                    dynamic_academic_hub = (
                        is_dynamic_academic_hub(soup, a, full_link, web_url)
                        and self._has_explicit_academic_hub_signal(full_link, t_text)
                    )
                    if current_hop < max_hops and (
                        link_priority >= HUB_AND_SPOKE_MIN_PRIORITY
                        or dynamic_academic_hub
                    ):
                        if norm_link not in seen_hubs and len(seen_hubs) < max_hubs * 2:
                            seen_hubs.add(norm_link)
                            insertion_counter += 1
                            heapq.heappush(pq, (-link_priority, current_hop + 1, insertion_counter, full_link, current_hop + 1))
                            
                    # 2. Indexación en catalog_map de páginas de titulación y planes docentes
                    if len(t_text) >= 4 and not is_spider_trap_or_spurious_url(full_link, t_text):
                        parsed_u = urllib.parse.urlparse(h)
                        depth = len([p for p in parsed_u.path.strip("/").split("/") if p])
                        if depth <= max_depth:
                            # Desambiguación: insertar al principio las páginas
                            # con marcadores de titulación, manteniendo además
                            # una cota global y otra por término.
                            index_catalog_link(full_link, t_text, link_priority)
            except Exception as exc:
                logger.debug(f"Excepción controlada en crawling: {exc}")
                continue
                
        if organic_hubs:
            with self.organic_lock:
                self.organic_affiliated_hubs[web_url].update(organic_hubs)
        return catalog_map

    def rescue_university_url(self, univ_name: str) -> str:
        """
        Consulta la API pública de Wikipedia y Wikidata para recuperar el sitio web oficial de una institución.
        """
        search_url = WIKIPEDIA_API_URL
        search_params = {
            "action": "query", "list": "search", "srsearch": univ_name,
            "format": "json", "utf8": 1, "srlimit": 1
        }
        
        rescue_downloader = RUCTDownloader(delay=REQUEST_DELAY, timeout=min(self.timeout, 15), ledger=self.ledger, phase="fase1_parte2_rescue")
        def get_json(base_url, params):
            query_url = base_url + ("&" if "?" in base_url else "?") + urllib.parse.urlencode(params)
            content = rescue_downloader.fetch_content(query_url)
            return json.loads(content) if content else {}
        try:
            data = get_json(search_url, search_params)
            if not data.get("query", {}).get("search"):
                return None
                
            title = data["query"]["search"][0]["title"]
            prop_params = {"action": "query", "prop": "pageprops", "titles": title, "format": "json"}
            prop_data = get_json(search_url, prop_params)
            
            pages = prop_data.get("query", {}).get("pages", {})
            page = list(pages.values())[0]
            wikibase_item = page.get("pageprops", {}).get("wikibase_item")
            
            if not wikibase_item:
                return None
                
            wikidata_url = WIKIDATA_API_URL
            wd_params = {"action": "wbgetentities", "ids": wikibase_item, "props": "claims", "format": "json"}
            wd_data = get_json(wikidata_url, wd_params)
            
            claims = wd_data.get("entities", {}).get(wikibase_item, {}).get("claims", {})
            website_claims = claims.get("P856", [])
            
            if website_claims:
                return website_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        except Exception as exc:
            logger.debug(f"Excepción controlada en crawling: {exc}")
            pass
        finally:
            rescue_downloader.close()
        return None

    def check_robots_allowed(self, target_url: str) -> tuple[bool, float | None]:
        """
        Verifica el archivo robots.txt de la web oficial de la universidad con caché 24h.
        Devuelve tupla (can_fetch, crawl_delay):
        - can_fetch: True si el rastreo está permitido para nuestro User-Agent / *, False en caso contrario.
        - crawl_delay: Tiempo de espera en segundos declarado en robots.txt (o None si no existe).
        """
        policy = RobotsPolicy(user_agent=self.user_agent, timeout=ROBOTS_CHECK_TIMEOUT)
        allowed, crawl_delay = policy.check(target_url)
        parsed = urllib.parse.urlparse(target_url)
        origin = f"{parsed.scheme}://{parsed.netloc.lower()}" if parsed.scheme and parsed.netloc else target_url
        with self._robots_lock:
            self._robots_cache[origin] = (time.time(), allowed, crawl_delay)
        if not allowed:
            logger.warning("[robots.txt] Acceso denegado o política no disponible para %s", target_url)
        return allowed, crawl_delay

    def _extract_recursive_sitemap_candidates(self, base_url: str, missing_degrees: list = None) -> set:
        """Recorre sitemaps e indices XML del origen autorizado con limites estrictos."""
        parsed = urllib.parse.urlparse(str(base_url or ""))
        if not parsed.scheme or not parsed.netloc:
            return set()

        title_tokens = set()
        for degree in missing_degrees or []:
            title = unicodedata.normalize(
                "NFKD", str(degree.get("titulo", "") or "")
            ).encode("ASCII", "ignore").decode("ascii").lower()
            for token in re.findall(r"\b[a-z0-9]{4,}\b", title):
                if token not in {
                    "grado", "grados", "master", "masters", "masteres", "universidad",
                    "universidades", "estudios", "oficial", "oficiales", "titulacion",
                    "titulaciones", "doctorado", "doctorados", "universitario",
                }:
                    title_tokens.add(token)

        origin = f"{parsed.scheme}://{parsed.netloc}"
        queue = deque(
            [
                f"{origin}/robots.txt",
                f"{origin}/sitemap.xml",
                f"{origin}/sitemap_index.xml",
                f"{origin}/sitemap.xml.gz",
                f"{origin}/sitemap_index.xml.gz",
                f"{origin}/sitemap-estudios.xml",
                f"{origin}/sitemap-grados.xml",
            ]
        )
        seen_sitemaps = set()
        candidates = set()
        max_sitemaps = min(64, max(16, 8 + 4 * len(missing_degrees or [])))
        max_locations = min(4000, max(200, 50 * len(missing_degrees or []) or 200))
        downloader = RUCTDownloader(
            delay=WEB_PROBE_DELAY,
            timeout=SITEMAP_FETCH_TIMEOUT,
            metrics_tracker=self.metrics_tracker,
            ledger=self.ledger,
            phase="fase1_parte2_sitemap_recursive",
        )
        try:
            while queue and len(seen_sitemaps) < max_sitemaps and len(candidates) < max_locations:
                sitemap_url = queue.popleft()
                normalized_sitemap = sitemap_url.rstrip("/")
                if normalized_sitemap in seen_sitemaps:
                    continue
                if not is_same_or_subdomain(sitemap_url, base_url):
                    continue
                seen_sitemaps.add(normalized_sitemap)
                try:
                    allowed, _ = self.check_robots_allowed(sitemap_url)
                    if not allowed:
                        continue
                    raw = downloader.fetch_content(sitemap_url)
                    if not raw:
                        continue
                    if sitemap_url.lower().endswith("/robots.txt"):
                        text = raw.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            if line.lower().startswith("sitemap:") and ":" in line:
                                declared = line.split(":", 1)[1].strip()
                                if declared and is_same_or_subdomain(declared, base_url):
                                    queue.append(declared)
                        continue
                    parsed_sitemap = parse_sitemap_locations(
                        raw, sitemap_url, max_locations=max_locations
                    )
                    locations = parsed_sitemap.get("locations", [])
                    if parsed_sitemap.get("kind") == "index":
                        for child in locations:
                            child_path = urllib.parse.urlparse(child).path.lower()
                            if (
                                is_same_or_subdomain(child, base_url)
                                and ("sitemap" in child_path or child_path.endswith((".xml", ".xml.gz", ".gz")))
                            ):
                                queue.append(child)
                        continue
                    for location in locations:
                        if not is_same_or_subdomain(location, base_url):
                            continue
                        location_low = location.lower()
                        if any(marker in location_low for marker in ACADEMIC_KEYWORDS) or (
                            title_tokens and any(token in location_low for token in title_tokens)
                        ):
                            candidates.add(location)
                            if len(candidates) >= max_locations:
                                break
                except Exception as exc:
                    logger.debug("No se pudo procesar sitemap %s: %s", sitemap_url, exc)
        finally:
            downloader.close()
        return candidates

    def extract_sitemap_candidate_urls(self, base_url: str, missing_degrees: list = None) -> set:
        """
        Extrae y pre-procesa el Sitemap XML de la universidad (incluyendo archivos .xml.gz comprimidos)
        para detectar directamente las URLs disponibles en el sitio web de la universidad.
        Optimización: Timeout ajustado a SITEMAP_FETCH_TIMEOUT y filtrado selectivo según keywords y grados faltantes.
        """
        sitemap_candidate_urls = set()
        parsed = urllib.parse.urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return sitemap_candidate_urls

        recursive_candidates = self._extract_recursive_sitemap_candidates(
            base_url, missing_degrees=missing_degrees
        )
        if recursive_candidates:
            return recursive_candidates

        domain_base = f"{parsed.scheme}://{parsed.netloc}"
        sitemap_targets = [
            f"{domain_base}/sitemap.xml",
            f"{domain_base}/sitemap.xml.gz",
            f"{domain_base}/sitemap_index.xml",
            f"{domain_base}/sitemap_index.xml.gz",
            f"{domain_base}/sitemap-grados.xml",
            f"{domain_base}/sitemap-estudios.xml"
        ]

        title_tokens = set()
        if missing_degrees:
            for deg in missing_degrees:
                t = deg.get("titulo", "").lower()
                words = [w for w in re.findall(r"\b[a-záéíóúñ]{4,}\b", t) if w not in ["grado", "graduada", "graduado", "master", "máster", "universidad", "estudios", "oficial", "titulacion", "titulación"]]
                title_tokens.update(words[:3])

        downloader = RUCTDownloader(delay=WEB_PROBE_DELAY, timeout=SITEMAP_FETCH_TIMEOUT, metrics_tracker=self.metrics_tracker, ledger=self.ledger, phase="fase1_parte2_sitemap")
        try:
            for sm_url in sitemap_targets:
                try:
                    can_fetch, _ = self.check_robots_allowed(sm_url)
                    if not can_fetch:
                        continue
                    raw_bytes = downloader.fetch_content(sm_url)
                    if not raw_bytes:
                        continue

                    if sm_url.endswith(".gz") or raw_bytes.startswith(b"\x1f\x8b"):
                        try:
                            raw_bytes = gzip.decompress(raw_bytes)
                        except Exception as exc:
                            logger.debug(f"Excepción controlada en crawling: {exc}")
                            pass

                    xml_content = raw_bytes.decode("utf-8", errors="replace")
                    if xml_content and ("<urlset" in xml_content or "<sitemapindex" in xml_content or "<loc>" in xml_content):
                        print(f"     [Sitemap] Sitemap XML detectado y analizado en '{sm_url}'.")
                        locs = re.findall(r"<loc>(.*?)</loc>", xml_content, re.IGNORECASE)
                        for loc in locs:
                            loc_clean = loc.strip()
                            loc_lower = loc_clean.lower()
                            if any(kw in loc_lower for kw in ACADEMIC_KEYWORDS):
                                sitemap_candidate_urls.add(loc_clean)
                            elif title_tokens and any(tok in loc_lower for tok in title_tokens):
                                sitemap_candidate_urls.add(loc_clean)
                        if sitemap_candidate_urls:
                            break
                except Exception as exc:
                    logger.debug(f"Excepción controlada en crawling: {exc}")
                    continue
        finally:
            downloader.close()

        return sitemap_candidate_urls

    def process_university_web(self, univ: dict, titulaciones_por_univ: dict, force: bool = False) -> dict:
        """
        Procesa una universidad en la Parte 2:
        1. Comprueba si tiene web oficial.
        2. Identifica titulaciones sin plan de estudios.
        3. Verifica permiso en robots.txt.
        4. Accede previamente al Sitemap XML (si existe) y escanea el portal académico con sinónimos ampliados.
        """
        full_revalidation = bool(FULL_REVALIDATION or force)
        rediscover_urls = bool(REDISCOVER_URLS_EVERY_RUN or full_revalidation)
        u_code = univ.get("codigo", "")
        u_name = univ.get("nombre", "")
        u_type = univ.get("tipo", "")
        web_url = (univ.get("web") or univ.get("url") or univ.get("web_url") or "").strip()
        # Sanitización de inputs externos
        if not re.fullmatch(r"[A-Z0-9]{3,6}", str(u_code)):
            logger.warning(f"Código de universidad inválido descartado: {u_code}")
            return {"u_code": u_code, "u_name": u_name, "has_web": False, "robots_allowed": False}

        stats = {
            "u_code": u_code,
            "u_name": u_name,
            "has_web": bool(web_url),
            "robots_allowed": True,
            "missing_degrees_count": 0,
            "resolved_degrees_count": 0
        }

        # 1. Comprobar si existe enlace a su página web oficial y forzar protocolo HTTPS
        if not web_url:
            logger.info(f"[Parte 2] Universidad [{u_code}] {u_name}: Sin web oficial registrada. Finalizado.")
            return stats

        web_url = ensure_https_url(web_url)
        registered_web_url = web_url

        # 2. Identificar titulaciones sin información del plan de estudios
        if isinstance(titulaciones_por_univ, list):
            active_degrees = titulaciones_por_univ
        else:
            univ_data = titulaciones_por_univ.get(u_code, {})
            active_degrees = univ_data.get("titulaciones_vigentes", []) if isinstance(univ_data, dict) else (univ_data or [])
        
        missing_degrees = []
        doctorate_degrees = []
        for deg in active_degrees:
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            d_level = deg.get("nivel_academico", "")

            # Los programas de doctorado (RD 99/2011) no tienen asignaturas docentes regladas; consisten en investigación tutelada.
            if is_doctorate_program(d_level, d_title):
                if needs_web_resolution(find_plan_filepath(u_code, d_code), force=force):
                    doctorate_degrees.append(deg)
                continue

            plan_file = find_plan_filepath(u_code, d_code)
            
            # La Parte 1 ya redescubre y verifica cada titulación en cada
            # ejecución. La Parte 2 es una vía de recuperación, no un segundo
            # rastreo general: solo debe consultar la web oficial si Parte 1
            # no dejó un plan completo y verificado para esta titulación.
            if needs_web_resolution(plan_file, force=force):
                missing_degrees.append(deg)

        stats["missing_degrees_count"] = len(missing_degrees)
        stats["doctorates_pending_count"] = len(doctorate_degrees)

        # El checkpoint no evita volver a consultar robots.txt en modo
        # revalidante: sus reglas y permisos pueden cambiar entre ejecuciones.
        # La decisión se toma después de contabilizar las cohortes para que un
        # bloqueo técnico no se presente como ``0/0`` y no oculte trabajo
        # pendiente en los manifiestos de campaña.
        if (
            not full_revalidation
            and self.checkpoint.is_robots_denied_university(
                u_code,
                max_age_seconds=ROBOTS_DENIED_RETRY_TTL_SECONDS,
            )
            and not force
        ):
            logger.info(
                "[checkpoint] Universidad %s denegada recientemente; se omite hasta caducar el TTL de reintento.",
                u_code,
            )
            stats["robots_allowed"] = False
            return stats

        if not missing_degrees and not doctorate_degrees:
            logger.info("Universidad [%s] %s: sin titulaciones web rastreables (p. ej. doctorados).", u_code, u_name)
            return stats

        logger.info("Universidad [%s] %s: %d titulaciones no resueltas por la Parte 1. Verificando conectividad en '%s'...", u_code, u_name, len(missing_degrees), web_url)

        # 2.5 robots.txt debe autorizar antes de cualquier petición de conectividad.
        can_fetch, crawl_delay = self.check_robots_allowed(web_url)
        if not can_fetch:
            # El origen principal puede estar bloqueado aunque un subportal
            # académico oficial ya evidenciado tenga una política permisiva.
            # Se prueba primero esa evidencia acotada antes de consultar una
            # fuente externa de rescate.
            for academic_origin in stored_academic_origins(
                missing_degrees + doctorate_degrees,
                web_url,
                u_code,
            ):
                alternate_allowed, alternate_delay = self.check_robots_allowed(academic_origin)
                if alternate_allowed:
                    logger.info(
                        "[ORIGEN ACADÉMICO] Se continúa por un subportal oficial ya evidenciado: %s",
                        academic_origin,
                    )
                    web_url = academic_origin
                    can_fetch, crawl_delay = alternate_allowed, alternate_delay
                    break

            if not can_fetch:
                # Si el origen registrado no responde o no tiene robots.txt
                # disponible, comprobar si Wikidata conoce la URL oficial activa.
                logger.warning("[AVISO ROBOTS] Universidad [%s] %s: fallo al comprobar robots en '%s'. Consultando URL alternativa...", u_code, u_name, web_url)
                rescued_url = self.rescue_university_url(u_name)
                if rescued_url:
                    cand_rescued = ensure_https_url(rescued_url)
                    if cand_rescued != web_url:
                        web_url = cand_rescued
                        logger.info("[RESCATE OK] URL actualizada por Wikidata para [%s]: %s", u_code, web_url)
                        can_fetch, crawl_delay = self.check_robots_allowed(web_url)

        if not can_fetch:
            logger.warning("[BLOQUEO ROBOTS] Universidad [%s] %s: acceso denegado en %s.", u_code, u_name, web_url)
            self.checkpoint.mark_robots_denied_university(u_code, web_url, "Crawling denegado o robots.txt no disponible")
            _annotate_plan_source_status(missing_degrees, u_code, "robots_denegado_conservando_anterior", u_name)
            stats["robots_allowed"] = False
            return stats

        # 2.6 Test de conectividad y Protocolo de Rescate (Wikipedia API)
        conn_downloader = RUCTDownloader(delay=WEB_PROBE_DELAY, timeout=WEB_CONNECTIVITY_TIMEOUT, ledger=self.ledger, phase="fase1_parte2_probe")
        conn_downloader.reset_university_context(u_code, u_name, web_url)
        try:
            conn_downloader.fetch_content(web_url)
            if conn_downloader.last_final_url:
                web_url = conn_downloader.last_final_url
                _persist_canonical_university_url(u_code, registered_web_url, web_url)
        except Exception as conn_err:
            # Un portal raíz puede resolver o responder de forma distinta al
            # subportal académico que ya aportó una fuente curricular válida.
            # Reintentar primero esos orígenes, con robots independiente,
            # evita abandonar recuperaciones accesibles y no inventa dominios.
            rescued_url = None
            rescued_from_stored_academic = False
            rescued_from_protocol_fallback = False
            rescued_from_search_origin = False
            for academic_origin in stored_academic_origins(
                missing_degrees + doctorate_degrees,
                registered_web_url,
                u_code,
            ):
                alternate_allowed, _ = self.check_robots_allowed(academic_origin)
                if not alternate_allowed:
                    continue
                try:
                    conn_downloader.reset_university_context(u_code, u_name, academic_origin)
                    conn_downloader.fetch_content(academic_origin)
                    rescued_url = academic_origin
                    rescued_from_stored_academic = True
                    logger.info(
                        "[RESCATE ACADÉMICO] Origen alternativo oficial accesible: %s",
                        academic_origin,
                        )
                    break
                except Exception as academic_err:
                    logger.debug(
                        "No responde el origen académico alternativo %s: %s",
                        academic_origin,
                        academic_err,
                    )
            if not rescued_url:
                protocol_fallback = http_protocol_fallback_url(web_url)
                if protocol_fallback:
                    alternate_allowed, _ = self.check_robots_allowed(protocol_fallback)
                    if alternate_allowed:
                        try:
                            conn_downloader.reset_university_context(u_code, u_name, protocol_fallback)
                            conn_downloader.fetch_content(protocol_fallback)
                            rescued_url = conn_downloader.last_final_url or protocol_fallback
                            rescued_from_protocol_fallback = True
                            logger.info(
                                "[RESCATE PROTOCOLO] Origen HTTP alternativo accesible para [%s]: %s",
                                u_code,
                                rescued_url,
                            )
                        except Exception as protocol_err:
                            logger.debug(
                                "No responde el fallback HTTP del origen %s: %s",
                                protocol_fallback,
                                protocol_err,
                            )
            if not rescued_url:
                # Rescate genérico de dominios institucionales obsoletos. El
                # buscador sólo propone una raíz; robots y conectividad deben
                # confirmar el destino antes de continuar.
                search_origin_result = discover_institutional_origins(
                    u_name,
                    registered_web_url,
                    conn_downloader.fetch_text,
                    query_limit=1,
                    result_limit=8,
                )
                stats["web_search_origin_queries"] = len(search_origin_result.get("queries", []))
                stats["web_search_origin_candidates"] = len(search_origin_result.get("records", []))
                stats["web_search_origin_errors"] = len(search_origin_result.get("errors", []))
                stats["web_search_origin_error_kinds"] = sorted(
                    {str(error) for error in search_origin_result.get("errors", [])}
                )
                for origin_record in search_origin_result.get("records", []):
                    candidate_origin_url = str(origin_record.get("url") or "").strip()
                    allowed_origin, _ = self.check_robots_allowed(candidate_origin_url)
                    if not allowed_origin:
                        continue
                    try:
                        conn_downloader.reset_university_context(u_code, u_name, candidate_origin_url)
                        conn_downloader.fetch_content(candidate_origin_url)
                        rescued_url = conn_downloader.last_final_url or candidate_origin_url
                        rescued_from_search_origin = True
                        stats["web_search_origin_recoveries"] = stats.get("web_search_origin_recoveries", 0) + 1
                        logger.info(
                            "[RESCATE BUSCADOR] Origen institucional alternativo accesible para [%s]: %s",
                            u_code,
                            rescued_url,
                        )
                        break
                    except Exception as search_origin_err:
                        logger.debug(
                            "No responde el origen institucional propuesto %s: %s",
                            candidate_origin_url,
                            search_origin_err,
                        )
            if not rescued_url:
                logger.info("[RESCATE] Web '%s' inalcanzable (%s). Consultando Wikipedia/Wikidata...", web_url, conn_err)
                rescued_url = self.rescue_university_url(u_name)
            if rescued_url:
                web_url = ensure_https_url(rescued_url)
                if rescued_from_stored_academic or rescued_from_protocol_fallback or rescued_from_search_origin:
                    logger.info("[RESCATE OK] Origen académico oficial ya evidenciado para [%s]: %s", u_code, web_url)
                    _persist_canonical_university_url(u_code, registered_web_url, web_url)
                else:
                    logger.info("[RESCATE OK] URL corregida por Wikidata para [%s]: %s", u_code, web_url)

                    # Actualizar permanentemente en universidades.json sólo
                    # cuando la fuente procede de Wikidata.
                    with self.univ_file_lock:
                        if os.path.exists(UNIVERSIDADES_JSON):
                            try:
                                with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
                                    all_univs = json.load(f)
                                for unv in all_univs:
                                    if unv.get("codigo") == u_code:
                                        unv["web"] = web_url
                                        unv["web_corregida_por_wikidata"] = True
                                        break
                                atomic_json_dump(all_univs, UNIVERSIDADES_JSON)
                            except Exception as file_err:
                                logger.warning("No se pudo persistir la URL corregida en el JSON: %s", file_err)
            else:
                logger.warning("[RESCATE FALLIDO] No se pudo encontrar web alternativa en Wikipedia para [%s].", u_code)
                self.checkpoint.record_pdf_download_failure(web_url, "ALL", f"Web principal caída/errónea. Rescate fallido: {conn_err}")
                _annotate_plan_source_status(missing_degrees, u_code, "web_no_disponible_conservando_anterior", u_name)
                stats["robots_allowed"] = False
                return stats
        finally:
            conn_downloader.close()

        # 3. Si se ha rescatado la URL, volver a validar su origen y robots.txt.
        can_fetch, crawl_delay = self.check_robots_allowed(web_url)
        if not can_fetch:
            logger.warning("[BLOQUEO ROBOTS] Universidad [%s] %s: Crawling DENEGADO por robots.txt en %s.", u_code, u_name, web_url)
            self.checkpoint.mark_robots_denied_university(u_code, web_url, "Crawling denegado por robots.txt")
            _annotate_plan_source_status(missing_degrees, u_code, "robots_denegado_conservando_anterior", u_name)
            stats["robots_allowed"] = False
            return stats

        effective_delay = max(crawl_delay, 0.5) if crawl_delay and crawl_delay > 0 else 0.5
        delay_msg = f" (Crawl-delay declarado en robots.txt: {crawl_delay:.1f}s)" if crawl_delay else ""
        logger.info("[PERMITIDO ROBOTS] Universidad [%s] %s: Crawling PERMITIDO por robots.txt%s. Iniciando escaneo web...", u_code, u_name, delay_msg)

        # 4. Acceso previo al Sitemap XML del portal académico (respetando retardo oficial)
        downloader = RUCTDownloader(delay=effective_delay, timeout=WEB_CONTENT_TIMEOUT, metrics_tracker=self.metrics_tracker, ledger=self.ledger, phase="fase1_parte2_web")
        downloader.reset_university_context(u_code, u_name, web_url)
        try:
            crawl_result = self._crawl_university_degrees(
                downloader, u_code, u_name, web_url, missing_degrees, stats, u_type=u_type, force=force
            )
        finally:
            downloader.close()

        # El rastreo ordinario no debe cortar la ejecución antes de procesar
        # los doctorados. Tienen un modelo propio y se ejecutan después de
        # cerrar el downloader general para respetar sus límites de red.
        if doctorate_degrees:
            logger.info(
                "[DOCTORADOS] Universidad [%s] %s: procesando %d programas pendientes...",
                u_code, u_name, len(doctorate_degrees),
            )
            doctoral_downloader = RUCTDownloader(
                delay=effective_delay,
                timeout=WEB_CONTENT_TIMEOUT,
                metrics_tracker=self.metrics_tracker,
                ledger=self.ledger,
                phase="fase1_parte2_doctorado",
            )
            doctoral_downloader.reset_university_context(u_code, u_name, web_url)
            try:
                # Reutilizar el índice académico que ya se construyó para la
                # misma universidad. Pasar {} aquí dejaba los doctorados sin
                # candidatos aunque su página oficial estuviera indexada.
                doctoral_catalog_map = crawl_result.pop("_catalog_map", {}) if isinstance(crawl_result, dict) else {}
                doctoral_sitemap_urls = crawl_result.pop("_sitemap_urls", []) if isinstance(crawl_result, dict) else []
                doc_stats = self.process_university_doctorates(
                    u_code, u_name, doctorate_degrees, web_url, doctoral_downloader,
                    doctoral_catalog_map, force=force, sitemap_urls=doctoral_sitemap_urls
                )
            finally:
                doctoral_downloader.close()
            crawl_result["resolved_degrees_count"] = crawl_result.get("resolved_degrees_count", 0) + doc_stats.get("resolved_doctorates", 0)
            crawl_result["doctorates_processed"] = doc_stats.get("total_doctorates", 0)
            crawl_result["doctorates_resolved"] = doc_stats.get("resolved_doctorates", 0)
        return crawl_result

    def _crawl_university_degrees(self, downloader: RUCTDownloader, u_code: str, u_name: str, 
                                  web_url: str, missing_degrees: list, stats: dict, u_type: str = "", force: bool = False) -> dict:
        """Recorre y extrae los planes de estudio de las titulaciones de una universidad."""
        sitemap_urls = set()
        catalog_map = {}
        crawl_origins = [web_url]
        discovered_academic_origins = set()
        discovery_loaded = False

        def ensure_discovery_index(include_hubs: bool = True):
            """Carga sitemaps y, opcionalmente, hubs tras las rutas baratas."""
            nonlocal sitemap_urls, catalog_map, crawl_origins, discovered_academic_origins, discovery_loaded
            if discovery_loaded:
                return
            related_academic_origins = []
            try:
                home_html = downloader.fetch_text(web_url)
                if home_html:
                    home_soup = BeautifulSoup(home_html, "html.parser")
                    related_academic_origins = discover_related_academic_origins(home_soup, web_url)
                    # Algunos CMS sirven todo el portal bajo un prefijo de
                    # contexto y/o idioma que no figura en la URL registrada.
                    # Se deriva de enlaces académicos reales de la portada,
                    # sin hardcodear ningún nombre de institución.
                    base_parts = urllib.parse.urlsplit(web_url)
                    for anchor in home_soup.find_all("a", href=True):
                        href = str(anchor.get("href") or "").strip()
                        full = urllib.parse.urljoin(web_url, href)
                        text = anchor.get_text(" ", strip=True)
                        if not is_valid_web_url(full) or not is_same_or_subdomain(full, web_url):
                            continue
                        if not self._has_explicit_academic_hub_signal(full, text):
                            continue
                        linked_parts = [part for part in urllib.parse.urlsplit(full).path.split("/") if part]
                        if not linked_parts:
                            continue
                        for depth in range(1, min(2, len(linked_parts)) + 1):
                            prefix = "/" + "/".join(linked_parts[:depth])
                            discovered_academic_origins.add(
                                urllib.parse.urlunsplit(
                                    (base_parts.scheme, base_parts.netloc, prefix, "", "")
                                ).rstrip("/")
                            )
            except Exception as exc:
                logger.debug("No se pudieron descubrir hosts académicos relacionados: %s", exc)

            crawl_origins = [web_url] + [origin for origin in related_academic_origins if origin != web_url]
            for origin in crawl_origins:
                if origin != web_url:
                    allowed_origin, _ = self.check_robots_allowed(origin)
                    if not allowed_origin:
                        continue
                sitemap_urls.update(self.extract_sitemap_candidate_urls(origin, missing_degrees=missing_degrees))
                try:
                    official_robots_sitemaps = downloader.robots_policy.get_sitemaps(origin)
                    for r_sm in official_robots_sitemaps:
                        if is_valid_web_url(r_sm) and is_same_or_subdomain(r_sm, origin):
                            sitemap_urls.add(r_sm)
                except Exception as sm_exc:
                    logger.debug("Error leyendo sitemaps de robots para %s: %s", origin, sm_exc)
            if sitemap_urls:
                logger.info("  [%s] %d URLs académicas indexadas extraídas del Sitemap XML.", u_code, len(sitemap_urls))
                if self.ledger:
                    self.ledger.record_discovery_evidence(
                        [{"url": u, "source_kind": "sitemap", "source_url": web_url} for u in sitemap_urls],
                        university_code=u_code,
                        phase="fase1_parte2",
                    )

            # La portada y los sitemaps son evidencia barata. El índice de
            # hubs se difiere hasta que terminen las rutas de ficha, PDF y
            # búsqueda; así una sola titulación no pierde su presupuesto en
            # navegación masiva del portal.
            if not include_hubs:
                return

            for origin in crawl_origins:
                if origin != web_url:
                    allowed_origin, _ = self.check_robots_allowed(origin)
                    if not allowed_origin:
                        continue
                discovered_map = self._build_academic_catalog_map(
                    downloader,
                    origin,
                    max_depth=6,
                    max_hubs=adaptive_hub_budget(len(missing_degrees), HUB_AND_SPOKE_MAX_HUBS),
                )
                merge_bounded_catalog_map(
                    catalog_map,
                    discovered_map,
                    max_indexed_urls=HUB_AND_SPOKE_MAX_INDEXED_URLS,
                    max_links_per_token=HUB_AND_SPOKE_MAX_LINKS_PER_TOKEN,
                )

            persisted_evidence_count = 0
            if self.ledger:
                get_evidence = getattr(self.ledger, "get_discovery_evidence", None)
                if callable(get_evidence):
                    try:
                        persisted_evidence = get_evidence(
                            u_code,
                            limit=max(1, int(HUB_AND_SPOKE_MAX_INDEXED_URLS)),
                            max_age_seconds=ACADEMIC_DISCOVERY_EVIDENCE_TTL_SECONDS,
                        )
                    except (TypeError, ValueError, OSError):
                        persisted_evidence = []
                    persisted_evidence_count = merge_persisted_discovery_evidence(catalog_map, persisted_evidence)
            if persisted_evidence_count:
                stats["persisted_discovery_urls"] = persisted_evidence_count
                logger.info("  [%s] %d URLs académicas reutilizadas desde el ledger persistente.", u_code, persisted_evidence_count)
            for token, links in catalog_map.items():
                unique_links = []
                seen_links = set()
                for link in links:
                    link_key = tuple(link) if isinstance(link, (list, tuple)) else str(link)
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        unique_links.append(link)
                catalog_map[token] = unique_links
            if catalog_map:
                print(f"     -> [Hub-and-Spoke] {len(catalog_map)} términos académicos indexados desde catálogos maestros (Profundidad <= 6).")
                if self.ledger:
                    catalog_records = []
                    for entries in catalog_map.values():
                        for entry in entries:
                            c_url, c_text = entry[:2] if isinstance(entry, (list, tuple)) and len(entry) >= 2 else (str(entry), "")
                            catalog_records.append({"url": c_url, "source_kind": "hub_catalog", "anchor_text": c_text, "source_url": web_url})
                    self.ledger.record_discovery_evidence(catalog_records, university_code=u_code, phase="fase1_parte2")
            discovery_loaded = True

        TITLE_STOPWORDS = {
            "grado", "grados", "graduado", "graduada", "graduats", "graduades", "grau", "graus", "grao", "graos", "gradua", "graduak", "bachelor", "undergraduate",
            "máster", "master", "másteres", "masteres", "màster", "màsters", "masterra", "masterrak", "postgrado", "posgrado", "postgrau", "posgrao", "postgraduate",
            "doctor", "doctora", "doctorado", "doctorados", "doctorat", "doctorats", "doutoramento", "doktoregoa", "doctorate", "phd",
            "universitario", "universitaria", "universitaris", "universitaries", "oficial", "oficials", "programa", "programas", "título", "titulo", "titulacion", "titulaciones", "titulacions",
            "estudio", "estudios", "estudis", "estudos", "ikasketak", "enseñanza", "ensenanza", "mención", "mencion",
            "universidad", "universidades", "universitat", "universitats", "universidade", "unibertsitatea", "university",
            "sobre", "entre", "para", "como", "esta", "este", "estos", "estas", "del", "los", "las", "por", "con", "una", "uno", "que", "sus", "mas", "más",
            "autónoma", "autonoma", "politécnica", "politecnica", "internacional", "nacional", "distancia",
            "en", "the", "and", "for", "of", "in", "to", "i", "de", "a", "el", "la", "l'", "d'", "els", "les", "o", "u"
        }
        
        lazy_home_html = None
        lazy_soup = None
        lazy_candidate_urls = None
        lazy_scanned_pages_cache = {} # Cache dict: candidate_page_url -> (sub_html, sub_soup)
        accepted_source_identities = {}

        # 5. Escaneo/recorrido meticuloso de la web oficial de la universidad
        # Conserva la instrumentación de descubrimiento para una cohorte vacía
        # (útil en auditorías), pero para una cohorte real lo difiere hasta
        # que falle la evidencia directa de la propia titulación.
        if not missing_degrees:
            ensure_discovery_index()

        for d_idx, deg in enumerate(missing_degrees, 1):
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            d_level = deg.get("nivel_academico", "")
            # Comparte el presupuesto por titulación con el downloader para
            # que también cubra esperas de cortesía, reintentos y respuestas
            # lentas; antes sólo protegía el bucle local de candidatos.
            downloader.set_degree_context(d_code)
            plan_file = find_plan_filepath(u_code, d_code)
            existing_plan_data = load_json_safe(plan_file, default={}) if os.path.exists(plan_file) else {}
            boe_resumen = (
                deg.get("resumen_creditos")
                or (deg.get("plan_estudios", {}).get("resumen_creditos") if isinstance(deg.get("plan_estudios"), dict) else None)
                or (existing_plan_data.get("plan_estudios", {}).get("resumen_creditos") if isinstance(existing_plan_data.get("plan_estudios"), dict) else None)
                or existing_plan_data.get("resumen_creditos")
            )

            logger.info("   [%d/%d] Buscando en web oficial plan para [%s]: %s...", d_idx, len(missing_degrees), d_code, d_title[:60])

            found_curriculum = None
            direct_source_url = None
            fallback_curriculum = None
            fallback_source_url = None
            degree_started_at = time.monotonic()
            degree_deadline = degree_started_at + max(1.0, float(WEB_DEGREE_TIMEOUT_SECONDS))
            degree_deadline_reached = False

            def budget_available() -> bool:
                """Limita el coste de una titulación sin cancelar su evidencia parcial."""
                nonlocal degree_deadline_reached
                if time.monotonic() < degree_deadline:
                    return True
                degree_deadline_reached = True
                return False

            def consider_curriculum(candidate: dict | None, source_url: str) -> bool:
                """Conserva el mejor candidato y solo corta al hallar uno completo.

                Una ficha curricular parcial es una evidencia útil, pero no
                debe impedir que el mismo dominio aporte otra página o PDF
                con el plan completo. La comparación usa únicamente la
                estructura extraída y el total declarado; no contiene reglas
                de universidades ni de titulaciones concretas.
                """
                nonlocal found_curriculum, direct_source_url
                nonlocal fallback_curriculum, fallback_source_url
                if not isinstance(candidate, dict) or not candidate:
                    return False
                if not is_source_url_level_compatible(source_url, d_level):
                    logger.info(
                        "     -> Fuente curricular rechazada por nivel explícito incompatible en la URL: %s",
                        source_url,
                    )
                    return False
                probe = {
                    "nivel_academico": d_level,
                    "titulo": d_title,
                    "plan_estudios": candidate,
                }
                status = get_curriculum_completeness_status(probe)

                # Revalidación contra plantilla de distribución de créditos del BOE si está incompleto
                if (
                    not status.get("is_complete")
                    and isinstance(boe_resumen, dict)
                    and boe_resumen
                    and isinstance(candidate.get("elementos_curriculares"), list)
                    and len(candidate["elementos_curriculares"]) >= 6
                ):
                    if matches_boe_credit_distribution(candidate["elementos_curriculares"], boe_resumen):
                        logger.info("     -> [PLANTILLA BOE] Candidato web concordante con distribución de créditos oficial del BOE.")
                        if not candidate.get("resumen_creditos"):
                            candidate["resumen_creditos"] = dict(boe_resumen)
                        probe["plan_estudios"] = candidate
                        status = get_curriculum_completeness_status(probe)

                required = float(status.get("required_ects") or 0.0)
                listed = float(status.get("total_ects_listed") or 0.0)
                elements = int(status.get("total_elementos") or 0)
                rank = (
                    int(bool(status.get("is_complete"))),
                    listed / required if required > 0 else 0.0,
                    elements,
                    float(status.get("total_ects_declared") or 0.0),
                )
                if status.get("is_complete"):
                    found_curriculum = candidate
                    direct_source_url = source_url
                    return True
                previous_status = get_curriculum_completeness_status(
                    {
                        "nivel_academico": d_level,
                        "titulo": d_title,
                        "plan_estudios": fallback_curriculum,
                    }
                ) if isinstance(fallback_curriculum, dict) else None
                if previous_status:
                    previous_required = float(previous_status.get("required_ects") or 0.0)
                    previous_rank = (
                        0,
                        float(previous_status.get("total_ects_listed") or 0.0) / previous_required
                        if previous_required > 0 else 0.0,
                        int(previous_status.get("total_elementos") or 0),
                        float(previous_status.get("total_ects_declared") or 0.0),
                    )
                else:
                    previous_rank = (-1, -1.0, -1, -1.0)
                if rank > previous_rank:
                    fallback_curriculum = candidate
                    fallback_source_url = source_url
                return False

            # RUTA RÁPIDA: Si ya teníamos guardada una URL directa en búsquedas previas
            existing_direct_url = None
            invalid_existing_direct_url = False
            if os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        d_json = json.load(f)
                        existing_direct_url = d_json.get("web_fuente_directa_url")
                except Exception as exc:
                    logger.debug(f"Excepción controlada en crawling: {exc}")
                    pass

            if existing_direct_url and not is_explicitly_historical(existing_direct_url):
                try:
                    logger.debug("     -> Probando URL directa guardada previamente: %s", existing_direct_url)
                    if existing_direct_url.lower().endswith(".pdf"):
                        parsed = self._try_parse_candidate_pdf(downloader, existing_direct_url, d_code, d_title, u_name)
                        if parsed:
                            consider_curriculum(parsed, existing_direct_url)
                    else:
                        sub_html = downloader.fetch_text(existing_direct_url)
                        if sub_html:
                            sub_soup = BeautifulSoup(sub_html, "html.parser")
                            elementos_html = extract_html_subjects(sub_soup)
                            if len(elementos_html) < 10:
                                dyn_e = extract_dynamic_widget_subjects(sub_soup, existing_direct_url, web_url, downloader)
                                if len(dyn_e) > len(elementos_html):
                                    elementos_html = dyn_e
                            required_ects = get_required_degree_credits(d_level, d_title)
                            extracted_ects = compute_curriculum_total_ects(elementos_html)
                            minimum_ects = max(3.0, required_ects * 0.6)
                            # Una ficha puede superar el umbral de carga mínima
                            # y seguir siendo incompleta (p. ej., sólo incluye
                            # el núcleo fijo y omite el PDF con optativas). No
                            # debemos confundir "bastante contenido" con un
                            # plan publicable: si la identidad de la ficha es
                            # válida, se debe probar su documentación enlazada
                            # mientras quede presupuesto.
                            direct_page_matches = (
                                len(elementos_html) >= 3
                                and is_html_page_matching_degree(
                                    sub_soup,
                                    d_title,
                                    u_name,
                                    existing_direct_url,
                                )
                            )
                            direct_page_status = None
                            if direct_page_matches:
                                direct_page_status = get_curriculum_completeness_status(
                                    {
                                        "nivel_academico": d_level,
                                        "titulo": d_title,
                                        "plan_estudios": build_html_curriculum_payload(
                                            elementos_html,
                                            d_title,
                                            infer_declared_total_ects(sub_soup),
                                        ),
                                    }
                                )
                            direct_page_needs_linked_source = bool(
                                direct_page_matches
                                and direct_page_status
                                and not direct_page_status.get("is_complete")
                            )
                            # Las fichas de presentación suelen enlazar su plan real. Se
                            # inspeccionan primero esos enlaces curriculares, acotados y del
                            # mismo ámbito organizativo, antes de abrir índices globales.
                            if (
                                (extracted_ects < minimum_ects or direct_page_needs_linked_source)
                                and budget_available()
                            ):
                                for linked_url, linked_text in discover_linked_curriculum_pages(
                                    sub_soup, existing_direct_url, max_pages=8
                                ):
                                    if not budget_available() or found_curriculum:
                                        break
                                    if is_explicitly_historical(linked_url, linked_text):
                                        continue
                                    try:
                                        if linked_url.lower().endswith((".pdf", ".pdf.gz")):
                                            parsed = self._try_parse_candidate_pdf(
                                                downloader, linked_url, d_code, d_title, u_name
                                            )
                                            if parsed:
                                                consider_curriculum(parsed, linked_url)
                                            continue
                                        linked_html = downloader.fetch_text(linked_url)
                                        if not linked_html:
                                            continue
                                        linked_soup = BeautifulSoup(linked_html, "html.parser")
                                        linked_elements = extract_html_subjects(linked_soup, linked_url)
                                        if len(linked_elements) < 10:
                                            dynamic_elements = extract_dynamic_widget_subjects(
                                                linked_soup, linked_url, web_url, downloader
                                            )
                                            if len(dynamic_elements) > len(linked_elements):
                                                linked_elements = dynamic_elements
                                        if (
                                            len(linked_elements) >= 3
                                            and is_html_page_matching_degree(
                                                linked_soup,
                                                d_title,
                                                u_name,
                                                linked_url,
                                                allow_curriculum_url_identity=True,
                                            )
                                        ):
                                            consider_curriculum(
                                                build_html_curriculum_payload(
                                                    linked_elements,
                                                    d_title,
                                                    infer_declared_total_ects(linked_soup),
                                                ),
                                                linked_url,
                                            )
                                    except Exception as exc:
                                        logger.debug("Enlace curricular directo no disponible: %s", exc)
                            # Una ficha conocida es la evidencia de mayor precisión. Si su
                            # HTML estático no contiene una carga suficiente, se intenta una
                            # única renderización antes de gastar el presupuesto en sitemaps y
                            # hubs. Es una ruta general para portales SPA y no relaja ni la
                            # comprobación de identidad ni la de completitud posterior.
                            if extracted_ects < minimum_ects and budget_available():
                                try:
                                    from spa_crawler import SPALayoutCrawler

                                    rendered_direct = SPALayoutCrawler.get_shared_instance(
                                        timeout=max(1, int(downloader.timeout))
                                    ).render_spa_page(
                                        existing_direct_url
                                    )
                                    if getattr(rendered_direct, "is_download", False):
                                        pdf_bytes = getattr(rendered_direct, "content_bytes", b"")
                                        if pdf_bytes and b"%PDF-" in pdf_bytes[:1024]:
                                            parsed = parse_boe_pdf(pdf_bytes, d_title, d_level)
                                            if parsed:
                                                consider_curriculum(parsed, existing_direct_url)
                                    elif rendered_direct:
                                        rendered_soup = BeautifulSoup(rendered_direct, "html.parser")
                                        rendered_elements = extract_html_subjects(
                                            rendered_soup, existing_direct_url
                                        )
                                        rendered_ects = compute_curriculum_total_ects(rendered_elements)
                                        if (
                                            len(rendered_elements) > len(elementos_html)
                                            or rendered_ects > extracted_ects
                                        ):
                                            sub_soup = rendered_soup
                                            sub_html = rendered_direct
                                            elementos_html = rendered_elements
                                            extracted_ects = rendered_ects
                                except Exception as exc:
                                    logger.debug(
                                        "Renderizado de URL directa no disponible: %s", exc
                                    )

                            # Consolidación multi-curso: Si la ficha expone una carga parcial (< minimum_ects)
                            # y contiene enlaces a subpáginas particionadas por curso (1º a 4º...),
                            # se acumulan y fusionan las materias de cada año lectivo.
                            if extracted_ects < minimum_ects and budget_available():
                                try:
                                    course_subpages = discover_course_partitioned_subpages(sub_soup, existing_direct_url)
                                    if len(course_subpages) >= 2:
                                        accumulated_elements = list(elementos_html)
                                        for c_url, c_text, c_label in course_subpages:
                                            if not budget_available():
                                                break
                                            c_html = downloader.fetch_text(c_url)
                                            if not c_html:
                                                continue
                                            c_soup = BeautifulSoup(c_html, "html.parser")
                                            c_elements = extract_html_subjects(c_soup, c_url)
                                            for c_elem in c_elements:
                                                if isinstance(c_elem, dict) and not c_elem.get("curso"):
                                                    c_elem["curso"] = c_label
                                            accumulated_elements = merge_curriculum_elements(accumulated_elements, c_elements)
                                        accumulated_ects = compute_curriculum_total_ects(accumulated_elements)
                                        if accumulated_ects > extracted_ects:
                                            elementos_html = accumulated_elements
                                            extracted_ects = accumulated_ects
                                            logger.info("     -> [Multi-Curso Consolidado] Fusión de %d cursos: %.1f ECTS acumulados.", len(course_subpages), accumulated_ects)
                                except Exception as c_exc:
                                    logger.debug("No se pudieron consolidar subpáginas de curso: %s", c_exc)

                            page_matches_degree = (
                                len(elementos_html) >= 3
                                and is_html_page_matching_degree(
                                    sub_soup,
                                    d_title,
                                    u_name,
                                    existing_direct_url,
                                )
                            )
                            if (
                                len(elementos_html) >= 3
                                and extracted_ects >= minimum_ects
                                and page_matches_degree
                            ):
                                consider_curriculum(
                                    build_html_curriculum_payload(
                                        elementos_html, d_title, infer_declared_total_ects(sub_soup)
                                    ),
                                    existing_direct_url,
                                )
                                logger.info("     -> [ÉXITO FAST-PATH] Encontradas %d asignaturas en URL previa: %s", len(elementos_html), existing_direct_url)
                            elif len(elementos_html) >= 3 and not page_matches_degree:
                                invalid_existing_direct_url = True
                                logger.warning(
                                    "     -> URL directa previa rechazada por identidad de titulación: %s",
                                    existing_direct_url,
                                )
                            elif len(elementos_html) >= 3:
                                logger.info(
                                    "     -> URL directa previa incompleta (%s ECTS de %s requeridos); se continúa con fuentes alternativas.",
                                    extracted_ects,
                                    required_ects,
                                )
                except Exception as e:
                    logger.debug("     -> Falló lectura de URL directa previa: %s", e)
            elif existing_direct_url:
                logger.info(
                    "     -> Se pospone URL histórica previa para priorizar una fuente vigente: %s",
                    existing_direct_url,
                )

            univ_name_tokens = set(re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}\b', u_name.lower()))
            title_keywords = [
                w for w in re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}\b', d_title)
                if w.lower() not in TITLE_STOPWORDS and w.lower() not in univ_name_tokens
            ]

            # El buscador se usa como índice de descubrimiento, no como fuente
            # de confianza. Consultarlo antes del índice Hub-and-Spoke permite
            # encontrar PDFs oficiales que no están enlazados desde la raíz y
            # reserva el rastreo profundo para los casos en que la vía barata
            # no aporta una fuente compatible.
            search_attempted = False
            if not found_curriculum and budget_available():
                search_cache_key = (
                    str(u_name or "").strip().lower(),
                    str(d_title or "").strip().lower(),
                    str(d_level or "").strip().lower(),
                    str(web_url or "").strip().lower(),
                )
                with self.web_search_lock:
                    early_search_result = self.web_search_cache.get(search_cache_key)
                if early_search_result is None:
                    early_search_result = discover_search_candidates(
                        u_name,
                        d_title,
                        d_level,
                        web_url,
                        downloader.fetch_text,
                        query_limit=1,
                        result_limit=min(4, max(1, int(WEB_SEARCH_DISCOVERY_MAX_RESULTS))),
                    )
                    with self.web_search_lock:
                        self.web_search_cache[search_cache_key] = early_search_result
                search_attempted = True
                early_records = (
                    early_search_result.get("records", [])
                    if isinstance(early_search_result, dict)
                    else []
                )
                stats["web_search_queries"] = stats.get("web_search_queries", 0) + len(
                    early_search_result.get("queries", [])
                    if isinstance(early_search_result, dict)
                    else []
                )
                stats["web_search_candidates"] = stats.get("web_search_candidates", 0) + len(early_records)
                stats["web_search_errors"] = stats.get("web_search_errors", 0) + len(
                    early_search_result.get("errors", [])
                    if isinstance(early_search_result, dict)
                    else []
                )
                if self.ledger and early_records:
                    self.ledger.record_discovery_evidence(
                        [
                            {
                                "url": item.get("url"),
                                "source_kind": "web_search",
                                "anchor_text": item.get("title", ""),
                                "snippet": item.get("snippet", ""),
                                "source_url": web_url,
                            }
                            for item in early_records
                            if item.get("url")
                        ],
                        university_code=u_code,
                        phase="fase1_parte2",
                    )
                for item in early_records:
                    if found_curriculum or not budget_available():
                        break
                    candidate_url = str(item.get("url") or "").strip()
                    if not candidate_url or not is_same_or_subdomain(candidate_url, web_url):
                        continue
                    try:
                        if candidate_url.lower().endswith((".pdf", ".pdf.gz")):
                            parsed_candidate = self._try_parse_candidate_pdf(
                                downloader, candidate_url, d_code, d_title, u_name
                            )
                            if parsed_candidate:
                                consider_curriculum(parsed_candidate, candidate_url)
                            continue
                        candidate_html = downloader.fetch_text(candidate_url)
                        candidate_soup = BeautifulSoup(candidate_html or "", "html.parser")
                        candidate_elements = extract_html_subjects(candidate_soup, candidate_url)
                        if len(candidate_elements) >= 3 and is_html_page_matching_degree(
                            candidate_soup,
                            d_title,
                            u_name,
                            candidate_url,
                            allow_curriculum_url_identity=True,
                        ):
                            consider_curriculum(
                                build_html_curriculum_payload(
                                    candidate_elements,
                                    d_title,
                                    infer_declared_total_ects(candidate_soup),
                                ),
                                candidate_url,
                            )
                        if not found_curriculum and budget_available():
                            for document_url, document_text in discover_linked_curriculum_documents(
                                candidate_soup, candidate_url, max_documents=4
                            ):
                                if not budget_available() or is_explicitly_historical(document_url, document_text):
                                    continue
                                parsed_document = self._try_parse_candidate_pdf(
                                    downloader, document_url, d_code, d_title, u_name
                                )
                                if parsed_document:
                                    consider_curriculum(parsed_document, document_url)
                                    if found_curriculum:
                                        break
                    except Exception as early_search_error:
                        logger.debug(
                            "Excepción controlada al evaluar descubrimiento temprano %s: %s",
                            candidate_url,
                            early_search_error,
                        )

            if not found_curriculum and budget_available():
                ensure_discovery_index(include_hubs=False)

            # ESTRATEGIA 1: Escaneo priorizado de URLs obtenidas del Sitemap XML
            if not found_curriculum and sitemap_urls and budget_available():
                sitemap_scored = []
                for url in sitemap_urls:
                    url_low = url.lower()
                    normalized_url = normalize_text(url_low)
                    kw_matches = sum(
                        1
                        for kw in title_keywords
                        if len(kw) >= 3 and normalize_text(kw) in normalized_url
                    )
                    if kw_matches >= min(2, len(title_keywords)) or (len(title_keywords) == 1 and kw_matches >= 1):
                        sitemap_scored.append((kw_matches, url))
                sitemap_scored.sort(key=lambda x: x[0], reverse=True)
                sitemap_matches = [u for _, u in sitemap_scored]

                for sm_candidate_url in sitemap_matches[:5]:
                    if found_curriculum or not budget_available():
                        break
                    try:
                        time.sleep(WEB_SEARCH_RETRY_DELAY)
                        if sm_candidate_url.lower().endswith(".pdf"):
                            parsed = self._try_parse_candidate_pdf(downloader, sm_candidate_url, d_code, d_title, u_name)
                            if parsed:
                                if not consider_curriculum(parsed, sm_candidate_url):
                                    continue
                                logger.info("     -> Encontrado plan de estudios desde Sitemap XML: %s", sm_candidate_url)
                                break
                        else:
                            sub_html = downloader.fetch_text(sm_candidate_url)
                            sub_soup = BeautifulSoup(sub_html, "html.parser")
                            elementos_html = extract_html_subjects(sub_soup)
                            if len(elementos_html) < 10:
                                dyn_e = extract_dynamic_widget_subjects(sub_soup, sm_candidate_url, web_url, downloader)
                                if len(dyn_e) > len(elementos_html):
                                    elementos_html = dyn_e
                            sitemap_matches_degree = is_html_page_matching_degree(
                                sub_soup,
                                d_title,
                                u_name,
                                sm_candidate_url,
                                allow_curriculum_url_identity=True,
                            )
                            if sitemap_matches_degree and len(elementos_html) < 3 and budget_available():
                                try:
                                    from spa_crawler import SPALayoutCrawler

                                    rendered_sitemap = SPALayoutCrawler.get_shared_instance(
                                        timeout=max(1, int(downloader.timeout))
                                    ).render_spa_page(sm_candidate_url)
                                    rendered_sitemap_html = getattr(
                                        rendered_sitemap, "html", rendered_sitemap
                                    )
                                    if rendered_sitemap_html and not getattr(
                                        rendered_sitemap, "is_download", False
                                    ):
                                        rendered_sitemap_soup = BeautifulSoup(
                                            rendered_sitemap_html, "html.parser"
                                        )
                                        rendered_sitemap_elements = extract_html_subjects(
                                            rendered_sitemap_soup, sm_candidate_url
                                        )
                                        if len(rendered_sitemap_elements) > len(elementos_html):
                                            elementos_html = rendered_sitemap_elements
                                        sub_soup = rendered_sitemap_soup
                                except Exception as exc:
                                    logger.debug(
                                        "Renderizado de candidato de Sitemap no disponible: %s",
                                        exc,
                                    )
                            if sitemap_matches_degree and not found_curriculum and budget_available():
                                for document_url, document_text in discover_linked_curriculum_documents(
                                    sub_soup, sm_candidate_url, max_documents=8
                                ):
                                    if not budget_available() or is_explicitly_historical(
                                        document_url, document_text
                                    ):
                                        continue
                                    parsed_document = self._try_parse_candidate_pdf(
                                        downloader, document_url, d_code, d_title, u_name
                                    )
                                    if parsed_document:
                                        consider_curriculum(parsed_document, document_url)
                                        if found_curriculum:
                                            break
                            if (
                                not found_curriculum
                                and len(elementos_html) >= 3
                                and sitemap_matches_degree
                            ):
                                if not consider_curriculum(
                                    build_html_curriculum_payload(
                                        elementos_html, d_title, infer_declared_total_ects(sub_soup)
                                    ),
                                    sm_candidate_url,
                                ):
                                    continue
                                logger.info("     -> Encontradas asignaturas HTML válidas desde Sitemap XML: %s", sm_candidate_url)
                                break
                    except Exception as exc:
                        logger.debug(f"Excepción controlada en crawling: {exc}")
                        pass

            # ESTRATEGIA 1.5: Búsqueda instantánea en el índice Hub-and-Spoke de Catálogos (Profundidad <= 6)
            if not found_curriculum and budget_available():
                ensure_discovery_index(include_hubs=True)
            if not found_curriculum and catalog_map and budget_available():
                catalog_candidates = []
                for kw in title_keywords:
                    kw_low = kw.lower()
                    kw_norm = unicodedata.normalize('NFKD', kw_low).encode('ASCII', 'ignore').decode('utf-8')
                    kw_stem = kw_norm[:4] if len(kw_norm) >= 4 else kw_norm
                    for map_tok, links in catalog_map.items():
                        if kw_norm in map_tok or kw_low in map_tok or (len(kw_stem) >= 4 and kw_stem in map_tok):
                            for c_url, c_text in links:
                                catalog_candidates.append((c_url, c_text))

                if catalog_candidates:
                    # Deduplicar y ordenar por score semántico
                    seen_c = set()
                    scored_cat = []
                    for c_url, c_text in catalog_candidates:
                        if c_url not in seen_c:
                            seen_c.add(c_url)
                            sc = score_academic_candidate_url(c_url, c_text, d_level, title_keywords)
                            scored_cat.append((sc, c_url, c_text))

                    # Si el catálogo ofrece enlaces con dos términos del
                    # título, no mezclar páginas de otra titulación que solo
                    # comparten un término genérico (p. ej. «ingeniería»).
                    relevant_cat = [
                        item for item in scored_cat
                        if _is_relevant_title_candidate(item[1], item[2], title_keywords)
                    ]
                    if relevant_cat:
                        scored_cat = relevant_cat
                    else:
                        # No expandir enlaces genéricos: suelen ser noticias,
                        # movilidad o investigación, no la ficha curricular.
                        scored_cat = []
                    
                    scored_cat.sort(key=lambda x: x[0], reverse=True)
                    # No forzar ocho fichas cuando la configuración de la
                    # campaña pide una cohorte pequeña: cada candidata puede
                    # abrir subpáginas y consumir el presupuesto de la
                    # titulación antes de llegar a las rutas posteriores.
                    candidate_limit = max(1, min(8, int(WEB_CANDIDATES_PER_DEGREE or 1)))
                    scored_cat.sort(key=lambda x: x[0], reverse=True)
                    for sc, cat_url, cat_text in scored_cat[:candidate_limit]:
                        if found_curriculum or sc < 40 or not budget_available():
                            break
                        try:
                            time.sleep(WEB_SEARCH_RETRY_DELAY)
                            if cat_url.lower().endswith(".pdf"):
                                parsed = self._try_parse_candidate_pdf(downloader, cat_url, d_code, d_title, u_name)
                                if parsed:
                                    if not consider_curriculum(parsed, cat_url):
                                        continue
                                    logger.info("     -> [Hub-and-Spoke] Encontrado plan PDF: %s", cat_url)
                                    break
                            else:
                                c_html = downloader.fetch_text(cat_url)
                                c_soup = BeautifulSoup(c_html, "html.parser")
                                c_elementos = extract_html_subjects(c_soup, cat_url)
                                req_c = get_required_degree_credits(d_level, d_title)
                                cur_c = compute_curriculum_total_ects(c_elementos)
                                
                                # Paso 0.4: Resolución genérica de widgets y microservicios HTML5 desacoplados
                                if len(c_elementos) < 10 or cur_c < (req_c * 0.6):
                                    dyn_c = extract_dynamic_widget_subjects(c_soup, cat_url, web_url, downloader)
                                    if len(dyn_c) > len(c_elementos):
                                        c_elementos = dyn_c
                                        cur_c = compute_curriculum_total_ects(c_elementos)

                                # Paso 0.5: Si HTML estático de la ficha tiene < 10 asignaturas o < 60% créditos, explorar subpáginas curriculares (-plan, /estructura, /asignaturas, etc.)
                                if len(c_elementos) < 10 or cur_c < (req_c * 0.6):
                                    cat_matches_degree = is_html_page_matching_degree(
                                        c_soup,
                                        d_title,
                                        u_name,
                                        cat_url,
                                        allow_curriculum_url_identity=True,
                                    )
                                    if cat_matches_degree and len(c_elementos) < 3 and budget_available():
                                        try:
                                            from spa_crawler import SPALayoutCrawler

                                            rendered_catalog_page = SPALayoutCrawler.get_shared_instance(
                                                timeout=max(1, int(downloader.timeout))
                                            ).render_spa_page(cat_url)
                                            rendered_catalog_html = getattr(
                                                rendered_catalog_page,
                                                "html",
                                                rendered_catalog_page,
                                            )
                                            if rendered_catalog_html and not getattr(
                                                rendered_catalog_page, "is_download", False
                                            ):
                                                rendered_catalog_soup = BeautifulSoup(
                                                    rendered_catalog_html, "html.parser"
                                                )
                                                rendered_catalog_elements = extract_html_subjects(
                                                    rendered_catalog_soup, cat_url
                                                )
                                                if len(rendered_catalog_elements) > len(c_elementos):
                                                    c_elementos = rendered_catalog_elements
                                                c_soup = rendered_catalog_soup
                                        except Exception as exc:
                                            logger.debug(
                                                "Renderizado temprano de candidata Hub no disponible: %s",
                                                exc,
                                            )
                                    if cat_matches_degree and not found_curriculum and budget_available():
                                        for linked_doc_url, linked_doc_text in discover_linked_curriculum_documents(
                                            c_soup, cat_url, max_documents=8
                                        ):
                                            if not budget_available() or is_explicitly_historical(
                                                linked_doc_url, linked_doc_text
                                            ):
                                                continue
                                            parsed_linked_doc = self._try_parse_candidate_pdf(
                                                downloader,
                                                linked_doc_url,
                                                d_code,
                                                d_title,
                                                u_name,
                                            )
                                            if parsed_linked_doc:
                                                consider_curriculum(
                                                    parsed_linked_doc,
                                                    linked_doc_url,
                                                )
                                                if found_curriculum:
                                                    break
                                    if found_curriculum:
                                        break

                                if found_curriculum:
                                    break

                                if len(c_elementos) < 10 or cur_c < (req_c * 0.6):
                                    discovered_cat_subpages = []
                                    seen_cat_subs = {cat_url}
                                    parsed_cat_target = urllib.parse.urlparse(cat_url)
                                    cat_path_prefix = parsed_cat_target.path.rstrip("/")

                                    # Una ficha institucional puede enlazar el
                                    # portal docente especializado en otro
                                    # subdominio de la misma organización.
                                    # Incorporar su origen permite aplicar allí
                                    # las mismas rutas y validaciones genéricas.
                                    for related_origin in discover_related_academic_origins(
                                        c_soup, cat_url
                                    ):
                                        if (
                                            related_origin not in crawl_origins
                                            and is_same_or_subdomain(related_origin, web_url)
                                        ):
                                            allowed_related, _ = self.check_robots_allowed(
                                                related_origin
                                            )
                                            if allowed_related:
                                                # Los orígenes descubiertos en
                                                # una ficha ya identificada son
                                                # más específicos que la
                                                # portada. Priorizarlos evita
                                                # consumir el plazo en rutas
                                                # genéricas antes de probar el
                                                # portal docente enlazado.
                                                crawl_origins.insert(0, related_origin)
                                        if (
                                            related_origin not in seen_cat_subs
                                            and is_same_or_subdomain(related_origin, web_url)
                                        ):
                                            seen_cat_subs.add(related_origin)
                                            discovered_cat_subpages.append((100, related_origin))

                                    for a_tag in c_soup.find_all("a", href=True):
                                        h_sub = a_tag["href"].strip()
                                        if not h_sub or h_sub.startswith(("javascript:", "mailto:", "tel:", "#")):
                                            continue
                                        t_sub = a_tag.get_text(" ", strip=True).lower()
                                        h_sub_low = h_sub.lower()
                                        if (
                                            any(kw in t_sub for kw in ACADEMIC_SUBPAGE_KEYWORDS) 
                                            or any(kw in h_sub_low for kw in ACADEMIC_SUBPAGE_KEYWORDS)
                                            or any(k in h_sub_low or k in t_sub for k in ["-plan", "estructura", "malla", "asignatura", "assignatura", "guia", "docencia", "web del curso", "plan de estudios"])
                                        ):
                                            full_sub_url = urllib.parse.urljoin(cat_url, h_sub)
                                            if full_sub_url not in seen_cat_subs and is_same_or_subdomain(full_sub_url, web_url):
                                                seen_cat_subs.add(full_sub_url)
                                                parsed_sub = urllib.parse.urlparse(full_sub_url)
                                                is_child = 1 if (cat_path_prefix and parsed_sub.path.startswith(cat_path_prefix)) else 0
                                                has_pla = 1 if any(k in full_sub_url.lower() or k in t_sub for k in ["pla-estudis", "plan-estudios", "malla", "asignaturas", "assignatures", "docencia", "-plan", "estructura"]) else 0
                                                priority = (is_child * 10) + (has_pla * 5)
                                                discovered_cat_subpages.append((priority, full_sub_url))

                                    discovered_cat_subpages.sort(key=lambda x: x[0], reverse=True)
                                    for _, sub_p_url in discovered_cat_subpages[: max(2, candidate_limit * 2)]:
                                        if not budget_available():
                                            break
                                        try:
                                            sub_p_html = downloader.fetch_text(sub_p_url)
                                            if sub_p_html:
                                                sub_p_soup = BeautifulSoup(sub_p_html, "html.parser")
                                                sub_p_elems = extract_html_subjects(sub_p_soup, sub_p_url)
                                                if len(sub_p_elems) < 10:
                                                    dyn_sub = extract_dynamic_widget_subjects(sub_p_soup, sub_p_url, web_url, downloader)
                                                    if len(dyn_sub) > len(sub_p_elems):
                                                        sub_p_elems = dyn_sub
                                                if len(sub_p_elems) > len(c_elementos):
                                                    c_elementos = sub_p_elems
                                                    c_soup = sub_p_soup
                                                    cat_url = sub_p_url
                                                
                                                # Si la subpágina enlaza a una estructura más profunda (ej. web del curso -> estructura del curso)
                                                if len(c_elementos) < 10:
                                                    for a2 in sub_p_soup.find_all("a", href=True):
                                                        h2 = a2["href"].strip()
                                                        t2 = a2.get_text(" ", strip=True).lower()
                                                        if any(k in h2.lower() or k in t2 for k in [
                                                            "estructura", "plan-de-estudios", "planestudios",
                                                            "plan-d-estudis", "asignaturas", "assignatures",
                                                            "subjects", "curriculum", "malla",
                                                        ]):
                                                            f2 = urllib.parse.urljoin(sub_p_url, h2)
                                                            if (
                                                                f2 not in seen_cat_subs
                                                                and is_same_or_subdomain(f2, web_url)
                                                                and budget_available()
                                                            ):
                                                                seen_cat_subs.add(f2)
                                                                try:
                                                                    h2_html = downloader.fetch_text(f2)
                                                                    if h2_html:
                                                                        s2_soup = BeautifulSoup(h2_html, "html.parser")
                                                                        s2_elems = extract_html_subjects(s2_soup, f2)
                                                                        if len(s2_elems) > len(c_elementos):
                                                                            c_elementos = s2_elems
                                                                            c_soup = s2_soup
                                                                            cat_url = f2
                                                                except Exception:
                                                                    pass
                                        except Exception as exc:
                                            logger.debug("Excepción controlada en crawling subpágina: %s", exc)
                                            pass

                                # Si tras explorar subpáginas sigue teniendo < 3 asignaturas (contenedor SPA vacío JS), renderizar con Playwright
                                if len(c_elementos) < 3:
                                    try:
                                        from spa_crawler import SPALayoutCrawler
                                        spa_c = SPALayoutCrawler.get_shared_instance(
                                            timeout=max(1, int(downloader.timeout))
                                        )
                                        rend = spa_c.render_spa_page(cat_url)
                                        if rend:
                                            if getattr(rend, "is_download", False):
                                                pdf_bytes = getattr(rend, "content_bytes", b"")
                                                if pdf_bytes and (b"%PDF-" in pdf_bytes[:1024] or getattr(rend, "filename", "").lower().endswith(".pdf")):
                                                    pdf_curriculum = parse_boe_pdf(pdf_bytes, d_title, d_level)
                                                    if pdf_curriculum and len(pdf_curriculum.get("elementos_curriculares", [])) >= 3:
                                                        if not consider_curriculum(pdf_curriculum, cat_url):
                                                            continue
                                                        logger.info("     -> [Playwright Download Rescate] Encontrado PDF oficial con %d asignaturas: %s", len(pdf_curriculum['elementos_curriculares']), cat_url)
                                                        break
                                            else:
                                                rend_soup = BeautifulSoup(rend, "html.parser")
                                                rend_elem = extract_html_subjects(rend_soup)
                                                if len(rend_elem) > len(c_elementos):
                                                    c_elementos = rend_elem
                                    except Exception as exc:
                                        logger.debug("Excepción controlada en crawling: %s", exc)
                                        pass
                                
                                if (
                                    len(c_elementos) >= 3
                                    and not found_curriculum
                                    and is_html_page_matching_degree(
                                        c_soup,
                                        d_title,
                                        u_name,
                                        cat_url,
                                        allow_curriculum_url_identity=True,
                                    )
                                ):
                                    if not consider_curriculum(
                                        build_html_curriculum_payload(
                                            c_elementos, d_title, infer_declared_total_ects(c_soup)
                                        ),
                                        cat_url,
                                    ):
                                        continue
                                    logger.info("     -> [Hub-and-Spoke] Encontradas %d asignaturas HTML: %s", len(c_elementos), cat_url)
                                    break
                        except Exception as exc:
                            logger.debug("Excepción controlada en crawling: %s", exc)
                            pass

            # ESTRATEGIA 1.8: Rutas académicas convencionales. Algunos
            # portales no enlazan el plan desde la portada, pero mantienen
            # endpoints predecibles (curriculum, estructura, asignaturas...).
            # Las rutas se generan sólo sobre el dominio ya autorizado y se
            # someten a la misma identidad y calidad que cualquier candidato.
            # Un buscador sin resultados no debe bloquear las rutas
            # convencionales: son fuentes de descubrimiento independientes y
            # siguen estando acotadas por origen, número de candidatas y
            # presupuesto temporal.
            if not found_curriculum and budget_available() and not early_records:
              generic_route_urls = []
              # Los prefijos académicos derivados de la portada son más
              # informativos que las rutas raíz genéricas; deben entrar en la
              # ventana acotada antes de que ésta se llene de 404 previsibles.
              all_route_origins = list(
                  dict.fromkeys(crawl_origins + list(discovered_academic_origins))
              )
              route_origins = sorted(
                  all_route_origins,
                  key=lambda origin: len(
                      [part for part in urllib.parse.urlsplit(origin).path.split("/") if part]
                  ),
              )
              for route_origin in route_origins:
                  generic_route_urls.extend(
                      generic_curriculum_path_candidates(route_origin, d_level, d_title)[:16]
                  )
              for route_url in list(dict.fromkeys(generic_route_urls))[:48]:
                    if not budget_available():
                        break
                    try:
                        time.sleep(WEB_SEARCH_RETRY_DELAY)
                        route_html = downloader.fetch_text(route_url)
                        if not route_html:
                            continue
                        route_soup = BeautifulSoup(route_html, "html.parser")
                        route_elements = extract_html_subjects(route_soup, route_url)
                        if len(route_elements) < 10:
                            dynamic_elements = extract_dynamic_widget_subjects(
                                route_soup, route_url, web_url, downloader
                            )
                            if len(dynamic_elements) > len(route_elements):
                                route_elements = dynamic_elements
                        # Una ficha vigente puede publicar el detalle en un
                        # PDF enlazado, sin duplicarlo en el HTML. Seguir sólo
                        # documentos curriculares del mismo origen organizativo
                        # evita abrir informes administrativos o dominios ajenos.
                        route_matches_degree = is_html_page_matching_degree(
                            route_soup,
                            d_title,
                            u_name,
                            route_url,
                            allow_curriculum_url_identity=True,
                        )
                        if route_matches_degree and len(route_elements) < 3 and budget_available():
                            try:
                                from spa_crawler import SPALayoutCrawler

                                rendered_route = SPALayoutCrawler.get_shared_instance(
                                    timeout=max(1, int(downloader.timeout))
                                ).render_spa_page(route_url)
                                rendered_route_html = getattr(
                                    rendered_route, "html", rendered_route
                                )
                                if rendered_route_html and not getattr(
                                    rendered_route, "is_download", False
                                ):
                                    rendered_route_soup = BeautifulSoup(
                                        rendered_route_html, "html.parser"
                                    )
                                    rendered_route_elements = extract_html_subjects(
                                        rendered_route_soup, route_url
                                    )
                                    if len(rendered_route_elements) > len(route_elements):
                                        route_elements = rendered_route_elements
                                    route_soup = rendered_route_soup
                            except Exception as exc:
                                logger.debug(
                                    "Renderizado de ruta académica no disponible: %s",
                                    exc,
                                )
                        if not found_curriculum and len(route_elements) < 3 and route_matches_degree:
                            linked_documents = discover_linked_curriculum_documents(
                                route_soup, route_url, max_documents=12
                            )
                            for document_url, document_text in linked_documents:
                                if is_explicitly_historical(document_url, document_text):
                                    continue
                                parsed_document = self._try_parse_candidate_pdf(
                                    downloader, document_url, d_code, d_title, u_name
                                )
                                if parsed_document and len(
                                    parsed_document.get("elementos_curriculares", [])
                                ) >= 3:
                                    if not consider_curriculum(parsed_document, document_url):
                                        continue
                                    logger.info(
                                        "     -> [DOCUMENTO CURRICULAR ENLAZADO] Encontrados %d elementos: %s",
                                        len(parsed_document.get("elementos_curriculares", [])),
                                        document_url,
                                    )
                                    break
                        if (
                            len(route_elements) >= 3
                            and route_matches_degree
                        ):
                            if not consider_curriculum(
                                build_html_curriculum_payload(
                                    route_elements, d_title, infer_declared_total_ects(route_soup)
                                ),
                                route_url,
                            ):
                                continue
                            logger.info(
                                "     -> [RUTA ACADÉMICA GENÉRICA] Encontrados %d elementos: %s",
                                len(route_elements), route_url,
                            )
                            break
                    except Exception as route_err:
                        logger.debug("Excepción en ruta académica genérica %s: %s", route_url, route_err)

            # ESTRATEGIA 2: Escaneo de portales académicos con sinónimos amplios
            if not found_curriculum and budget_available():
                try:
                    if lazy_home_html is None:
                        lazy_home_html = downloader.fetch_text(web_url)
                        lazy_soup = BeautifulSoup(lazy_home_html, "html.parser")
                        lazy_candidate_urls = []

                        for a in lazy_soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if not is_valid_web_url(href):
                                continue
                            
                            text = a.get_text(strip=True)
                            text_lower = text.lower()
                            if any(kw in text_lower for kw in ACADEMIC_KEYWORDS) or any(kw in href.lower() for kw in ACADEMIC_KEYWORDS):
                                full_url = urllib.parse.urljoin(web_url, href)
                                if is_same_or_subdomain(full_url, web_url):
                                    lazy_candidate_urls.append((full_url, text))
                    
                    home_html = lazy_home_html
                    soup = lazy_soup

                    # Ordenar URLs candidatas por puntuación semántica descendente (de mayor a menor prioridad según nivel académico)
                    d_level = deg.get("nivel_academico", "")
                    candidate_text_by_url = {}
                    scored_candidates = []
                    for u, t in lazy_candidate_urls:
                        candidate_text_by_url.setdefault(u, t)
                        scored_candidates.append((score_academic_candidate_url(u, t, d_level, title_keywords), u))
                    relevant_lazy = [
                        item for item in scored_candidates
                        if _is_relevant_title_candidate(item[1], candidate_text_by_url.get(item[1], ""), title_keywords)
                    ]
                    if relevant_lazy:
                        scored_candidates = relevant_lazy
                    else:
                        # Sin coincidencia académica relevante, no abrir una
                        # página arbitraria de la portada institucional.
                        scored_candidates = []
                    best_url_scores = {}
                    for sc, u in scored_candidates:
                        if u not in best_url_scores or sc > best_url_scores[u]:
                            best_url_scores[u] = sc

                    sorted_candidates = sorted(best_url_scores.items(), key=lambda x: x[1], reverse=True)
                    # Evaluar varias fichas relevantes por titulación. El filtro
                    # semántico evita falsos positivos; el límite configurable
                    # recupera recall cuando la primera ficha es solo un índice.
                    candidate_limit = max(1, int(WEB_CANDIDATES_PER_DEGREE or 1))
                    scanned_urls = [u for u, score in sorted_candidates[:candidate_limit]]
                    visited_targets = set()
                    
                    for candidate_page_url in scanned_urls:
                        if found_curriculum or not budget_available():
                            break

                        try:
                            if candidate_page_url in lazy_scanned_pages_cache:
                                sub_html, sub_soup = lazy_scanned_pages_cache[candidate_page_url]
                            else:
                                time.sleep(WEB_SEARCH_RETRY_DELAY) # Buenas prácticas de rate-limiting
                                try:
                                    sub_html = downloader.fetch_text(candidate_page_url)
                                    sub_soup = BeautifulSoup(sub_html, "html.parser")
                                    if len(lazy_scanned_pages_cache) < LAZY_SCANNED_PAGES_CACHE_LIMIT:
                                        lazy_scanned_pages_cache[candidate_page_url] = (sub_html, sub_soup)
                                except Exception as fetch_err:
                                    lazy_scanned_pages_cache[candidate_page_url] = (None, None)
                                    if isinstance(fetch_err, SkipUniversityException):
                                        raise
                                    continue

                            if not sub_html or not sub_soup:
                                continue

                            for a in sub_soup.find_all("a", href=True):
                                if not budget_available():
                                    break
                                href = a["href"].strip()
                                if not is_valid_web_url(href):
                                    continue

                                text = a.get_text(strip=True)
                                text_lower = text.lower()

                                # Los CMS suelen traducir sólo la etiqueta o
                                # el slug de la ficha (p. ej. «biologia» frente
                                # a «biología»). La comparación normalizada
                                # conserva el filtro por título sin depender
                                # de un idioma concreto.
                                matches_title = any(
                                    normalize_text(kw) in normalize_text(text_lower)
                                    or normalize_text(kw) in normalize_text(href.lower())
                                    for kw in title_keywords
                                )
                                if matches_title:
                                    target_link = urllib.parse.urljoin(candidate_page_url, href)
                                    if target_link in visited_targets:
                                        continue
                                    visited_targets.add(target_link)
                                    
                                    if not is_same_or_subdomain(target_link, web_url):
                                        continue
                                    
                                    if target_link.lower().endswith(".pdf"):
                                        parsed = self._try_parse_candidate_pdf(downloader, target_link, d_code, d_title, u_name)
                                        if parsed:
                                            if not consider_curriculum(parsed, target_link):
                                                continue
                                            break
                                        # Fallback: si el PDF no contiene plan, intentar extraer HTML de la misma URL sin .pdf
                                        html_fallback_url = target_link[:-4] if target_link.lower().endswith(".pdf") else target_link
                                        try:
                                            html_content = downloader.fetch_text(html_fallback_url)
                                            html_soup = BeautifulSoup(html_content, "html.parser")
                                            elementos_html = extract_html_subjects(html_soup)
                                            if len(elementos_html) >= 3 and is_html_page_matching_degree(
                                                html_soup,
                                                d_title,
                                                u_name,
                                                html_fallback_url,
                                                allow_curriculum_url_identity=True,
                                            ):
                                                if not consider_curriculum(
                                                    build_html_curriculum_payload(
                                                        elementos_html,
                                                        d_title,
                                                        infer_declared_total_ects(html_soup),
                                                    ),
                                                    html_fallback_url,
                                                ):
                                                    continue
                                                break
                                        except Exception as exc:
                                            logger.debug(f"Excepción controlada en crawling: {exc}")
                                            pass
                                    else:
                                        # Descargar e inspeccionar el HTML específico de la subpágina de la titulación target_link
                                        try:
                                            target_html = downloader.fetch_text(target_link)
                                            target_soup = BeautifulSoup(target_html, "html.parser")
                                            elementos_html = extract_html_subjects(target_soup, target_link)
                                            if len(elementos_html) < 10:
                                                dyn_e = extract_dynamic_widget_subjects(target_soup, target_link, web_url, downloader)
                                                if len(dyn_e) > len(elementos_html):
                                                    elementos_html = dyn_e
                                            # No profundizar en noticias, movilidad o investigación
                                            # que solo coinciden por palabras sueltas del título.
                                            # Las fichas legítimas pueden tener inicialmente cero
                                            # asignaturas, pero deben identificarse semánticamente
                                            # como la titulación antes de explorar sus enlaces.
                                            if len(elementos_html) < 3 and not is_html_page_matching_degree(
                                                target_soup,
                                                d_title,
                                                u_name,
                                                target_link,
                                                allow_curriculum_url_identity=True,
                                            ):
                                                continue
                                            # Paso 0.5: Si HTML estático de la ficha tiene < 3 asignaturas,
                                            # explorar dinámicamente cualquier subpágina enlazada en el DOM de la ficha (<a> tags)
                                            # priorizando subrutas directas del grado y enlaces a portales institucionales de gestión (2-Hop).
                                            req_ects = get_required_degree_credits(d_level, d_title)
                                            if len(elementos_html) < 3:
                                                # Algunos CMS sólo insertan el PDF vigente tras ejecutar
                                                # JavaScript. Renderizar aquí, justo después de validar la
                                                # identidad de la ficha, evita gastar el presupuesto en
                                                # subpáginas auxiliares antes de inspeccionar esa evidencia.
                                                try:
                                                    from spa_crawler import SPALayoutCrawler

                                                    rendered_target = SPALayoutCrawler.get_shared_instance(
                                                        timeout=max(1, int(downloader.timeout))
                                                    ).render_spa_page(target_link)
                                                    rendered_target_html = getattr(
                                                        rendered_target, "html", rendered_target
                                                    )
                                                    if rendered_target_html and not getattr(
                                                        rendered_target, "is_download", False
                                                    ):
                                                        rendered_target_soup = BeautifulSoup(
                                                            rendered_target_html, "html.parser"
                                                        )
                                                        rendered_target_elements = extract_html_subjects(
                                                            rendered_target_soup, target_link
                                                        )
                                                        if len(rendered_target_elements) > len(elementos_html):
                                                            elementos_html = rendered_target_elements
                                                        target_soup = rendered_target_soup
                                                        target_html = rendered_target_html
                                                except Exception as exc:
                                                    logger.debug(
                                                        "Renderizado temprano de ficha no disponible: %s",
                                                        exc,
                                                    )

                                                # Inspeccionar primero los documentos que la ficha
                                                # renderizada declara como curriculares. El filtro de
                                                # mismo origen y la compuerta de identidad/calidad se
                                                # mantienen para evitar aceptar PDFs administrativos.
                                                for linked_doc_url, linked_doc_text in discover_linked_curriculum_documents(
                                                    target_soup, target_link, max_documents=8
                                                ):
                                                    if not budget_available() or is_explicitly_historical(
                                                        linked_doc_url, linked_doc_text
                                                    ):
                                                        continue
                                                    parsed_linked_doc = self._try_parse_candidate_pdf(
                                                        downloader,
                                                        linked_doc_url,
                                                        d_code,
                                                        d_title,
                                                        u_name,
                                                    )
                                                    if parsed_linked_doc:
                                                        consider_curriculum(
                                                            parsed_linked_doc,
                                                            linked_doc_url,
                                                        )
                                                        if found_curriculum:
                                                            break
                                                if found_curriculum:
                                                    break

                                            if len(elementos_html) < 3:
                                                discovered_subpages = []
                                                seen_sub_urls = {target_link}
                                                parsed_target = urllib.parse.urlparse(target_link)
                                                target_path_prefix = parsed_target.path.rstrip("/")

                                                # Priorizar variantes lingüísticas declaradas por el
                                                # propio portal. Suelen contener una ficha equivalente
                                                # con documentación distinta; no se infiere ningún
                                                # idioma ni se fija una ruta institucional concreta.
                                                language_variants = []
                                                for variant_node in target_soup.find_all(
                                                    ["link", "a"], href=True
                                                ):
                                                    rel_values = " ".join(
                                                        variant_node.get("rel") or []
                                                    ).lower()
                                                    hreflang = str(
                                                        variant_node.get("hreflang") or ""
                                                    ).strip()
                                                    if "alternate" not in rel_values and not hreflang:
                                                        continue
                                                    variant_href = str(
                                                        variant_node.get("href") or ""
                                                    ).strip()
                                                    if not variant_href:
                                                        continue
                                                    variant_url = urllib.parse.urljoin(
                                                        target_link, variant_href
                                                    )
                                                    if (
                                                        variant_url not in seen_sub_urls
                                                        and is_valid_web_url(variant_url)
                                                        and is_same_or_subdomain(variant_url, web_url)
                                                    ):
                                                        seen_sub_urls.add(variant_url)
                                                        language_variants.append(variant_url)
                                                for variant_url in reversed(language_variants):
                                                    discovered_subpages.append((1000, variant_url))

                                                for a_tag in target_soup.find_all("a", href=True):
                                                    h_sub = a_tag["href"].strip()
                                                    if not h_sub or h_sub.startswith(("javascript:", "mailto:", "tel:", "#")):
                                                        continue
                                                    t_sub = a_tag.get_text(" ", strip=True).lower()
                                                    h_sub_low = h_sub.lower()
                                                    if any(kw in t_sub for kw in ACADEMIC_SUBPAGE_KEYWORDS) or any(kw in h_sub_low for kw in ACADEMIC_SUBPAGE_KEYWORDS):
                                                        full_sub_url = urllib.parse.urljoin(target_link, h_sub)
                                                        if full_sub_url not in seen_sub_urls and is_same_or_subdomain(full_sub_url, web_url):
                                                            seen_sub_urls.add(full_sub_url)
                                                            parsed_sub = urllib.parse.urlparse(full_sub_url)
                                                            is_child = 1 if (target_path_prefix and parsed_sub.path.startswith(target_path_prefix)) else 0
                                                            has_pla = 1 if any(k in full_sub_url.lower() or k in t_sub for k in ["pla-estudis", "plan-estudios", "malla", "asignaturas", "assignatures", "docencia"]) else 0
                                                            priority = (is_child * 10) + (has_pla * 5)
                                                            discovered_subpages.append((priority, full_sub_url))

                                                discovered_subpages.sort(key=lambda x: x[0], reverse=True)
                                                sorted_subpages = [u for _, u in discovered_subpages]

                                                for sub_p_url in sorted_subpages[:6]:
                                                    if not budget_available():
                                                        break
                                                    try:
                                                        sub_p_html = downloader.fetch_text(sub_p_url)
                                                        if sub_p_html:
                                                            sub_p_soup = BeautifulSoup(sub_p_html, "html.parser")
                                                            sub_p_elems = extract_html_subjects(sub_p_soup, sub_p_url)
                                                            if len(sub_p_elems) < 3 and budget_available():
                                                                for linked_doc_url, linked_doc_text in discover_linked_curriculum_documents(
                                                                    sub_p_soup,
                                                                    sub_p_url,
                                                                    max_documents=8,
                                                                ):
                                                                    if not budget_available() or is_explicitly_historical(
                                                                        linked_doc_url, linked_doc_text
                                                                    ):
                                                                        continue
                                                                    parsed_linked_doc = self._try_parse_candidate_pdf(
                                                                        downloader,
                                                                        linked_doc_url,
                                                                        d_code,
                                                                        d_title,
                                                                        u_name,
                                                                    )
                                                                    if parsed_linked_doc:
                                                                        consider_curriculum(
                                                                            parsed_linked_doc,
                                                                            linked_doc_url,
                                                                        )
                                                                        if found_curriculum:
                                                                            break
                                                                if found_curriculum:
                                                                    break
                                                            if len(sub_p_elems) < 10:
                                                                dyn_sub = extract_dynamic_widget_subjects(sub_p_soup, sub_p_url, web_url, downloader)
                                                                if len(dyn_sub) > len(sub_p_elems):
                                                                    sub_p_elems = dyn_sub

                                                            # Comprobar si la subpágina apunta a un portal institucional de gestión docente (SIA, Apps, etc.)
                                                            portal_links = []
                                                            for a_p in sub_p_soup.find_all("a", href=True):
                                                                hp_val = a_p["href"].strip()
                                                                tp_val = a_p.get_text(strip=True).lower()
                                                                if any(kw in hp_val.lower() for kw in INSTITUTIONAL_PORTAL_KEYWORDS) or any(kw in tp_val for kw in INSTITUTIONAL_PORTAL_KEYWORDS):
                                                                    full_portal_url = urllib.parse.urljoin(sub_p_url, hp_val)
                                                                    if is_same_or_subdomain(full_portal_url, web_url) and any(seg in full_portal_url.lower() for seg in ["/estudio/", "/plan/", "/asignatura/", "/grau/", "/grado/"]):
                                                                        portal_links.append(full_portal_url)

                                                            target_eval_urls = portal_links if portal_links else ([sub_p_url] if len(sub_p_elems) < 3 else [])

                                                            for tr_url in target_eval_urls:
                                                                if not budget_available():
                                                                    break
                                                                try:
                                                                    from spa_crawler import SPALayoutCrawler
                                                                    spa_c = SPALayoutCrawler.get_shared_instance(
                                                                        timeout=max(1, int(downloader.timeout))
                                                                    )
                                                                    rendered_sub = spa_c.render_spa_page(tr_url)
                                                                    if rendered_sub:
                                                                        r_soup = BeautifulSoup(rendered_sub, "html.parser")
                                                                        r_elems = extract_html_subjects(r_soup, tr_url)
                                                                        if len(r_elems) > len(sub_p_elems):
                                                                            sub_p_elems = r_elems
                                                                            sub_p_url = tr_url
                                                                            sub_p_soup = r_soup
                                                                except Exception as exc:
                                                                    logger.debug(f"Excepción controlada en crawling: {exc}")
                                                                    pass

                                                            if len(sub_p_elems) >= 3:
                                                                elementos_html = sub_p_elems
                                                                target_soup = sub_p_soup
                                                                target_html = sub_p_html
                                                                target_link = sub_p_url
                                                                break
                                                    except Exception as exc:
                                                        logger.debug(f"Excepción controlada en crawling: {exc}")
                                                        pass



                                            # Paso 1: Si tras variantes sigue teniendo < 3 asignaturas (contenedor SPA vacío JS), renderizar con Playwright
                                            current_ects = compute_curriculum_total_ects(elementos_html)
                                            if len(elementos_html) < 3:
                                                try:
                                                    from spa_crawler import SPALayoutCrawler
                                                    spa_crawler = SPALayoutCrawler.get_shared_instance(
                                                        timeout=max(1, int(downloader.timeout))
                                                    )
                                                    rendered_html = spa_crawler.render_spa_page(target_link)
                                                    if rendered_html:
                                                        if getattr(rendered_html, "is_download", False):
                                                            pdf_bytes = getattr(rendered_html, "content_bytes", b"")
                                                            if pdf_bytes and (b"%PDF-" in pdf_bytes[:1024] or getattr(rendered_html, "filename", "").lower().endswith(".pdf")):
                                                                pdf_curriculum = parse_boe_pdf(pdf_bytes, d_title, d_level)
                                                                if pdf_curriculum and len(pdf_curriculum.get("elementos_curriculares", [])) >= 3:
                                                                    if not consider_curriculum(pdf_curriculum, target_link):
                                                                        continue
                                                                    logger.info("     -> [Playwright Download Rescate] Encontrado PDF oficial con %d asignaturas: %s", len(pdf_curriculum['elementos_curriculares']), target_link)
                                                                    break
                                                        else:
                                                            spa_soup = BeautifulSoup(rendered_html, "html.parser")
                                                            spa_elementos = extract_html_subjects(spa_soup, target_link)
                                                            if len(spa_elementos) > len(elementos_html):
                                                                elementos_html = spa_elementos
                                                                target_soup = spa_soup
                                                                target_html = rendered_html
                                                                current_ects = compute_curriculum_total_ects(elementos_html)
                                                except Exception as exc:
                                                    logger.warning("Excepción controlada en crawling Playwright/SPA: %s", exc)
                                                    pass

                                            # Paso 2: Si el temario sigue siendo parcial, explorar sub-enlaces de menciones/especialidades/TFG en la misma ficha
                                            if elementos_html and req_ects > 0 and current_ects < req_ects:
                                                sub_itinerarios = []
                                                for a_sub in target_soup.find_all("a", href=True):
                                                    h_sub = a_sub["href"].strip()
                                                    t_sub = a_sub.get_text(strip=True).lower()
                                                    if any(k in t_sub or k in h_sub.lower() for k in [
                                                        "mencion", "mención", "menció", "mencions", "especialidad", "especialidades", "especialitats",
                                                        "optativas", "optatives", "hautazkoak", "itinerari", "itineraris", "itinerario", "itinerarios",
                                                        "ibilbidea", "aipamena", "aipamenak", "track", "major", "specialization",
                                                        "trabajo fin", "tfg", "tfm", "treball fi", "traballo fin", "menciones"
                                                    ]):
                                                        full_sub = urllib.parse.urljoin(target_link, h_sub)
                                                        if is_same_or_subdomain(full_sub, web_url) and full_sub != target_link and is_valid_web_url(full_sub):
                                                            sub_itinerarios.append(full_sub)

                                                seen_names = {
                                                    curriculum_element_key(e.get("nombre_elemento", ""))
                                                    for e in elementos_html
                                                }
                                                for s_url in sub_itinerarios[:8]:
                                                    if not budget_available():
                                                        break
                                                    try:
                                                        s_html = downloader.fetch_text(s_url)
                                                        s_soup = BeautifulSoup(s_html, "html.parser")
                                                        s_elems = extract_html_subjects(s_soup)
                                                        for se in s_elems:
                                                            s_name = curriculum_element_key(se.get("nombre_elemento", ""))
                                                            if s_name and s_name not in seen_names:
                                                                seen_names.add(s_name)
                                                                elementos_html.append(se)
                                                        current_ects = compute_curriculum_total_ects(elementos_html)
                                                    except Exception as exc:
                                                        logger.debug("Excepción controlada en crawling: %s", exc)
                                                        pass

                                            # Paso 3: Si sigue siendo parcial o faltan asignaturas, comprobar si la ficha enlaza el PDF oficial del plan completo
                                            if not found_curriculum and budget_available() and (len(elementos_html) < 3 or (req_ects > 0 and current_ects < req_ects)):
                                                for a_pdf in target_soup.find_all("a", href=True):
                                                    if not budget_available():
                                                        break
                                                    h_pdf = a_pdf["href"].strip()
                                                    t_pdf = a_pdf.get_text(strip=True).lower()
                                                    if h_pdf.lower().endswith(".pdf") or any(pk in t_pdf for pk in ["plan de estudios", "pla d'estudis", "guía docente", "guia docent", "folleto"]) or any(pk in t_pdf or pk in h_pdf.lower() for pk in MEMORIA_VERIFICADA_KEYWORDS):
                                                        pdf_link = urllib.parse.urljoin(target_link, h_pdf)
                                                        if pdf_link.lower().endswith(".pdf") and is_same_or_subdomain(pdf_link, web_url):
                                                            parsed_pdf = self._try_parse_candidate_pdf(downloader, pdf_link, d_code, d_title, u_name)
                                                            if parsed_pdf and parsed_pdf.get("total_elementos", 0) > len(elementos_html):
                                                                if not consider_curriculum(parsed_pdf, pdf_link):
                                                                    continue
                                                                break
                                            
                                            # Extraer precios de matrículas en universidades privadas
                                            extracted_pricing = {}
                                            if "privad" in (u_type or "").lower():
                                                extracted_pricing = extract_private_university_pricing(target_soup, target_html)
                                                
                                                # Si no se encuentra precio en la subpágina directa, escanear enlaces de precios/admisión de la portada
                                                if not extracted_pricing.get("precio_credito_ects"):
                                                    pricing_keywords = ["precio", "tasas", "tuition", "fees", "coste", "admision", "admissions", "honorarios"]
                                                    pricing_links = [
                                                        urllib.parse.urljoin(web_url, a["href"].strip()) 
                                                        for a in soup.find_all("a", href=True) 
                                                        if any(pk in a.get_text(strip=True).lower() or pk in a["href"].lower() for pk in pricing_keywords)
                                                        and is_valid_web_url(a["href"])
                                                    ]
                                                    for plink in pricing_links[:3]:
                                                        if not budget_available():
                                                            break
                                                        try:
                                                            p_html = downloader.fetch_text(plink)
                                                            p_soup = BeautifulSoup(p_html, "html.parser")
                                                            extracted_pricing = extract_private_university_pricing(p_soup, p_html)
                                                            if extracted_pricing.get("precio_credito_ects"):
                                                                break
                                                        except Exception as exc:
                                                            logger.debug("Excepción controlada en crawling: %s", exc)
                                                            pass

                                            if not found_curriculum and len(elementos_html) >= 3 and is_html_page_matching_degree(
                                                target_soup,
                                                d_title,
                                                u_name,
                                                target_link,
                                                allow_curriculum_url_identity=True,
                                            ):
                                                if not consider_curriculum(
                                                    build_html_curriculum_payload(
                                                        elementos_html,
                                                        d_title,
                                                        infer_declared_total_ects(target_soup),
                                                    ),
                                                    target_link,
                                                ):
                                                    continue
                                                if extracted_pricing.get("precio_credito_ects"):
                                                    found_curriculum["precio_credito_ects"] = extracted_pricing["precio_credito_ects"]
                                                    found_curriculum["precio_credito_2"] = extracted_pricing.get("precio_credito_2")
                                                    found_curriculum["precio_credito_3"] = extracted_pricing.get("precio_credito_3")
                                                    found_curriculum["precio_credito_4"] = extracted_pricing.get("precio_credito_4")
                                                    found_curriculum["precio_estimado_anual"] = extracted_pricing.get("precio_estimado_anual")
                                                    found_curriculum["fuente_precio"] = "Web Oficial Universidad Privada"

                                                logger.info("     -> Encontrados datos e información en subpágina de titulación: %s", target_link)
                                                break
                                            elif found_curriculum:
                                                break
                                        except Exception as t_err:
                                            logger.debug("     -> Error al examinar subpágina de titulación '%s': %s", target_link, t_err)
                        except Exception as sub_err:
                            logger.debug("     -> Excepción al escanear sub-página '%s': %s", candidate_page_url, sub_err)

                except Exception as crawl_err:
                    logger.debug("     -> Error al rastrear la web oficial para [%s]: %s", d_code, crawl_err)

            # ESTRATEGIA 2.5: Exploración Orgánica de Centros Adscritos Descubiertos (Patrón 1)
            # ESTRATEGIA 2.25: Descubrimiento externo acotado para portales no
            # enlazados desde la raíz. El buscador sólo aporta candidatos; no
            # se usa como fuente de datos ni relaja la identidad institucional.
            if not found_curriculum and budget_available():
                search_cache_key = (
                    str(u_name or "").strip().lower(),
                    str(d_title or "").strip().lower(),
                    str(d_level or "").strip().lower(),
                    str(web_url or "").strip().lower(),
                )
                with self.web_search_lock:
                    search_result = self.web_search_cache.get(search_cache_key)
                if search_result is None:
                    search_result = discover_search_candidates(
                        u_name,
                        d_title,
                        d_level,
                        web_url,
                        downloader.fetch_text,
                        query_limit=WEB_SEARCH_DISCOVERY_MAX_QUERIES,
                        result_limit=WEB_SEARCH_DISCOVERY_MAX_RESULTS,
                    )
                    with self.web_search_lock:
                        self.web_search_cache[search_cache_key] = search_result
                search_records = search_result.get("records", []) if isinstance(search_result, dict) else []
                stats["web_search_queries"] = stats.get("web_search_queries", 0) + len(
                    search_result.get("queries", []) if isinstance(search_result, dict) else []
                )
                stats["web_search_candidates"] = stats.get("web_search_candidates", 0) + len(search_records)
                stats["web_search_errors"] = stats.get("web_search_errors", 0) + len(
                    search_result.get("errors", []) if isinstance(search_result, dict) else []
                )
                if isinstance(search_result, dict):
                    stats["web_search_error_kinds"] = sorted(
                        set(stats.get("web_search_error_kinds", []))
                        | {str(error) for error in search_result.get("errors", [])}
                    )
                if self.ledger and search_records:
                    self.ledger.record_discovery_evidence(
                        [
                            {
                                "url": record.get("url"),
                                "source_kind": "web_search",
                                "anchor_text": record.get("title", ""),
                                "snippet": record.get("snippet", ""),
                                "source_url": web_url,
                            }
                            for record in search_records
                            if record.get("url")
                        ],
                        university_code=u_code,
                        phase="fase1_parte2",
                    )
                for search_record in search_records:
                    if found_curriculum or not budget_available():
                        break
                    search_url = str(search_record.get("url") or "").strip()
                    if not search_url:
                        continue
                    try:
                        time.sleep(WEB_SEARCH_RETRY_DELAY)
                        if search_url.lower().endswith(".pdf"):
                            parsed_search = self._try_parse_candidate_pdf(
                                downloader, search_url, d_code, d_title, u_name
                            )
                            if parsed_search and consider_curriculum(parsed_search, search_url):
                                stats["web_search_recoveries"] = stats.get("web_search_recoveries", 0) + 1
                                logger.info(
                                    "     -> [BUSCADOR] Encontrado plan PDF compatible: %s",
                                    search_url,
                                )
                                break
                            continue

                        search_html = downloader.fetch_text(search_url)
                        if not search_html:
                            continue
                        search_soup = BeautifulSoup(search_html, "html.parser")
                        search_elements = extract_html_subjects(search_soup, search_url)
                        if len(search_elements) < 10:
                            dynamic_search_elements = extract_dynamic_widget_subjects(
                                search_soup, search_url, web_url, downloader
                            )
                            if len(dynamic_search_elements) > len(search_elements):
                                search_elements = dynamic_search_elements
                        search_matches_degree = is_html_page_matching_degree(
                            search_soup,
                            d_title,
                            u_name,
                            search_url,
                            allow_curriculum_url_identity=True,
                        )
                        if search_matches_degree and len(search_elements) >= 3:
                            if consider_curriculum(
                                build_html_curriculum_payload(
                                    search_elements,
                                    d_title,
                                    infer_declared_total_ects(search_soup),
                                ),
                                search_url,
                            ):
                                stats["web_search_recoveries"] = stats.get("web_search_recoveries", 0) + 1
                                logger.info(
                                    "     -> [BUSCADOR] Encontradas %d asignaturas HTML compatibles: %s",
                                    len(search_elements),
                                    search_url,
                                )
                                break
                        # Muchas fichas indexadas por buscadores sólo enlazan
                        # el PDF/plan desde la propia página. Seguir esos
                        # documentos conserva la misma trazabilidad y límites.
                        if search_matches_degree and budget_available():
                            for document_url, document_text in discover_linked_curriculum_documents(
                                search_soup, search_url, max_documents=8
                            ):
                                if not budget_available() or is_explicitly_historical(document_url, document_text):
                                    continue
                                parsed_document = self._try_parse_candidate_pdf(
                                    downloader, document_url, d_code, d_title, u_name
                                )
                                if parsed_document and consider_curriculum(parsed_document, document_url):
                                    stats["web_search_recoveries"] = stats.get("web_search_recoveries", 0) + 1
                                    logger.info(
                                        "     -> [BUSCADOR] Encontrado documento curricular enlazado: %s",
                                        document_url,
                                    )
                                    break
                    except Exception as search_err:
                        logger.debug(
                            "Excepción controlada al evaluar resultado de búsqueda %s: %s",
                            search_url,
                            search_err,
                        )

            # ESTRATEGIA 2.5: Exploración Orgánica de Centros Adscritos Descubiertos (Patrón 1)
            if not found_curriculum and budget_available():
                discovered_hubs = self.organic_affiliated_hubs.get(web_url, {})
                d_title_low = d_title.lower()
                matched_hub_url = None
                matched_hub_name = None
                
                for ext_dom, (hub_url, hub_name) in discovered_hubs.items():
                    hub_tokens = re.findall(r'\b[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]{3,}\b', hub_name.lower())
                    if any(tok in d_title_low for tok in hub_tokens if tok not in TITLE_STOPWORDS and tok not in univ_name_tokens):
                        matched_hub_url = hub_url
                        matched_hub_name = hub_name
                        break
                
                if matched_hub_url:
                    try:
                        logger.info("     -> [Centro Adscrito Orgánico] Descubierto '%s' (%s)", matched_hub_name, matched_hub_url)
                        with self.organic_lock:
                            has_cached = matched_hub_url in self.organic_affiliated_cache
                        if not has_cached:
                            built_map = self._build_academic_catalog_map(
                                downloader, matched_hub_url, max_depth=5, max_hubs=8, max_hops=3
                            )
                            with self.organic_lock:
                                self.organic_affiliated_cache[matched_hub_url] = built_map
                        with self.organic_lock:
                            center_map = self.organic_affiliated_cache.get(matched_hub_url)
                        if center_map:
                            center_candidates = []
                            for kw in title_keywords:
                                kw_low = kw.lower()
                                for map_tok, links in center_map.items():
                                    if kw_low in map_tok:
                                        for c_u, c_t in links:
                                            center_candidates.append((c_u, c_t))
                            if center_candidates:
                                for c_u, c_t in center_candidates[:3]:
                                    if found_curriculum:
                                        break
                                    try:
                                        c_html = downloader.fetch_text(c_u)
                                        c_soup = BeautifulSoup(c_html, "html.parser")
                                        c_elems = extract_html_subjects(c_soup)
                                        if len(c_elems) >= 3 and is_html_page_matching_degree(
                                            c_soup,
                                            d_title,
                                            u_name,
                                            c_u,
                                            allow_curriculum_url_identity=True,
                                        ):
                                            if not consider_curriculum(
                                                build_html_curriculum_payload(
                                                    c_elems,
                                                    d_title,
                                                    infer_declared_total_ects(c_soup),
                                                ),
                                                c_u,
                                            ):
                                                continue
                                            found_curriculum["centro_adscrito"] = matched_hub_name
                                            logger.info("     -> [Centro Adscrito Éxito] Encontradas %d asignaturas en %s", len(c_elems), c_u)
                                            break
                                    except Exception as exc:
                                        logger.debug("Excepción controlada en crawling: %s", exc)
                                        pass
                    except Exception as e_center:
                        logger.debug("     -> Error al consultar centro adscrito orgánico '%s': %s", matched_hub_name, e_center)

            # ESTRATEGIA 3: Modelado de Alianzas Universitarias Europeas y Erasmus Mundus (Patrón 3)
            is_european_program = any(k in d_title.lower() for k in EUROPEAN_ALLIANCES_KEYWORDS)
            if is_european_program and (not found_curriculum or len(found_curriculum.get("elementos_curriculares", [])) == 0):
                discovered_alliance_url = None
                discovered_hubs = self.organic_affiliated_hubs.get(web_url, {})
                for ext_dom, (hub_url, hub_name) in discovered_hubs.items():
                    if any(ak in hub_name.lower() or ak in hub_url.lower() for ak in ["sea-eu", "erasmus", "eunice", "charmeu", "arqus", "civica", "civis", "alliance", "european"]):
                        discovered_alliance_url = hub_url
                        break
                        
                direct_source_url = discovered_alliance_url or existing_direct_url or deg.get("boe_url") or web_url
                logger.info("     -> [Alianza Europea / Erasmus Mundus] Fuente localizada -> %s", direct_source_url)

            # Si ninguna fuente alcanzó completitud, conservar el mejor
            # parcial como evidencia auditable. Esto ocurre después de haber
            # probado todas las estrategias, para que una primera coincidencia
            # incompleta no bloquee la recuperación de una fuente mejor.
            if not found_curriculum and isinstance(fallback_curriculum, dict):
                found_curriculum = fallback_curriculum
                direct_source_url = fallback_source_url
            if degree_deadline_reached:
                stats["degree_timeouts"] = stats.get("degree_timeouts", 0) + 1
                logger.warning(
                    "     [PRESUPUESTO AGOTADO] Se conserva la mejor evidencia encontrada para la titulación."
                )

            # Guardar el plan y la URL directa donde se ha encontrado
            if found_curriculum and direct_source_url:
                source_key = normalize_url(direct_source_url)
                previous_identity = accepted_source_identities.get(source_key)
                if previous_identity and not are_degree_titles_compatible(
                    previous_identity["title"], d_title, u_name
                ):
                    stats["source_identity_conflicts"] = stats.get("source_identity_conflicts", 0) + 1
                    logger.warning(
                        "     [CUARENTENA IDENTIDAD] La URL curricular ya fue aceptada "
                        "para una titulación incompatible: %s", direct_source_url
                    )
                    found_curriculum = None
                    direct_source_url = None
                elif source_key:
                    accepted_source_identities.setdefault(
                        source_key,
                        {"code": str(d_code), "title": str(d_title or "")},
                    )

            if found_curriculum and direct_source_url:
                logger.info("     [CANDIDATO PARTE 2] Plan localizado en web oficial: '%s'", direct_source_url)
                
                degree_data = load_json_safe(plan_file)
                degree_data["codigo_estudio"] = d_code
                degree_data["titulo"] = deg.get("titulo", "")
                degree_data["nivel_academico"] = deg.get("nivel_academico", "")
                degree_data["universidad_codigo"] = u_code
                degree_data["universidad_nombre"] = u_name
                degree_data["fecha_procesado"] = datetime.now().isoformat()
                degree_data["estado_fuente"] = "encontrada_pendiente_validacion"
                degree_data["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                degree_data["web_fuente_directa_url"] = direct_source_url
                
                # Origen de fuente semántico
                if found_curriculum.get("centro_adscrito"):
                    degree_data["centro_adscrito"] = found_curriculum["centro_adscrito"]
                    degree_data["origen_fuente"] = "centro_adscrito_organico"
                elif found_curriculum.get("es_alianza_europea"):
                    degree_data["es_alianza_europea"] = True
                    degree_data["origen_fuente"] = "alianza_europea_erasmus_mundus"
                else:
                    degree_data["origen_fuente"] = "web_oficial_universidad"
                    
                merge_preserved_pricing(degree_data, found_curriculum, deg)
                
                source = source_record(
                    direct_source_url,
                    "WEB_OFICIAL_UNIVERSIDAD",
                    confidence=0.85 if not found_curriculum.get("es_alianza_europea") else 0.65,
                )
                fuentes = degree_data.setdefault("fuentes", [])
                if not isinstance(fuentes, list):
                    fuentes = []
                    degree_data["fuentes"] = fuentes
                fuentes[:] = [item for item in fuentes if item.get("url") != source["url"]]
                fuentes.append(source)
                quality = apply_plan_quality(degree_data, found_curriculum, degree_data["origen_fuente"])
                found_curriculum["plan_completo"] = quality["plan_completo"]
                found_curriculum["ects_totales_detectados"] = quality["ects_totales_detectados"]
                found_curriculum["ects_exigidos"] = quality["ects_exigidos"]
                degree_data["estado_fuente"] = "verificada" if quality["publicable"] else "candidata_no_publicable"
                if quality["publicable"]:
                    stats["resolved_degrees_count"] += 1
                    logger.info("     [VERIFICADO PARTE 2] Plan publicado con estado %s.", quality['estado'])
                else:
                    logger.info("     [CUARENTENA PARTE 2] Plan no publicado: %s (%s).", quality['estado'], ', '.join(quality['errores']) or quality['completitud'])
                
                atomic_json_dump(degree_data, plan_file)
                self.checkpoint.update_degree_record(d_code, direct_source_url, datetime.now().strftime("%Y-%m-%d"), datetime.now().isoformat())
            else:
                logger.debug("     -> No se encontró plan de estudios en la web oficial para [%s].", d_code)
                existing_data = load_json_safe(plan_file, default=None)
                if not isinstance(existing_data, dict):
                    existing_data = {}
                if (
                    invalid_existing_direct_url
                    and existing_direct_url
                    and normalize_url(existing_data.get("web_fuente_directa_url"))
                    == normalize_url(existing_direct_url)
                ):
                    rejected_url = existing_data.pop("web_fuente_directa_url", None)
                    fuentes_rechazadas = existing_data.setdefault("fuentes_rechazadas", [])
                    if not isinstance(fuentes_rechazadas, list):
                        fuentes_rechazadas = []
                        existing_data["fuentes_rechazadas"] = fuentes_rechazadas
                    rejected_key = normalize_url(rejected_url)
                    if rejected_key and not any(
                        isinstance(item, dict)
                        and normalize_url(item.get("url")) == rejected_key
                        for item in fuentes_rechazadas
                    ):
                        fuentes_rechazadas.append({
                            "url": rejected_url,
                            "motivo": "identidad_pagina_no_coincide",
                            "fecha": datetime.now().isoformat(),
                        })
                    fuentes = existing_data.get("fuentes")
                    if isinstance(fuentes, list):
                        existing_data["fuentes"] = [
                            item for item in fuentes
                            if not (
                                isinstance(item, dict)
                                and normalize_url(item.get("url")) == rejected_key
                                and "web" in str(item.get("tipo") or "").lower()
                            )
                        ]
                identity = {
                    "codigo_estudio": d_code,
                    "titulo": str(d_title or "").strip(),
                    "nivel_academico": str(d_level or "").strip(),
                    "universidad_codigo": str(u_code or "").zfill(3),
                    "universidad_nombre": str(u_name or "").strip(),
                }
                for key, value in identity.items():
                    if value and not str(existing_data.get(key) or "").strip():
                        existing_data[key] = value
                existing_data.setdefault("plan_estudios", None)
                existing_data["estado_fuente"] = "sin_plan_actual_conservando_anterior" if existing_data.get("plan_estudios") else "sin_plan_actual_sin_dato"
                existing_data["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                atomic_json_dump(existing_data, plan_file)

        # Artefacto de ejecución para el flujo doctoral; no se persiste en
        # ningún fichero de datos ni se expone por API.
        stats["_catalog_map"] = catalog_map
        stats["_sitemap_urls"] = sitemap_urls
        return stats

    def process_university_doctorates(self, u_code: str, u_name: str, doctorate_degrees: list, web_url: str, downloader, catalog_map: dict = None, force: bool = False, sitemap_urls: list | None = None) -> dict:
        """
        Procesa de forma universal y estructurada los programas oficiales de Doctorado (RD 99/2011).
        Recupera líneas de investigación científica, escuela de doctorado y actividades formativas.
        """
        stats = {"total_doctorates": len(doctorate_degrees), "resolved_doctorates": 0}

        for d_idx, deg in enumerate(doctorate_degrees, 1):
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            d_level = deg.get("nivel_academico", "")
            downloader.set_degree_context(d_code)
            plan_file = find_plan_filepath(u_code, d_code)

            degree_data = load_json_safe(plan_file, default={})
            if not isinstance(degree_data, dict):
                degree_data = {}

            # Si ya está verificado como programa doctoral y no se fuerza, saltar
            if not force and degree_data.get("estado_calidad") in ("verificado_programa_doctoral", "doctorado_verificado") and degree_data.get("programa_doctoral"):
                continue

            target_urls_to_try = []
            if degree_data.get("web_fuente_directa_url"):
                target_urls_to_try.append(degree_data["web_fuente_directa_url"])

            # Buscar en catalog_map enlaces que coincidan con palabras clave del título
            if catalog_map:
                d_tokens = [tok for tok in re.findall(r'[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]{4,}', d_title.lower()) if tok not in TITLE_STOPWORDS]
                candidate_scores = {}
                # ``_build_academic_catalog_map`` indexa por término y guarda
                # listas de (URL, texto). No confundir la clave léxica con la
                # URL: la implementación anterior descartaba todos los
                # candidatos doctorales al intentar descargar "bioinformática"
                # o "economía" como si fueran direcciones web.
                for entries in catalog_map.values():
                    iterable = entries if isinstance(entries, (list, tuple)) else [entries]
                    for entry in iterable:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            cat_url, cat_text = str(entry[0]), str(entry[1])
                        else:
                            cat_url, cat_text = str(entry), ""
                        if not is_valid_web_url(cat_url):
                            continue
                        haystack = f"{cat_url} {cat_text}".lower()
                        match_count = sum(1 for tok in d_tokens if tok in haystack)
                        if match_count >= 2:
                            candidate_scores[cat_url] = max(candidate_scores.get(cat_url, 0), match_count)
                for cat_url, _ in sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True):
                    if cat_url not in target_urls_to_try:
                        target_urls_to_try.append(cat_url)

            # El sitemap suele contener la ficha doctoral exacta aunque no
            # esté enlazada desde la portada ni desde el catálogo de grados.
            if sitemap_urls:
                d_tokens = [
                    unicodedata.normalize("NFKD", tok.lower()).encode("ASCII", "ignore").decode("utf-8")
                    for tok in re.findall(r"[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]{4,}", d_title)
                    if tok not in TITLE_STOPWORDS
                ]
                sitemap_candidates = []
                for candidate_url in sitemap_urls:
                    candidate_low = unicodedata.normalize("NFKD", str(candidate_url).lower()).encode("ASCII", "ignore").decode("utf-8")
                    matches = sum(1 for tok in d_tokens if tok in candidate_low)
                    has_doctor_marker = any(marker in candidate_low for marker in ("doctor", "phd", "recerca", "investigacio"))
                    if matches >= 2 and has_doctor_marker:
                        sitemap_candidates.append((matches, str(candidate_url)))
                for _, candidate_url in sorted(sitemap_candidates, reverse=True)[:10]:
                    if candidate_url not in target_urls_to_try:
                        target_urls_to_try.append(candidate_url)

            # Algunos portales excluyen las fichas doctorales de su sitemap
            # académico. Explorar sólo hubs doctorales convencionales y sus
            # enlaces semánticamente coincidentes mantiene el alcance acotado
            # y evita depender de una URL fija de una universidad concreta.
            if web_url:
                parsed_web = urllib.parse.urlparse(web_url)
                hub_paths = ("/es/doctorados", "/doctorados", "/doctorado", "/phd", "/doctorate")
                d_tokens = [
                    unicodedata.normalize("NFKD", tok.lower()).encode("ASCII", "ignore").decode("utf-8")
                    for tok in re.findall(r"[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]{4,}", d_title)
                    if tok not in TITLE_STOPWORDS
                ]
                for hub_path in hub_paths:
                    hub_url = urllib.parse.urlunsplit((parsed_web.scheme, parsed_web.netloc, hub_path, "", ""))
                    try:
                        hub_html = downloader.fetch_text(hub_url)
                        if not hub_html:
                            continue
                        hub_soup = BeautifulSoup(hub_html, "html.parser")
                        for anchor in hub_soup.find_all("a", href=True):
                            candidate_url = urllib.parse.urljoin(hub_url, anchor["href"].strip())
                            if not is_valid_web_url(candidate_url) or not is_same_or_subdomain(candidate_url, web_url):
                                continue
                            haystack = f"{candidate_url} {anchor.get_text(' ', strip=True)}".lower()
                            normalized = unicodedata.normalize("NFKD", haystack).encode("ASCII", "ignore").decode("utf-8")
                            matches = sum(1 for tok in d_tokens if tok in normalized)
                            if matches >= 2 and any(marker in normalized for marker in ("doctor", "phd", "recerca", "investigacio")):
                                if candidate_url not in target_urls_to_try:
                                    target_urls_to_try.insert(0, candidate_url)
                    except Exception as exc:
                        logger.debug("Excepción al explorar hub doctoral %s: %s", hub_url, exc)

            # Intentar extracción con el extractor genérico de doctorados
            doc_data = None
            for cand_url in target_urls_to_try[:3]:
                try:
                    res = extract_generic_doctoral_program(cand_url, downloader)
                    if res and res.get("total_lineas", 0) >= 2:
                        doc_data = res
                        break
                except Exception as ex:
                    logger.debug("Excepción en extracción doctoral de %s: %s", cand_url, ex)

            now_iso = datetime.now().isoformat()
            degree_data.update({
                "codigo_estudio": d_code,
                "titulo": d_title,
                "nivel_academico": d_level,
                "universidad_codigo": str(u_code).zfill(3),
                "universidad_nombre": u_name,
                "fecha_procesado": now_iso,
                "fecha_ultima_comprobacion_fuente": now_iso,
            })
            # La ficha doctoral normalmente no contiene información de
            # precios. No sustituir valores ya recolectados por ``None`` al
            # actualizar exclusivamente la parte curricular.
            merge_preserved_pricing(degree_data, recovered={}, catalog=deg)

            if doc_data and doc_data.get("total_lineas", 0) >= 2:
                final_url = doc_data.get("url_fuente") or (target_urls_to_try[0] if target_urls_to_try else web_url)
                lines = doc_data.get("lineas_investigacion", [])
                escuela = doc_data.get("escuela_doctorado", "Escuela Internacional de Doctorado / Posgrado")
                
                curriculum_payload = {
                    "nombre_plan": d_title,
                    "codigo_plan": d_code,
                    "tipo_estructura": "programa_doctorado_investigacion",
                    "normativa": "Real Decreto 99/2011",
                    "ects_exigidos": 0.0,
                    "plan_completo": True,
                    "ects_totales_detectados": 0.0,
                    "elementos_curriculares": [
                        {
                            "nombre_elemento": line,
                            "caracter": "INVESTIGACION",
                            "modulo": "Línea de Investigación",
                            "materia": escuela,
                            "creditos_ects": None,
                            "curso": "Tutela Académica",
                        }
                        for line in lines
                    ],
                    "resumen_creditos": {"Investigación y Tesis": "Tutela Académica Anual"}
                }
                degree_data["plan_estudios"] = curriculum_payload
                degree_data["programa_doctoral"] = doc_data
                degree_data["web_fuente_directa_url"] = final_url
                degree_data["origen_fuente"] = "web_oficial_universidad"
                degree_data["estado_fuente"] = "verificada"
                degree_data["estado_calidad"] = "verificado_programa_doctoral"
                stats["resolved_doctorates"] += 1
                logger.info("     [DOCTORADO VERIFICADO] [%s] %s: %d líneas oficiales en %s", d_code, d_title[:50], len(lines), escuela)
            else:
                # Si no se localizaron líneas en la web, el título sigue siendo 100% legal y oficial bajo RD 99/2011
                curriculum_payload = {
                    "nombre_plan": d_title,
                    "codigo_plan": d_code,
                    "tipo_estructura": "programa_doctorado_investigacion",
                    "normativa": "Real Decreto 99/2011",
                    "ects_exigidos": 0.0,
                    "plan_completo": True,
                    "ects_totales_detectados": 0.0,
                    "elementos_curriculares": [],
                    "resumen_creditos": {"Investigación y Tesis": "Tutela Académica Anual"}
                }
                degree_data["plan_estudios"] = curriculum_payload
                degree_data["programa_doctoral"] = {
                    "regulacion": "RD 99/2011",
                    "tipo_programa": "investigacion_doctoral",
                    "escuela_doctorado": "Escuela Internacional de Posgrado / Doctorado",
                    "duracion_anos": {"tiempo_completo": 3, "tiempo_parcial": 5},
                    "lineas_investigacion": [],
                    "actividades_formativas": []
                }
                degree_data["origen_fuente"] = "resolucion_boe_ruct"
                degree_data["estado_fuente"] = "programa_doctoral_oficial"
                degree_data["estado_calidad"] = "doctorado_oficial"

            atomic_json_dump(degree_data, plan_file)

        return stats


from extractors.consortium_sync import (
    _quarantine_incompatible_direct_source_collisions,
    normalize_joint_title,
    propagate_interuniversity_and_shared_boe_plans,
)


def run_phase1_part2(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
    degree_title_filter: str | None = None,
    degree_level_filter: str | None = None,
    target_universities: list[str] | set[str] | None = None,
) -> dict:
    """
    Punto de entrada principal para la Fase 1 - Parte 2:
    Rastrea las webs oficiales de las universidades de forma paralela para encontrar información faltante.
    """
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 2: ESCANEO PARALELO WEBS OFICIALES")
    print("======================================================================")

    if not os.path.exists(UNIVERSIDADES_JSON) or not os.path.exists(TITULACIONES_JSON):
        print(" [AVISO PARTE 2] No existen archivos de datos de universidades/titulaciones. Finalizando.")
        return {"status": "skipped", "reason": "missing_catalogs"}

    if max_workers is None:
        max_workers = WEB_CRAWLER_WORKERS
    max_workers = max(1, int(max_workers))

    try:
        with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
            universities = json.load(f)
        with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
            titulaciones_por_univ = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f" [AVISO PARTE 2] Catálogos inválidos; no se inicia el escaneo: {exc}")
        return {"status": "skipped", "reason": "invalid_catalogs", "error": str(exc)}

    if not isinstance(universities, list) or not isinstance(titulaciones_por_univ, dict):
        print(" [AVISO PARTE 2] Formato de catálogos inválido; no se inicia el escaneo.")
        return {"status": "skipped", "reason": "invalid_catalogs"}

    valid_universities = [item for item in universities if isinstance(item, dict)]
    if universities and not valid_universities:
        print(" [AVISO PARTE 2] El catálogo de universidades no contiene registros válidos.")
        return {"status": "skipped", "reason": "invalid_catalogs"}
    universities = valid_universities

    effective_targets = target_universities or TARGET_UNIVERSITY_CODES
    if effective_targets:
        target_set = {str(c).zfill(3) for c in effective_targets}
        universities = [u for u in universities if str(u.get("codigo", "")).zfill(3) in target_set]
    # Cuando no se está filtrando por titulaciones, conservar el límite
    # histórico de instituciones tal cual. Las campañas de recuperación, en
    # cambio, deben aplicar este límite después de descartar universidades sin
    # expedientes pendientes: de otro modo una muestra puede agotarse en
    # registros vacíos y medir cero trabajo real.
    defer_university_limit = bool(limit_degrees is not None or degree_title_filter or degree_level_filter)
    if limit_universities is not None and not defer_university_limit:
        universities = universities[:max(0, limit_universities)]

    if (limit_degrees is not None or degree_title_filter) and isinstance(titulaciones_por_univ, dict):
        from phase_common import matches_degree_title
        limited_catalog = {}
        for u_code, u_data in titulaciones_por_univ.items():
            if isinstance(u_data, dict):
                u_data = dict(u_data)
                degs = list(u_data.get("titulaciones_vigentes", []))
                if degree_title_filter:
                    degs = [d for d in degs if matches_degree_title(d.get("titulo"), degree_title_filter)]
                if degree_level_filter:
                    degs = [
                        d for d in degs
                        if matches_academic_level(d.get("titulo"), d.get("nivel_academico"), degree_level_filter)
                    ]
                if limit_degrees is not None:
                    # El límite de una campaña de recuperación debe contar
                    # titulaciones pendientes, no las primeras entradas del
                    # catálogo que ya pueden estar completas y verificadas.
                    # En modo ``force`` todas siguen siendo candidatas, por lo
                    # que se conserva el comportamiento esperado de una
                    # revalidación explícita.
                    pending_degrees = [
                        degree
                        for degree in degs
                        if not is_doctorate_program(
                            degree.get("nivel_academico"), degree.get("titulo")
                        )
                        and needs_web_resolution(
                            find_plan_filepath(
                                str(u_code).zfill(3),
                                str(degree.get("codigo_estudio") or "").strip(),
                            ),
                            force=force,
                        )
                    ]
                    degs = pending_degrees[:max(0, limit_degrees)]
                u_data["titulaciones_vigentes"] = degs
            limited_catalog[u_code] = u_data
        titulaciones_por_univ = limited_catalog

    if limit_universities is not None and defer_university_limit:
        eligible_codes = {
            str(code).zfill(3)
            for code, data in titulaciones_por_univ.items()
            if isinstance(data, dict) and data.get("titulaciones_vigentes")
        }
        universities = [
            university
            for university in universities
            if (
                str(university.get("codigo", "")).zfill(3) in eligible_codes
                and str(
                    university.get("web")
                    or university.get("url")
                    or university.get("web_url")
                    or ""
                ).strip()
            )
        ][:max(0, limit_universities)]

    print(f" -> {len(universities)} universidades a procesar en paralelo con {max_workers} trabajadores.")

    crawler = UniversityWebCrawler(metrics_tracker=metrics_tracker)
    
    total_missing = 0
    total_resolved = 0
    total_source_identity_conflicts = 0
    denied_by_robots = 0
    university_errors = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(crawler.process_university_web, univ, titulaciones_por_univ, force): univ
            for univ in universities
        }

        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            univ = futures[future]
            u_code = str(univ.get("codigo", "")).zfill(3)
            u_name = str(univ.get("nombre", ""))
            try:
                res = future.result() or {}
                u_missing = res.get("missing_degrees_count", 0)
                u_resolved = res.get("resolved_degrees_count", 0)
                total_missing += u_missing
                total_resolved += u_resolved
                total_source_identity_conflicts += res.get("source_identity_conflicts", 0)
                if not res.get("robots_allowed", True):
                    denied_by_robots += 1
                # La salida de consola debe ser segura también en Windows con
                # una página de códigos heredada (p. ej. cp1252). Los
                # símbolos Unicode de estado podían provocar una excepción
                # justo al consolidar el resultado de una universidad.
                print(f"  [OK] [{completed}/{len(universities)}] Universidad [{u_code}] {u_name}: {u_resolved}/{u_missing} planes verificados", flush=True)
            except Exception as exc:
                university_errors += 1
                print(f"  [ERROR] [{completed}/{len(universities)}] [ERROR PARTE 2] Universidad [{u_code}]: {exc}", flush=True)
                crawler.logger.log_error("fase1_parte2_univ_web", univ.get("codigo", "ALL"), univ.get("web", ""), "Excepcion no controlada en escaneo web de universidad", str(exc))
            if progress_emitter is not None:
                progress_emitter.update_university(
                    completed,
                    len(universities),
                    univ.get("codigo", ""),
                    univ.get("nombre", ""),
                    univ.get("tipo", ""),
                )

    # Consolidación atómica de planes interuniversitarios y resoluciones BOE compartidas
    prop_stats = propagate_interuniversity_and_shared_boe_plans()
    try:
        crawler.ledger.reconcile_processing(
            phase_prefix="fase1_parte2",
            reason="intento sin respuesta al cerrar la Parte 2",
        )
        crawler.checkpoint.close()
        crawler.ledger.close()
    except Exception as close_error:
        logger.warning("No se pudieron cerrar los recursos de la Parte 2: %s", close_error, exc_info=True)
    print(f" -> Titulaciones propagadas por BOE/Consorcio: {prop_stats.get('total_propagated', 0)}")

    print("\n" + "=" * 70)
    print("      FASE 1 - PARTE 2 FINALIZADA DE FORMA METICULOSA Y RESPETUOSA")
    print("======================================================================")
    print(f" -> Universidades escaneadas:             {len(universities)}")
    print(f" -> Titulaciones sin plan iniciales:       {total_missing}")
    print(f" -> Titulaciones completadas desde web:    {total_resolved}")
    print(f" -> Titulaciones propagadas interuniv:     {prop_stats.get('total_propagated', 0)}")
    print(f" -> Cancelaciones por robots.txt:         {denied_by_robots}")

    return {
        "status": "partial" if university_errors else "completed",
        "universities_processed": len(universities),
        "university_codes_processed": sorted(
            str(univ.get("codigo", "")).zfill(3)
            for univ in universities
            if univ.get("codigo")
        ),
        "missing_degrees": total_missing,
        "resolved_degrees": total_resolved,
        "source_identity_conflicts": total_source_identity_conflicts,
        "propagated_degrees": prop_stats.get("total_propagated", 0),
        "robots_denied": denied_by_robots,
        "errors": university_errors,
        "persistence": {
            "checkpoint_sqlite": "degraded" if getattr(crawler.checkpoint, "_sqlite_disabled", False) else "ok",
            "crawl_ledger_sqlite": "degraded" if getattr(crawler.ledger, "_disabled", False) else "ok",
        },
    }

if __name__ == "__main__":
    run_phase1_part2()
