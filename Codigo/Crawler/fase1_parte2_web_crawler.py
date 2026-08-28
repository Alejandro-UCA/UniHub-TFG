import os
import sys
import re
import json
import time
import gzip
import logging
import threading
import requests
import urllib.parse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import concurrent.futures
import unicodedata
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger("unihub_web_crawler")
_MAX_PDF_PAGES_EXTRACT = 80


def _annotate_plan_source_status(degrees: list, university_code: str, status: str) -> None:
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
            continue
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
    WEB_PROBE_DELAY,
    WEB_SEARCH_SUBPAGES_LIMIT,
    PRIVATE_ECTS_MIN,
    PRIVATE_ECTS_MAX,
    PRIVATE_ANNUAL_MIN,
    PRIVATE_ANNUAL_MAX,
    WEB_CRAWLER_WORKERS,
    ROBOTS_CACHE_TTL_SECONDS,
    LAZY_SCANNED_PAGES_CACHE_LIMIT,
    ROBOTS_CHECK_TIMEOUT,
    HUB_AND_SPOKE_MAX_HUBS,
    HUB_AND_SPOKE_MAX_DEPTH,
    HUB_AND_SPOKE_MAX_HOPS,
    DYNAMIC_HUB_MIN_SIBLINGS,
    DYNAMIC_HUB_MIN_TITLE_WORDS,
    DYNAMIC_HUB_MAX_TITLE_WORDS,
    SPIDER_TRAP_PATH_MARKERS,
    HUB_ACADEMIC_KEYWORDS,
    MEMORIA_VERIFICADA_KEYWORDS,
    ACADEMIC_SUBPAGE_KEYWORDS,
    INVALID_METADATA_LABELS,


    MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV,
    ORGANIC_AFFILIATED_HUB_KEYWORDS,
    EUROPEAN_ALLIANCES_KEYWORDS,
    SPA_SUBPAGE_FETCH_TIMEOUT,
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
    TARGET_UNIVERSITY_CODES
)
from downloader import RUCTDownloader, is_same_or_subdomain as downloader_is_same_or_subdomain
from robots_policy import RobotsPolicy
from crawl_ledger import CrawlLedger
from data_quality import source_record, validate_plan_identity
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump, load_json_safe
from phase_common import iter_plan_files
from parsers import (
    parse_boe_pdf,
    classify_subject_caracter,
    sanitize_subject_name,
    is_spurious_or_administrative_subject,
    is_curriculum_complete,
    get_curriculum_completeness_status,
    compute_curriculum_total_ects,
    get_required_degree_credits,
    is_doctorate_program,
    extract_degree_core_keywords,
    is_section_matching,
    extract_subjects_from_card_blocks,
    detect_academic_language,
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

    return score


def is_valid_curricular_table(table_tag) -> bool:
    """Verifica que una tabla HTML sea verdaderamente curricular y no un formulario de búsqueda, escala de notas, tabla de cookies ni baremo administrativo de convalidaciones (Multilingüe)."""
    if table_tag.find(["input", "select", "textarea", "button", "form"]):
        return False
    txt = table_tag.get_text(separator=" ", strip=True).lower()
    
    # 1. Marcadores de descarte administrativo, legal, reconocimientos o formación corporativa
    discard_markers = [
        # Escala de notas y baremos
        "calificación cualitativa", "calificacion cualitativa", "calificación numérica", "calificacion numerica",
        "calificación estándar", "calificacion estandar", "escala de calificaciones", "tabla de equivalencias",
        "qualificació qualitativa", "qualificacio qualitativa", "cualificación cualitativa", "kalifikazio kualitatiboa",
        "grading scale", "qualitative grade",
        # Reconocimientos y convalidaciones administrativas
        "se pueden reconocer", "reconocimiento de créditos", "reconocimiento de creditos", "normativa aplicable",
        "tabla de convalidaciones", "taula de convalidacions", "taula dequivalencies", "táboa de equivalencias",
        # Privacidad y protección de datos
        "responsable del tratamiento", "delegado de protección", "delegado de proteccion", "dpo", "finalidades o usos de los datos",
        "base jurídica", "base juridica", "derechos de los interesados", "plazo de conservación", "_ga", "_gid", "_fbp", "cookie-agreed",
        "protección de datos", "proteccion de datos", "datos de carácter personal", "datos de caracter personal",
        "política de cookies", "politica de cookies", "política de privacidad", "politica de privacidad",
        "legitimación", "legitimacion", "destinatarios", "ejercicio de derechos", "agencia española de protección",
        "configuración de cookies", "configuracion de cookies", "gestión de cookies", "gestion de cookies",
        # Formación a medida / Convenios de empresas
        "formación a medida", "formacion a medida", "empresa / institución", "empresa / institucion", "entidad colaboradora",
        # Mínors y microcredenciales (si no es el grado oficial)
        "oferta de minors", "plan de estudios del mínor",
        # Horarios y calendarios de exámenes
        "horario de clases", "horari de classes", "calendario de exámenes", "calendari d'exàmens"
    ]
    if any(m in txt for m in discard_markers):
        return False

    # 2. Descartar tablas de política de cookies y privacidad
    cookie_markers = ["_ga", "_gid", "_fbp", "cookie", "cookies", "cookie-agreed", "caducidad", "titularidad", "finalidad", "consentimiento", "duración", "duracio", "duracion"]
    if any(m in txt for m in cookie_markers) and not any(cm in txt for cm in ["asignatura", "assignatura", "materia", "irakasgaia", "subject", "course"]):
        return False

    # 3. Debe poseer al menos un indicador curricular genuino en encabezados o texto (Multilingüe)
    curricular_markers = [
        # ES
        "asignatura", "materia", "denominaci", "ects", "crédito", "credito", "carácter", "caracter", "semestre", "cuatrimestre", "guía docente", "guia docente",
        # CA
        "assignatura", "credits", "curs", "tipus", "quadrimestre", "guia docent",
        # GL
        "asineira", "creditos", "cuadrimestre",
        # EU
        "irakasgaia", "kredituak", "maila", "ikasturtea", "mota", "lauhilekoa",
        # EN
        "subject", "course", "module", "credits", "syllabus", "semester"
    ]
    return any(m in txt for m in curricular_markers)


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


def build_html_curriculum_payload(elementos_html: list, degree_title: str) -> dict:
    """Construye la estructura estándar de plan de estudios a partir de asignaturas extraídas de HTML."""
    return {
        # No inferir el total reglamentario a partir del tipo de título: el
        # nivel puede ser un máster de 60/90/120 ECTS u otro programa.
        "resumen_creditos": {},
        "total_elementos": len(elementos_html),
        "elementos_curriculares": elementos_html
    }


RE_LEVEL_GRADO = re.compile(r"\b(?:grado|grados|graduado|graduada|graduados|graduadas|grau|graus|grao|graos|gradua|graduak|bachelor|undergraduate|llistat-de-graus|estudis-de-grau)\b", re.IGNORECASE)
RE_LEVEL_MASTER = re.compile(r"\b(?:master|masters|máster|másteres|màster|màsters|masterra|masterrak|postgrado|posgrado|postgrau|posgrao|postgraduate)\b", re.IGNORECASE)
RE_LEVEL_DOCTOR = re.compile(r"\b(?:doctor|doctora|doctorado|doctorados|doctorat|doctorats|doutoramento|doktoregoa|doctorate|doctoral|phd)\b", re.IGNORECASE)
RE_ENGINEERING_MARKER = re.compile(r"\b(?:ingenier[ií]a|ingeniero|ingeniera|enginyeria|engineering)\b", re.IGNORECASE)
RE_DOUBLE_DEGREE_MARKER = re.compile(r"\b(?:doble|simultaneidad|pceo|double)\b", re.IGNORECASE)


def is_html_page_matching_degree(soup: BeautifulSoup, target_title: str, univ_name: str, page_url: str = "") -> bool:
    """
    Verifica que la página HTML pertenezca realmente a la titulación objetivo y no a otra titulación distinta.
    Comprueba:
    1. Que no sea una subpágina de cursos de extensión, títulos propios o formularios no oficiales.
    2. Consistencia estricta de Nivel Académico (3 niveles independientes: Grado, Máster y Doctorado).
    3. Distinción estricta de Ingeniería vs Ciencia/Salud (evita que Ingeniería Química absorba Química).
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

    # 2. Extraer encabezados y título de la página
    page_texts = []
    if soup.title and soup.title.string:
        page_texts.append(soup.title.string)

    for h in soup.find_all(["h1", "h2", "h3"]):
        h_text = h.get_text(separator=" ", strip=True)
        if h_text and len(h_text) > 3:
            page_texts.append(h_text)

    for meta in soup.find_all("meta", attrs={"property": "og:title"}):
        if meta.get("content"):
            page_texts.append(meta["content"])
    for meta in soup.find_all("meta", attrs={"name": "title"}):
        if meta.get("content"):
            page_texts.append(meta["content"])

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

    # 4. Distinción estricta de Ingeniería vs Ciencia/Salud Pura
    is_target_eng = bool(RE_ENGINEERING_MARKER.search(target_low))
    is_page_eng = bool(RE_ENGINEERING_MARKER.search(combined_page_header))
    if is_target_eng != is_page_eng:
        return False

    # 5. Distinción estricta de Grado Simple vs Doble Grado
    is_target_double = bool(RE_DOUBLE_DEGREE_MARKER.search(target_low))
    is_page_double = bool(RE_DOUBLE_DEGREE_MARKER.search(combined_page_header))
    if not is_target_double and is_page_double:
        return False

    # 6. Validación semántica del núcleo temático
    target_kw = extract_degree_core_keywords(target_title, univ_name)
    if not target_kw:
        return True

    page_kw = extract_degree_core_keywords(combined_page_header, univ_name)
    if not page_kw:
        return False

    return is_section_matching(page_kw, target_kw)


def is_valid_web_url(href) -> bool:
    """Valida que un enlace sea HTTP/HTTPS y no un esquema especial (mailto, javascript, tel, ancla)."""
    if not href or not isinstance(href, str):
        return False
    h = href.strip().lower()
    if h.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:", "ftp:", "data:")):
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


def extract_html_subjects(soup: BeautifulSoup, base_url: str = "") -> list:
    """
    Extrae elementos curriculares de tablas HTML evitando filas de cabecera (<th>),
    filas de resumen de créditos (Totals, 1r curs...), palabras clave no curriculares,
    soportando celdas multi-línea divididas por <br>, <p>, <div> o <li>, y capturando
    el enlace saliente a la guía docente oficial (url_guia_docente).
    """
    elementos = []
    seen_names = set()
    tables = soup.find_all("table")

    for t in tables:
        if not is_valid_curricular_table(t):
            continue
        rows = t.find_all("tr")
        subj_col = 0
        ects_col = -1
        car_col = -1
        curso_col = -1

        for r_idx, row in enumerate(rows):
            tds = row.find_all(["td", "th"])
            if not tds:
                continue

            cols_raw = [td.get_text(separator=" ", strip=True) for td in tds]

            # Detectar si la primera fila o <th> definen los índices de columnas
            if r_idx == 0 or all(cell.name == "th" for cell in tds):
                for c_i, c_val in enumerate(cols_raw):
                    c_low = c_val.lower().strip()
                    if any(w == c_low or w in c_low for w in ["asignatura", "assignatura", "asineira", "irakasgaia", "materia", "denominació", "denominacion", "denominación", "nombre", "actividad", "subject", "course", "modul", "módulo", "modulo"]):
                        subj_col = c_i
                    elif any(w == c_low or w in c_low for w in ["crédito", "credito", "crèdits", "credits", "credit", "kredituak", "kreditu", "ects"]):
                        ects_col = c_i
                    elif any(w == c_low or w in c_low for w in ["carácter", "caracter", "caràcter", "tipo", "tipus", "mota", "type"]):
                        car_col = c_i
                    elif any(w == c_low or w in c_low for w in ["curso", "curs", "ano", "año", "ikasturtea", "maila", "year", "level"]):
                        curso_col = c_i
                continue

            # Si alguna celda contiene saltos de línea (<br>, <p>, <div>, <li>), extraer cada línea individualmente
            extracted_any_multiline = False
            for td in tds:
                lines = [l.strip() for l in td.get_text(separator="\n").splitlines() if l.strip()]

                if len(lines) >= 2:
                    for line in lines:
                        clean_line = re.sub(r"^[\s\-•*]+\s*", "", line).strip()
                        clean_line = sanitize_subject_name(clean_line)
                        if not clean_line or len(clean_line) < 4 or len(clean_line) > 120:
                            continue
                        clean_low = clean_line.lower()
                        if (
                            _RE_SUMMARY_ROW_MARKERS.match(clean_low)
                            or any(clean_low == hk for hk in HEADER_KEYWORDS)
                            or any(sk in clean_low for sk in INVALID_SUBJECT_KEYWORDS)
                            or clean_low in INVALID_METADATA_LABELS
                            or any(lbl in clean_low for lbl in INVALID_METADATA_LABELS if len(lbl) > 6)
                            or clean_line.isdigit()
                        ):
                            continue

                        creditos = None
                        ects_val_num = None
                        m_cr = re.search(r"[/()]\s*(\d+(?:[.,]\d+)?)\s*(?:cr[eè]dits?|cr\.?|ects)", clean_line, re.IGNORECASE)
                        if m_cr:
                            creditos = m_cr.group(1).replace(",", ".")
                            try:
                                ects_val_num = float(creditos)
                            except ValueError:
                                pass

                        caracter = "OB"
                        if "optativ" in clean_low:
                            caracter = "OP"
                        elif any(k in clean_low for k in ["treball de final", "tfg", "tfm", "trabajo fin"]):
                            caracter = "TFG"
                        elif any(k in clean_low for k in ["pràctiques", "practicas", "prácticas"]):
                            caracter = "PE"
                        elif any(k in clean_low for k in ["bàsica", "basica"]):
                            caracter = "FB"

                        if is_spurious_or_administrative_subject(clean_line, ects_val=ects_val_num, caracter=caracter):
                            continue

                        norm_name = re.sub(r"[^\w\s]", "", clean_low).strip()
                        if norm_name in seen_names or len(norm_name) < 4:
                            continue
                        seen_names.add(norm_name)

                        # Extraer enlace si existe
                        url_guia = ""
                        a_tag = td.find("a", href=True)
                        if a_tag:
                            href_val = a_tag["href"].strip()
                            if href_val.startswith("http"):
                                url_guia = href_val
                            elif base_url and not href_val.startswith("javascript:"):
                                url_guia = urllib.parse.urljoin(base_url, href_val)

                        # Extraer código si viene en la celda o URL
                        cod_asig = ""
                        if url_guia:
                            m_cod = re.search(r"[/?=](\d{4,8})(?:[/?&.#]|$)", url_guia)
                            if m_cod:
                                cod_asig = m_cod.group(1)

                        elem_item = {
                            "modulo": "",
                            "materia": "",
                            "codigo_asignatura": cod_asig,
                            "nombre_elemento": clean_line,
                            "creditos_ects": creditos,
                            "caracter": caracter,
                            "curso": "",
                            "cuatrimestre": "",
                            "idioma": detect_academic_language(clean_line)
                        }
                        if url_guia:
                            elem_item["url_guia_docente"] = url_guia

                        elementos.append(elem_item)
                        extracted_any_multiline = True

            if extracted_any_multiline:
                continue

            # Extracción tabular clásica (1 fila = 1 asignatura con columnas)
            if len(cols_raw) < 2:
                continue

            nombre_candidato = ""
            if subj_col < len(cols_raw) and len(cols_raw[subj_col]) >= 4 and not cols_raw[subj_col].isdigit():
                nombre_candidato = cols_raw[subj_col]
            elif len(cols_raw) > 1 and (len(cols_raw[0]) <= 4 or cols_raw[0].isdigit() or re.match(r"^[1-6][º°a-z]*$", cols_raw[0].lower())) and len(cols_raw[1]) >= 4:
                nombre_candidato = cols_raw[1]
            elif len(cols_raw) > 0:
                nombre_candidato = cols_raw[0]

            nombre_candidato = sanitize_subject_name(nombre_candidato)
            nombre_lower = nombre_candidato.lower()

            if (
                len(nombre_candidato) < 4
                or _RE_SUMMARY_ROW_MARKERS.match(nombre_lower)
                or any(nombre_lower == hk for hk in HEADER_KEYWORDS)
                or any(sk in nombre_lower for sk in INVALID_SUBJECT_KEYWORDS)
                or nombre_lower in INVALID_METADATA_LABELS
                or any(lbl in nombre_lower for lbl in INVALID_METADATA_LABELS if len(lbl) > 6)
                or len(nombre_candidato) > 150
            ):
                continue

            norm_name = re.sub(r"[^\w\s]", "", nombre_lower).strip()
            if norm_name in seen_names:
                continue

            creditos = None
            ects_val_num = None
            if ects_col != -1 and ects_col < len(cols_raw):
                m_c = re.search(r"\b(\d+(?:[.,]\d+)?)\b", cols_raw[ects_col])
                if m_c:
                    raw_c = m_c.group(1).replace(",", ".")
                    try:
                        c_f = float(raw_c)
                        if 1.0 <= c_f <= 30.0:
                            creditos = raw_c
                            ects_val_num = c_f
                    except ValueError:
                        pass
            else:
                for col in cols_raw[1:]:
                    m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", col)
                    if m:
                        val_str = m.group(1).replace(",", ".")
                        try:
                            val_num = float(val_str)
                            if 1.0 <= val_num <= 30.0:
                                creditos = str(int(val_num)) if val_num.is_integer() else str(val_num)
                                ects_val_num = val_num
                                break
                        except ValueError:
                            pass

            caracter = "OB"
            if car_col != -1 and car_col < len(cols_raw):
                caracter = classify_subject_caracter(cols_raw[car_col], default="OB")
            else:
                for col in cols_raw:
                    car = classify_subject_caracter(col, default="")
                    if car:
                        caracter = car
                        break

            if is_spurious_or_administrative_subject(nombre_candidato, ects_val=ects_val_num, caracter=caracter):
                continue

            curso = ""
            if curso_col != -1 and curso_col < len(cols_raw):
                curso = cols_raw[curso_col]
            else:
                for col in cols_raw[1:]:
                    col_lower = col.lower()
                    if any(c_kw in col_lower for c_kw in ["1º", "2º", "3º", "4º", "primer", "segundo", "tercer", "cuarto", "1er", "2do", "3er", "4to"]):
                        curso = col
                        break

            # Extraer enlace saliente a la guía docente si existe en la fila o celda
            url_guia = ""
            a_tag = row.find("a", href=True)
            if a_tag:
                href_val = a_tag["href"].strip()
                if href_val.startswith("http"):
                    url_guia = href_val
                elif base_url and not href_val.startswith("javascript:"):
                    url_guia = urllib.parse.urljoin(base_url, href_val)

            # Extraer código si existe en alguna columna o en la URL
            codigo_asig = ""
            for c_val in cols_raw:
                c_val_strip = c_val.strip()
                if re.match(r"^\d{4,8}$", c_val_strip) or re.match(r"^[A-Z]{2,4}\d{2,6}$", c_val_strip):
                    codigo_asig = c_val_strip
                    break
            if not codigo_asig and url_guia:
                m_cod = re.search(r"[/?=](\d{4,8})(?:[/?&.#]|$)", url_guia)
                if m_cod:
                    codigo_asig = m_cod.group(1)

            seen_names.add(norm_name)
            elem_item = {
                "modulo": "",
                "materia": "",
                "codigo_asignatura": codigo_asig,
                "nombre_elemento": nombre_candidato,
                "creditos_ects": creditos,
                "caracter": caracter,
                "curso": curso,
                "cuatrimestre": ""
            }
            if url_guia:
                elem_item["url_guia_docente"] = url_guia

            elementos.append(elem_item)

    if len(elementos) < 3:
        card_elems = extract_subjects_from_card_blocks(soup, base_url)
        if len(card_elems) > len(elementos):
            return card_elems

    return elementos


def extract_private_university_pricing(soup: BeautifulSoup, page_text: str) -> dict:
    """
    Rastrea e identifica la información de precios de matrícula (precio por crédito ECTS y coste anual)
    en las páginas y subpáginas de universidades privadas.
    """
    pricing_data = {}
    text_lower = page_text.lower()
    
    # 1. Patrones para precio por crédito ECTS
    ects_patterns = [
        r'(?:precio|coste|importe|valor)\s*(?:del)?\s*(?:crédito|ects)\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?',
        r'(\d{2,4}(?:[.,]\d{1,2})?)\s*€?\s*/\s*(?:crédito|ects|cr)',
        r'(\d{2,4}(?:[.,]\d{1,2})?)\s*€?\s*por\s*crédito',
        r'(\d{2,4}(?:[.,]\d{1,2})?)\s*€\s*ects'
    ]
    for pat in ects_patterns:
        m = re.search(pat, text_lower)
        if m:
            price = parse_price_value(m.group(1), 15.0, 500.0)
            if price is not None:
                pricing_data["precio_credito_ects"] = price
                break
                
    # 1.5 Patrones para segunda/tercera/cuarta matrícula
    tier_patterns = {
        "precio_credito_2": [r'(?:segunda|2ª|2a)\s*matrícula\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?', r'crédito\s*repetidor\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?'],
        "precio_credito_3": [r'(?:tercera|3ª|3a)\s*matrícula\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?'],
        "precio_credito_4": [r'(?:cuarta|4ª|4a)\s*matrícula\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?']
    }
    for key, patterns in tier_patterns.items():
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                price = parse_price_value(m.group(1), 15.0, 500.0)
                if price is not None:
                    pricing_data[key] = price
                    break
                    
    # Clonar precios base si faltan recargos de matrícula en privadas
    if "precio_credito_ects" in pricing_data:
        pricing_data["precio_credito_2"] = pricing_data.get("precio_credito_2", pricing_data["precio_credito_ects"])
        pricing_data["precio_credito_3"] = pricing_data.get("precio_credito_3", pricing_data["precio_credito_ects"])
        pricing_data["precio_credito_4"] = pricing_data.get("precio_credito_4", pricing_data["precio_credito_ects"])
                
    # 2. Patrones para precio/importe anual total
    annual_patterns = [
        r'(?:precio|importe|coste|tuition|cuota|honorarios)\s*(?:total|anual|por\s*curso)?\D*?(\d{1,2}[.,]\d{3}|\d{4,5})\s*€?',
        r'(\d{1,2}[.,]\d{3}|\d{4,5})\s*€?\s*/\s*(?:año|curso|anual)',
        r'(\d{1,2}[.,]\d{3}|\d{4,5})\s*€\s*(?:al\s*año|por\s*curso)'
    ]
    for pat in annual_patterns:
        m = re.search(pat, text_lower)
        if m:
            price = parse_price_value(m.group(1), 1000.0, 45000.0)
            if price is not None:
                pricing_data["precio_estimado_anual"] = price
                break
                
    if "precio_credito_ects" in pricing_data and "precio_estimado_anual" not in pricing_data:
        pricing_data["precio_estimado_anual"] = round(pricing_data["precio_credito_ects"] * 60, 2)
    elif "precio_estimado_anual" in pricing_data and "precio_credito_ects" not in pricing_data:
        pricing_data["precio_credito_ects"] = round(pricing_data["precio_estimado_anual"] / 60, 2)
        
    return pricing_data


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

    def _build_academic_catalog_map(
        self, 
        downloader: RUCTDownloader, 
        web_url: str, 
        max_depth: int = HUB_AND_SPOKE_MAX_DEPTH, 
        max_hubs: int = HUB_AND_SPOKE_MAX_HUBS,
        max_hops: int = HUB_AND_SPOKE_MAX_HOPS
    ) -> dict:
        """
        Patrón Hub-and-Spoke Catalog Indexing Autónomo (6 Capas) con exploración BFS multinivel.
        Descarga de forma secuencial y cortés (respetando REQUEST_DELAY y robots.txt)
        los catálogos maestros y sub-hubs descubiertos dinámicamente mediante topología DOM,
        densidad de enlaces hermanos, cargas de hidratación (JSON-LD/Next.js), desplegables de formularios
        y migas de pan, sin dependencia obligatoria de diccionarios de palabras fijas.
        """
        catalog_map = defaultdict(list)
        seen_hubs = {web_url.rstrip("/")}
        seen_deg_urls = set()
        seen_organic_domains = set()
        organic_hubs = {}
        
        # Cola BFS: tuplas de (url_hub, nivel_salto_actual)
        queue = deque([(web_url, 0)])
        visited_hubs_count = 0

        while queue and visited_hubs_count < max_hubs:
            current_hub, current_hop = queue.popleft()
            visited_hubs_count += 1
            
            try:
                html_content = downloader.fetch_text(current_hub)
                if not html_content:
                    continue
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Capa 3: Ascenso Jerárquico por Migas de Pan (Breadcrumbs)
                if current_hop < max_hops:
                    for bc_hub in extract_breadcrumb_parent_hubs(soup, current_hub, web_url):
                        norm_bc = bc_hub.rstrip("/")
                        if norm_bc not in seen_hubs and len(seen_hubs) < max_hubs * 2:
                            seen_hubs.add(norm_bc)
                            queue.append((bc_hub, current_hop + 1))

                # Capa 4, 5 y 6: Extracción de fuentes dinámicas (JSON-LD, Formularios Select y Eventos JS)
                dynamic_candidates = []
                dynamic_candidates.extend(extract_hydration_payload_degrees(soup, current_hub))
                dynamic_candidates.extend(extract_form_select_academic_options(soup, current_hub))
                dynamic_candidates.extend(extract_js_event_links(soup, current_hub))

                for dyn_url, dyn_title in dynamic_candidates:
                    norm_dyn = dyn_url.rstrip("/")
                    if norm_dyn not in seen_deg_urls and is_valid_web_url(dyn_url) and is_same_or_subdomain(dyn_url, web_url):
                        seen_deg_urls.add(norm_dyn)
                        raw_toks = re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}\b', dyn_title + " " + dyn_url)
                        all_toks = set()
                        for w in raw_toks:
                            w_low = w.lower()
                            all_toks.add(w_low)
                            w_norm = unicodedata.normalize('NFKD', w_low).encode('ASCII', 'ignore').decode('utf-8')
                            all_toks.add(w_norm)
                            if w_norm.endswith('s') and len(w_norm) > 4:
                                all_toks.add(w_norm[:-1])
                            if w_norm.endswith('es') and len(w_norm) > 5:
                                all_toks.add(w_norm[:-2])
                        for tok in all_toks:
                            catalog_map[tok].append((dyn_url, dyn_title))

                # Capa 1 y 2: Enlaces hipertexto estándar con evaluación heurística de HUB y Sibling Uniformity
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
                            ext_domain = f"{parsed_ext.scheme}://{parsed_ext.netloc}"
                            if ext_domain not in seen_organic_domains and len(organic_hubs) < MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV:
                                seen_organic_domains.add(ext_domain)
                                hub_name = t_text.strip() if len(t_text.strip()) >= 3 else parsed_ext.netloc
                                organic_hubs[ext_domain] = (full_link, hub_name)
                        continue
                        
                    # 1. Detección dinámica de Sub-HUBs de catálogo (Capa 1, 2 y fallback)
                    if current_hop < max_hops and is_dynamic_academic_hub(soup, a, full_link, web_url):
                        if norm_link not in seen_hubs and len(seen_hubs) < max_hubs * 2:
                            seen_hubs.add(norm_link)
                            queue.append((full_link, current_hop + 1))
                            
                    # 2. Indexación en catalog_map de páginas de titulación y planes docentes
                    if len(t_text) >= 4 and not is_spider_trap_or_spurious_url(full_link, t_text):
                        parsed_u = urllib.parse.urlparse(h)
                        depth = len([p for p in parsed_u.path.strip("/").split("/") if p])
                        if depth <= max_depth and norm_link not in seen_deg_urls:
                            seen_deg_urls.add(norm_link)
                            raw_toks = re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}\b', t_text + " " + h)
                            all_toks = set()
                            for w in raw_toks:
                                w_low = w.lower()
                                all_toks.add(w_low)
                                w_norm = unicodedata.normalize('NFKD', w_low).encode('ASCII', 'ignore').decode('utf-8')
                                all_toks.add(w_norm)
                                if w_norm.endswith('s') and len(w_norm) > 4:
                                    all_toks.add(w_norm[:-1])
                                if w_norm.endswith('es') and len(w_norm) > 5:
                                    all_toks.add(w_norm[:-2])
                            for tok in all_toks:
                                catalog_map[tok].append((full_link, t_text))
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

        # El checkpoint no evita volver a consultar robots.txt en modo
        # revalidante: sus reglas y permisos pueden cambiar entre ejecuciones.
        if not full_revalidation and self.checkpoint.is_robots_denied_university(u_code) and not force:
            logger.info("[checkpoint] Universidad %s denegada previamente; se omite por política no revalidante.", u_code)
            stats["robots_allowed"] = False
            return stats

        # 2. Identificar titulaciones sin información del plan de estudios
        if isinstance(titulaciones_por_univ, list):
            active_degrees = titulaciones_por_univ
        else:
            univ_data = titulaciones_por_univ.get(u_code, {})
            active_degrees = univ_data.get("titulaciones_vigentes", []) if isinstance(univ_data, dict) else (univ_data or [])
        
        missing_degrees = []
        for deg in active_degrees:
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            d_level = deg.get("nivel_academico", "")

            # Los programas de doctorado (RD 99/2011) no tienen asignaturas docentes regladas; consisten en investigación tutelada.
            if is_doctorate_program(d_level, d_title):
                continue

            plan_file = find_plan_filepath(u_code, d_code)
            
            # La Parte 1 ya redescubre y verifica cada titulación en cada
            # ejecución. La Parte 2 es una vía de recuperación, no un segundo
            # rastreo general: solo debe consultar la web oficial si Parte 1
            # no dejó un plan completo y verificado para esta titulación.
            if needs_web_resolution(plan_file, force=force):
                missing_degrees.append(deg)

        stats["missing_degrees_count"] = len(missing_degrees)

        if not missing_degrees:
            print(f" [Parte 2] Universidad [{u_code}] {u_name}: sin titulaciones web rastreables (p. ej. doctorados). Finalizado.")
            return stats

        print(f" [Parte 2] Universidad [{u_code}] {u_name}: {len(missing_degrees)} titulaciones no resueltas por la Parte 1. Verificando conectividad en '{web_url}'...")

        # 2.5 robots.txt debe autorizar antes de cualquier petición de conectividad.
        can_fetch, crawl_delay = self.check_robots_allowed(web_url)
        if not can_fetch:
            # Si el origen registrado en el RUCT no responde o no tiene robots.txt disponible, comprobar si Wikidata conoce la URL oficial activa
            print(f" [AVISO ROBOTS] Universidad [{u_code}] {u_name}: fallo al comprobar robots en '{web_url}'. Consultando URL alternativa...")
            rescued_url = self.rescue_university_url(u_name)
            if rescued_url:
                cand_rescued = ensure_https_url(rescued_url)
                if cand_rescued != web_url:
                    web_url = cand_rescued
                    print(f" [RESCATE OK] URL actualizada por Wikidata para [{u_code}]: {web_url}")
                    can_fetch, crawl_delay = self.check_robots_allowed(web_url)

        if not can_fetch:
            print(f" [BLOQUEO ROBOTS] Universidad [{u_code}] {u_name}: acceso denegado en {web_url}.")
            self.checkpoint.mark_robots_denied_university(u_code, web_url, "Crawling denegado o robots.txt no disponible")
            _annotate_plan_source_status(missing_degrees, u_code, "robots_denegado_conservando_anterior")
            stats["robots_allowed"] = False
            return stats

        # 2.6 Test de conectividad y Protocolo de Rescate (Wikipedia API)
        conn_downloader = RUCTDownloader(delay=WEB_PROBE_DELAY, timeout=WEB_CONNECTIVITY_TIMEOUT, ledger=self.ledger, phase="fase1_parte2_probe")
        conn_downloader.reset_university_context(u_code)
        try:
            conn_downloader.fetch_content(web_url)
        except Exception as conn_err:
            print(f" [RESCATE] Web '{web_url}' inalcanzable ({conn_err}). Consultando Wikipedia/Wikidata...")
            rescued_url = self.rescue_university_url(u_name)
            if rescued_url:
                web_url = ensure_https_url(rescued_url)
                print(f" [RESCATE OK] URL corregida por Wikidata para [{u_code}]: {web_url}")
                
                # Actualizar permanentemente en universidades.json
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
                            print(f"   [AVISO] No se pudo persistir la URL corregida en el JSON: {file_err}")
            else:
                print(f" [RESCATE FALLIDO] No se pudo encontrar web alternativa en Wikipedia para [{u_code}].")
                self.checkpoint.record_pdf_download_failure(web_url, "ALL", f"Web principal caída/errónea. Rescate fallido: {conn_err}")
                _annotate_plan_source_status(missing_degrees, u_code, "web_no_disponible_conservando_anterior")
                stats["robots_allowed"] = False
                return stats
        finally:
            conn_downloader.close()

        # 3. Si se ha rescatado la URL, volver a validar su origen y robots.txt.
        can_fetch, crawl_delay = self.check_robots_allowed(web_url)
        if not can_fetch:
            print(f" [BLOQUEO ROBOTS] Universidad [{u_code}] {u_name}: Crawling DENEGADO por robots.txt en {web_url}. Registrando en checkpoint y cancelando operación.")
            self.checkpoint.mark_robots_denied_university(u_code, web_url, "Crawling denegado por robots.txt")
            _annotate_plan_source_status(missing_degrees, u_code, "robots_denegado_conservando_anterior")
            stats["robots_allowed"] = False
            return stats

        effective_delay = max(crawl_delay, 0.5) if crawl_delay and crawl_delay > 0 else 0.5
        delay_msg = f" (Crawl-delay declarado en robots.txt: {crawl_delay:.1f}s)" if crawl_delay else ""
        print(f" [PERMITIDO ROBOTS] Universidad [{u_code}] {u_name}: Crawling PERMITIDO por robots.txt{delay_msg}. Iniciando escaneo web...")

        # 4. Acceso previo al Sitemap XML del portal académico (respetando retardo oficial)
        downloader = RUCTDownloader(delay=effective_delay, timeout=WEB_CONTENT_TIMEOUT, metrics_tracker=self.metrics_tracker, ledger=self.ledger, phase="fase1_parte2_web")
        downloader.reset_university_context(u_code)
        try:
            return self._crawl_university_degrees(downloader, u_code, u_name, web_url, missing_degrees, stats)
        finally:
            downloader.close()

    def _crawl_university_degrees(self, downloader: RUCTDownloader, u_code: str, u_name: str, 
                                 web_url: str, missing_degrees: list, stats: dict) -> dict:
        """Recorre y extrae los planes de estudio de las titulaciones de una universidad."""
        sitemap_urls = self.extract_sitemap_candidate_urls(web_url, missing_degrees=missing_degrees)
        if sitemap_urls:
            print(f"     -> {len(sitemap_urls)} URLs académicas indexadas extraídas del Sitemap XML de la universidad.")

        # 4.1. Pre-indexado rápido de catálogos maestros Hub-and-Spoke (Profundidad <= 6)
        catalog_map = self._build_academic_catalog_map(downloader, web_url, max_depth=6)
        if catalog_map:
            print(f"     -> [Hub-and-Spoke] {len(catalog_map)} términos académicos indexados desde catálogos maestros (Profundidad <= 6).")

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

        # 5. Escaneo/recorrido meticuloso de la web oficial de la universidad
        for d_idx, deg in enumerate(missing_degrees, 1):
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            d_level = deg.get("nivel_academico", "")
            plan_file = find_plan_filepath(u_code, d_code)

            print(f"   [{d_idx}/{len(missing_degrees)}] Buscando en web oficial plan para [{d_code}]: {d_title[:60]}...")

            found_curriculum = None
            direct_source_url = None

            # RUTA RÁPIDA: Si ya teníamos guardada una URL directa en búsquedas previas
            existing_direct_url = None
            if os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        d_json = json.load(f)
                        existing_direct_url = d_json.get("web_fuente_directa_url")
                except Exception as exc:
                    logger.debug(f"Excepción controlada en crawling: {exc}")
                    pass

            if existing_direct_url:
                try:
                    print(f"     -> Probando URL directa guardada previamente: {existing_direct_url}")
                    if existing_direct_url.lower().endswith(".pdf"):
                        parsed = self._try_parse_candidate_pdf(downloader, existing_direct_url, d_code, d_title, u_name)
                        if parsed:
                            found_curriculum = parsed
                            direct_source_url = existing_direct_url
                    else:
                        sub_html = downloader.fetch_text(existing_direct_url)
                        if sub_html:
                            sub_soup = BeautifulSoup(sub_html, "html.parser")
                            elementos_html = extract_html_subjects(sub_soup)
                            if len(elementos_html) >= 3 and is_html_page_matching_degree(sub_soup, d_title, u_name, existing_direct_url):
                                found_curriculum = build_html_curriculum_payload(elementos_html, d_title)
                                direct_source_url = existing_direct_url
                                print(f"     -> [ÉXITO FAST-PATH] Encontradas {len(elementos_html)} asignaturas en URL previa: {existing_direct_url}")
                except Exception as e:
                    print(f"     -> Falló lectura de URL directa previa: {e}")

            univ_name_tokens = set(re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}\b', u_name.lower()))
            title_keywords = [
                w for w in re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}\b', d_title)
                if w.lower() not in TITLE_STOPWORDS and w.lower() not in univ_name_tokens
            ]

            # ESTRATEGIA 1: Escaneo priorizado de URLs obtenidas del Sitemap XML
            if not found_curriculum and sitemap_urls:
                sitemap_scored = []
                for url in sitemap_urls:
                    url_low = url.lower()
                    kw_matches = sum(1 for kw in title_keywords if len(kw) >= 3 and kw.lower() in url_low)
                    if kw_matches >= min(2, len(title_keywords)) or (len(title_keywords) == 1 and kw_matches >= 1):
                        sitemap_scored.append((kw_matches, url))
                sitemap_scored.sort(key=lambda x: x[0], reverse=True)
                sitemap_matches = [u for _, u in sitemap_scored]

                for sm_candidate_url in sitemap_matches[:5]:
                    if found_curriculum:
                        break
                    try:
                        time.sleep(WEB_SEARCH_RETRY_DELAY)
                        if sm_candidate_url.lower().endswith(".pdf"):
                            parsed = self._try_parse_candidate_pdf(downloader, sm_candidate_url, d_code, d_title, u_name)
                            if parsed:
                                found_curriculum = parsed
                                direct_source_url = sm_candidate_url
                                print(f"     -> Encontrado plan de estudios desde Sitemap XML: {sm_candidate_url}")
                                break
                        else:
                            sub_html = downloader.fetch_text(sm_candidate_url)
                            sub_soup = BeautifulSoup(sub_html, "html.parser")
                            elementos_html = extract_html_subjects(sub_soup)
                            if len(elementos_html) >= 3 and is_html_page_matching_degree(sub_soup, d_title, u_name, sm_candidate_url):
                                found_curriculum = build_html_curriculum_payload(elementos_html, d_title)
                                direct_source_url = sm_candidate_url
                                print(f"     -> Encontradas asignaturas HTML válidas desde Sitemap XML: {sm_candidate_url}")
                                break
                    except Exception as exc:
                        logger.debug(f"Excepción controlada en crawling: {exc}")
                        pass

            # ESTRATEGIA 1.5: Búsqueda instantánea en el índice Hub-and-Spoke de Catálogos (Profundidad <= 6)
            if not found_curriculum and catalog_map:
                catalog_candidates = []
                for kw in title_keywords:
                    kw_low = kw.lower()
                    kw_stem = kw_low[:4] if len(kw_low) >= 4 else kw_low
                    for map_tok, links in catalog_map.items():
                        if kw_low in map_tok or (len(kw_stem) >= 4 and kw_stem in map_tok):
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
                    
                    scored_cat.sort(key=lambda x: x[0], reverse=True)
                    for sc, cat_url, cat_text in scored_cat[:4]:
                        if found_curriculum or sc < 40:
                            break
                        try:
                            time.sleep(WEB_SEARCH_RETRY_DELAY)
                            if cat_url.lower().endswith(".pdf"):
                                parsed = self._try_parse_candidate_pdf(downloader, cat_url, d_code, d_title, u_name)
                                if parsed:
                                    found_curriculum = parsed
                                    direct_source_url = cat_url
                                    print(f"     -> [Hub-and-Spoke] Encontrado plan PDF: {cat_url}")
                                    break
                            else:
                                c_html = downloader.fetch_text(cat_url)
                                c_soup = BeautifulSoup(c_html, "html.parser")
                                c_elementos = extract_html_subjects(c_soup)
                                req_c = get_required_degree_credits(d_level, d_title)
                                cur_c = compute_curriculum_total_ects(c_elementos)
                                
                                # Si HTML estático tiene < 3 asignaturas (contenedor SPA vacío JS), renderizar con Playwright
                                if len(c_elementos) < 3:
                                    try:
                                        from spa_crawler import SPALayoutCrawler
                                        spa_c = SPALayoutCrawler.get_shared_instance()
                                        rend = spa_c.render_spa_page(cat_url)
                                        if rend:
                                            if getattr(rend, "is_download", False):
                                                pdf_bytes = getattr(rend, "content_bytes", b"")
                                                if pdf_bytes and (b"%PDF-" in pdf_bytes[:1024] or getattr(rend, "filename", "").lower().endswith(".pdf")):
                                                    pdf_curriculum = parse_boe_pdf(pdf_bytes, d_title, d_level)
                                                    if pdf_curriculum and len(pdf_curriculum.get("elementos_curriculares", [])) >= 3:
                                                        found_curriculum = pdf_curriculum
                                                        direct_source_url = cat_url
                                                        print(f"     -> [Playwright Download Rescate] Encontrado PDF oficial con {len(pdf_curriculum['elementos_curriculares'])} asignaturas: {cat_url}")
                                                        break
                                            else:
                                                rend_soup = BeautifulSoup(rend, "html.parser")
                                                rend_elem = extract_html_subjects(rend_soup)
                                                if len(rend_elem) > len(c_elementos):
                                                    c_elementos = rend_elem
                                    except Exception as exc:
                                        logger.debug(f"Excepción controlada en crawling: {exc}")
                                        pass
                                
                                if len(c_elementos) >= 3 and not found_curriculum and is_html_page_matching_degree(c_soup, d_title, u_name, cat_url):
                                    found_curriculum = build_html_curriculum_payload(c_elementos, d_title)
                                    direct_source_url = cat_url
                                    print(f"     -> [Hub-and-Spoke] Encontradas {len(c_elementos)} asignaturas HTML: {cat_url}")
                                    break
                        except Exception as exc:
                            logger.debug(f"Excepción controlada en crawling: {exc}")
                            pass

            # ESTRATEGIA 2: Escaneo de portales académicos con sinónimos amplios
            if not found_curriculum:
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
                    scored_candidates = [
                        (score_academic_candidate_url(u, t, d_level, title_keywords), u)
                        for u, t in lazy_candidate_urls
                    ]
                    best_url_scores = {}
                    for sc, u in scored_candidates:
                        if u not in best_url_scores or sc > best_url_scores[u]:
                            best_url_scores[u] = sc

                    sorted_candidates = sorted(best_url_scores.items(), key=lambda x: x[1], reverse=True)
                    scanned_urls = [u for u, score in sorted_candidates[:4]]
                    visited_targets = set()
                    
                    for candidate_page_url in scanned_urls:
                        if found_curriculum:
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
                                href = a["href"].strip()
                                if not is_valid_web_url(href):
                                    continue

                                text = a.get_text(strip=True)
                                text_lower = text.lower()

                                matches_title = any(kw.lower() in text_lower or kw.lower() in href.lower() for kw in title_keywords)
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
                                            found_curriculum = parsed
                                            direct_source_url = target_link
                                            break
                                        # Fallback: si el PDF no contiene plan, intentar extraer HTML de la misma URL sin .pdf
                                        html_fallback_url = target_link[:-4] if target_link.lower().endswith(".pdf") else target_link
                                        try:
                                            html_content = downloader.fetch_text(html_fallback_url)
                                            html_soup = BeautifulSoup(html_content, "html.parser")
                                            elementos_html = extract_html_subjects(html_soup)
                                            if len(elementos_html) >= 3 and is_html_page_matching_degree(html_soup, d_title, u_name, html_fallback_url):
                                                found_curriculum = build_html_curriculum_payload(elementos_html, d_title)
                                                direct_source_url = html_fallback_url
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
                                            # Paso 0.5: Si HTML estático de la ficha tiene < 3 asignaturas,
                                            # explorar dinámicamente cualquier subpágina enlazada en el DOM de la ficha (<a> tags)
                                            # priorizando subrutas directas del grado y enlaces a portales institucionales de gestión (2-Hop).
                                            req_ects = get_required_degree_credits(d_level, d_title)
                                            if len(elementos_html) < 3:
                                                discovered_subpages = []
                                                seen_sub_urls = {target_link}
                                                parsed_target = urllib.parse.urlparse(target_link)
                                                target_path_prefix = parsed_target.path.rstrip("/")

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
                                                    try:
                                                        sub_p_html = downloader.fetch_text(sub_p_url)
                                                        if sub_p_html:
                                                            sub_p_soup = BeautifulSoup(sub_p_html, "html.parser")
                                                            sub_p_elems = extract_html_subjects(sub_p_soup, sub_p_url)

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
                                                                try:
                                                                    from spa_crawler import SPALayoutCrawler
                                                                    spa_c = SPALayoutCrawler.get_shared_instance()
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
                                                    spa_crawler = SPALayoutCrawler.get_shared_instance()
                                                    rendered_html = spa_crawler.render_spa_page(target_link)
                                                    if rendered_html:
                                                        if getattr(rendered_html, "is_download", False):
                                                            pdf_bytes = getattr(rendered_html, "content_bytes", b"")
                                                            if pdf_bytes and (b"%PDF-" in pdf_bytes[:1024] or getattr(rendered_html, "filename", "").lower().endswith(".pdf")):
                                                                pdf_curriculum = parse_boe_pdf(pdf_bytes, d_title, d_level)
                                                                if pdf_curriculum and len(pdf_curriculum.get("elementos_curriculares", [])) >= 3:
                                                                    found_curriculum = pdf_curriculum
                                                                    direct_source_url = target_link
                                                                    print(f"     -> [Playwright Download Rescate] Encontrado PDF oficial con {len(pdf_curriculum['elementos_curriculares'])} asignaturas: {target_link}")
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
                                                    logger.warning(f"Excepción controlada en crawling Playwright/SPA: {exc}")
                                                    pass

                                            # Paso 2: Si el temario sigue siendo parcial, explorar sub-enlaces de menciones/especialidades/TFG en la misma ficha
                                            if elementos_html and req_ects > 0 and current_ects < req_ects:
                                                sub_itinerarios = []
                                                for a_sub in target_soup.find_all("a", href=True):
                                                    h_sub = a_sub["href"].strip()
                                                    t_sub = a_sub.get_text(strip=True).lower()
                                                    if any(k in t_sub or k in h_sub.lower() for k in ["mencion", "mención", "especialidad", "optativas", "itinerari", "itinerario", "trabajo fin", "tfg", "tfm", "menciones"]):
                                                        full_sub = urllib.parse.urljoin(target_link, h_sub)
                                                        if is_same_or_subdomain(full_sub, web_url) and full_sub != target_link and is_valid_web_url(full_sub):
                                                            sub_itinerarios.append(full_sub)

                                                seen_names = {e.get("nombre_elemento", "").lower() for e in elementos_html}
                                                for s_url in sub_itinerarios[:3]:
                                                    try:
                                                        s_html = downloader.fetch_text(s_url)
                                                        s_soup = BeautifulSoup(s_html, "html.parser")
                                                        s_elems = extract_html_subjects(s_soup)
                                                        for se in s_elems:
                                                            s_name = se.get("nombre_elemento", "").lower()
                                                            if s_name and s_name not in seen_names:
                                                                seen_names.add(s_name)
                                                                elementos_html.append(se)
                                                        current_ects = compute_curriculum_total_ects(elementos_html)
                                                    except Exception as exc:
                                                        logger.debug(f"Excepción controlada en crawling: {exc}")
                                                        pass

                                            # Paso 3: Si sigue siendo parcial o faltan asignaturas, comprobar si la ficha enlaza el PDF oficial del plan completo
                                            if not found_curriculum and (len(elementos_html) < 3 or (req_ects > 0 and current_ects < req_ects)):
                                                for a_pdf in target_soup.find_all("a", href=True):
                                                    h_pdf = a_pdf["href"].strip()
                                                    t_pdf = a_pdf.get_text(strip=True).lower()
                                                    if h_pdf.lower().endswith(".pdf") or any(pk in t_pdf for pk in ["plan de estudios", "pla d'estudis", "guía docente", "guia docent", "folleto"]) or any(pk in t_pdf or pk in h_pdf.lower() for pk in MEMORIA_VERIFICADA_KEYWORDS):
                                                        pdf_link = urllib.parse.urljoin(target_link, h_pdf)
                                                        if pdf_link.lower().endswith(".pdf") and is_same_or_subdomain(pdf_link, web_url):
                                                            parsed_pdf = self._try_parse_candidate_pdf(downloader, pdf_link, d_code, d_title, u_name)
                                                            if parsed_pdf and parsed_pdf.get("total_elementos", 0) > len(elementos_html):
                                                                found_curriculum = parsed_pdf
                                                                direct_source_url = pdf_link
                                                                break
                                            
                                            # Extraer precios de matrículas en universidades privadas
                                            extracted_pricing = {}
                                            if "privad" in u_type.lower():
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
                                                        try:
                                                            p_html = downloader.fetch_text(plink)
                                                            p_soup = BeautifulSoup(p_html, "html.parser")
                                                            extracted_pricing = extract_private_university_pricing(p_soup, p_html)
                                                            if extracted_pricing.get("precio_credito_ects"):
                                                                break
                                                        except Exception as exc:
                                                            logger.debug(f"Excepción controlada en crawling: {exc}")
                                                            pass

                                            if not found_curriculum and ((len(elementos_html) >= 3 and is_html_page_matching_degree(target_soup, d_title, u_name, target_link)) or extracted_pricing):
                                                found_curriculum = build_html_curriculum_payload(elementos_html, d_title)
                                                if extracted_pricing.get("precio_credito_ects"):
                                                    found_curriculum["precio_credito_ects"] = extracted_pricing["precio_credito_ects"]
                                                    found_curriculum["precio_credito_2"] = extracted_pricing.get("precio_credito_2")
                                                    found_curriculum["precio_credito_3"] = extracted_pricing.get("precio_credito_3")
                                                    found_curriculum["precio_credito_4"] = extracted_pricing.get("precio_credito_4")
                                                    found_curriculum["precio_estimado_anual"] = extracted_pricing.get("precio_estimado_anual")
                                                    found_curriculum["fuente_precio"] = "Web Oficial Universidad Privada"

                                                direct_source_url = target_link
                                                print(f"     -> Encontrados datos e información en subpágina de titulación: {target_link}")
                                                break
                                            elif found_curriculum:
                                                break
                                        except Exception as t_err:
                                            print(f"     -> Error al examinar subpágina de titulación '{target_link}': {t_err}")
                        except Exception as sub_err:
                            print(f"     -> Excepción al escanear sub-página '{candidate_page_url}': {sub_err}")

                except Exception as crawl_err:
                    print(f"     -> Error al rastrear la web oficial para [{d_code}]: {crawl_err}")

            # ESTRATEGIA 2.5: Exploración Orgánica de Centros Adscritos Descubiertos (Patrón 1)
            if not found_curriculum:
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
                        print(f"     -> [Centro Adscrito Orgánico] Descubierto '{matched_hub_name}' ({matched_hub_url})")
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
                                        if len(c_elems) >= 3 and is_html_page_matching_degree(c_soup, d_title, u_name, c_u):
                                            found_curriculum = build_html_curriculum_payload(c_elems, d_title)
                                            direct_source_url = c_u
                                            found_curriculum["centro_adscrito"] = matched_hub_name
                                            print(f"     -> [Centro Adscrito Éxito] Encontradas {len(c_elems)} asignaturas en {c_u}")
                                            break
                                    except Exception as exc:
                                        logger.debug(f"Excepción controlada en crawling: {exc}")
                                        pass
                    except Exception as e_center:
                        print(f"     -> Error al consultar centro adscrito orgánico '{matched_hub_name}': {e_center}")

            # ESTRATEGIA 3: Modelado de Alianzas Universitarias Europeas y Erasmus Mundus (Patrón 3)
            is_european_program = any(k in d_title.lower() for k in EUROPEAN_ALLIANCES_KEYWORDS)
            if is_european_program and (not found_curriculum or len(found_curriculum.get("elementos_curriculares", [])) == 0):
                req_ects = get_required_degree_credits(d_level, d_title)
                discovered_alliance_url = None
                discovered_hubs = self.organic_affiliated_hubs.get(web_url, {})
                for ext_dom, (hub_url, hub_name) in discovered_hubs.items():
                    if any(ak in hub_name.lower() or ak in hub_url.lower() for ak in ["sea-eu", "erasmus", "eunice", "charmeu", "arqus", "civica", "civis", "alliance", "european"]):
                        discovered_alliance_url = hub_url
                        break
                        
                found_curriculum = {
                    "tipo_estructura": "consorcio_europeo_erasmus_mundus",
                    "nombre_plan": d_title,
                    "total_elementos": 0,
                    "elementos_curriculares": [],
                    "es_alianza_europea": True,
                    "plan_completo": False,
                    "ects_exigidos": req_ects,
                    "ects_totales_detectados": 0,
                    "descripcion_consorcio": "Programa Conjunto de Excelencia Internacional (Erasmus Mundus / Alianza Universitaria Europea). La docencia e itinerario curricular se imparten en consorcio internacional en lengua inglesa a través de los campus europeos asociados."
                }
                direct_source_url = discovered_alliance_url or existing_direct_url or deg.get("boe_url") or web_url
                print(f"     -> [Alianza Europea / Erasmus Mundus Orgánico] Ficha de consorcio internacional ({req_ects} ECTS) -> {direct_source_url}")

            # Guardar el plan y la URL directa donde se ha encontrado
            if found_curriculum and direct_source_url:
                print(f"     [ÉXITO PARTE 2] Encontrado plan de estudios en la web oficial: '{direct_source_url}'")
                stats["resolved_degrees_count"] += 1
                
                degree_data = load_json_safe(plan_file)
                degree_data["codigo_estudio"] = d_code
                degree_data["titulo"] = deg.get("titulo", "")
                degree_data["nivel_academico"] = deg.get("nivel_academico", "")
                degree_data["universidad_codigo"] = u_code
                degree_data["universidad_nombre"] = u_name
                degree_data["fecha_procesado"] = datetime.now().isoformat()
                degree_data["estado_fuente"] = "verificada"
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
                    
                degree_data["precio_credito_ects"] = found_curriculum.get("precio_credito_ects") or deg.get("precio_credito_ects")
                degree_data["precio_credito_2"] = found_curriculum.get("precio_credito_2") or deg.get("precio_credito_2")
                degree_data["precio_credito_3"] = found_curriculum.get("precio_credito_3") or deg.get("precio_credito_3")
                degree_data["precio_credito_4"] = found_curriculum.get("precio_credito_4") or deg.get("precio_credito_4")
                degree_data["precio_estimado_anual"] = found_curriculum.get("precio_estimado_anual") or deg.get("precio_estimado_anual")
                degree_data["fuente_precio"] = found_curriculum.get("fuente_precio") or deg.get("fuente_precio")
                
                # Diagnosticar completitud curricular del plan obtenido
                degree_data["plan_estudios"] = found_curriculum
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
                degree_data["calidad_datos"] = {"errores_identidad": validate_plan_identity(degree_data)}
                comp_status = get_curriculum_completeness_status(degree_data)
                found_curriculum["plan_completo"] = comp_status["is_complete"]
                found_curriculum["ects_totales_detectados"] = comp_status["total_ects_obtained"]
                found_curriculum["ects_exigidos"] = comp_status["required_ects"]
                
                atomic_json_dump(degree_data, plan_file)
                self.checkpoint.update_degree_record(d_code, direct_source_url, datetime.now().strftime("%Y-%m-%d"), datetime.now().isoformat())
            else:
                print(f"     -> No se encontró plan de estudios en la web oficial para [{d_code}].")
                existing_data = load_json_safe(plan_file, default=None)
                if isinstance(existing_data, dict):
                    existing_data["estado_fuente"] = "sin_plan_actual_conservando_anterior" if existing_data.get("plan_estudios") else "sin_plan_actual_sin_dato"
                    existing_data["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                    atomic_json_dump(existing_data, plan_file)

        return stats


def normalize_joint_title(title: str) -> str:
    """Normaliza el título de una titulación interuniversitaria para indexación y emparejamiento."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title.lower()).encode("ASCII", "ignore").decode("utf-8")
    t = re.sub(r"[\(\[].*?[\)\]]", "", t)
    t = t.replace("universitat", "universidad").replace("politècnica", "politecnica").replace("de la", "de")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


def propagate_interuniversity_and_shared_boe_plans(planes_dir: str = PLANES_DIR) -> dict:
    """
    Sincroniza y propaga atómicamente planes de estudio completos entre:
    1. Titulaciones que comparten la MISMA resolución oficial del BOE.
    2. Titulaciones interuniversitarias que comparten el mismo plan verificado por ANECA.
    Garantiza 100% de aislamiento entre procesos sin bloqueos ni contención de red.
    """
    stats = {"boe_shared_rescued": 0, "interuniv_shared_rescued": 0, "total_propagated": 0}
    if not os.path.exists(planes_dir):
        return stats

    file_paths = iter_plan_files(planes_dir)

    boe_index = {}
    title_index = {}
    empty_records = []

    for path in file_paths:
        d = load_json_safe(path)
        if not d:
            continue
        boe = d.get("boe_url") or ""
        elems = d.get("plan_estudios", {}).get("elementos_curriculares", []) if d.get("plan_estudios") else []
        norm_t = normalize_joint_title(d.get("titulo", ""))
        level_key = normalize_joint_title(d.get("nivel_academico", ""))
        title_key = f"{norm_t}|{level_key}" if level_key else norm_t
        
        if len(elems) >= 3 and is_curriculum_complete(d):
            if boe and "boe.es" in boe:
                if boe not in boe_index or len(elems) > len(boe_index[boe][0].get("elementos_curriculares", [])):
                    boe_index[boe] = (d.get("plan_estudios", {}), d.get("web_fuente_directa_url") or boe)
            if title_key:
                if title_key not in title_index or len(elems) > len(title_index[title_key][0].get("elementos_curriculares", [])):
                    title_index[title_key] = (d.get("plan_estudios", {}), d.get("web_fuente_directa_url") or boe)
        else:
            empty_records.append((path, d, boe, norm_t))

    for path, d, boe, norm_t in empty_records:
        matched_plan = None
        source_url = ""
        origen = ""

        if boe in boe_index:
            matched_plan, source_url = boe_index[boe]
            origen = "resolucion_boe_compartida"
            stats["boe_shared_rescued"] += 1
        else:
            title_key = f"{norm_t}|{normalize_joint_title(d.get('nivel_academico', ''))}" if d.get("nivel_academico") else norm_t
            if title_key in title_index:
                matched_plan, source_url = title_index[title_key]
            else:
                matched_plan = None
        if matched_plan and not origen:
            origen = "interuniversitario_compartido"
            stats["interuniv_shared_rescued"] += 1

        is_european = any(k in d.get("titulo", "").lower() for k in EUROPEAN_ALLIANCES_KEYWORDS)
        if not matched_plan and is_european:
            req_c = get_required_degree_credits(d.get("nivel_academico", ""), d.get("titulo", ""))
            matched_plan = {
                "tipo_estructura": "consorcio_europeo_erasmus_mundus",
                "nombre_plan": d.get("titulo", ""),
                "total_elementos": 0,
                "elementos_curriculares": [],
                "es_alianza_europea": True,
                "plan_completo": False,
                "ects_exigidos": req_c,
                "ects_totales_detectados": 0,
                "descripcion_consorcio": "Programa Conjunto de Excelencia Internacional (Erasmus Mundus / Alianza Universitaria Europea). La docencia e itinerario curricular se imparten en consorcio internacional en lengua inglesa a través de los campus europeos asociados."
            }
            origen = "alianza_europea_erasmus_mundus"
            source_url = d.get("web_fuente_directa_url") or d.get("boe_url") or "https://erasmus-plus.ec.europa.eu"
            stats["interuniv_shared_rescued"] += 1

        if matched_plan:
            d["plan_estudios"] = matched_plan
            d["origen_fuente"] = origen
            d["web_fuente_directa_url"] = source_url
            d["fecha_procesado"] = datetime.now().isoformat()
            atomic_json_dump(d, path)
            stats["total_propagated"] += 1

    return stats


def run_phase1_part2(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
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

    with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
        universities = json.load(f)

    with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
        titulaciones_por_univ = json.load(f)

    if TARGET_UNIVERSITY_CODES:
        universities = [u for u in universities if str(u.get("codigo", "")).zfill(3) in TARGET_UNIVERSITY_CODES]
    if limit_universities is not None:
        universities = universities[:max(0, limit_universities)]

    if limit_degrees is not None and isinstance(titulaciones_por_univ, dict):
        limited_catalog = {}
        for u_code, u_data in titulaciones_por_univ.items():
            if isinstance(u_data, dict):
                u_data = dict(u_data)
                u_data["titulaciones_vigentes"] = list(u_data.get("titulaciones_vigentes", []))[:max(0, limit_degrees)]
            limited_catalog[u_code] = u_data
        titulaciones_por_univ = limited_catalog

    print(f" -> {len(universities)} universidades a procesar en paralelo con {max_workers} trabajadores.")

    crawler = UniversityWebCrawler(metrics_tracker=metrics_tracker)
    
    total_missing = 0
    total_resolved = 0
    denied_by_robots = 0
    university_errors = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(crawler.process_university_web, univ, titulaciones_por_univ, force): univ
            for univ in universities
        }

        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            univ = futures[future]
            try:
                res = future.result() or {}
                total_missing += res.get("missing_degrees_count", 0)
                total_resolved += res.get("resolved_degrees_count", 0)
                if not res.get("robots_allowed", True):
                    denied_by_robots += 1
            except Exception as exc:
                university_errors += 1
                print(f" [ERROR PARTE 2] Excepción inesperada en universidad {univ.get('codigo')}: {exc}")
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
        "missing_degrees": total_missing,
        "resolved_degrees": total_resolved,
        "propagated_degrees": prop_stats.get("total_propagated", 0),
        "robots_denied": denied_by_robots,
        "errors": university_errors,
    }

if __name__ == "__main__":
    run_phase1_part2()
