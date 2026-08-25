import os
import sys
import re
import io
import json
import time
import sqlite3
import hashlib
import logging
import unicodedata
from urllib.parse import urljoin, urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import pypdf

from config import (
    PLANES_DIR,
    DATA_DIR,
    USER_AGENT,
    REQUEST_DELAY,
    ASYNC_PREFETCH_WORKERS
)
from downloader import RUCTDownloader, SkipUniversityException, normalize_url
from checkpoint import atomic_json_dump
from parsers import sanitize_subject_name, classify_subject_caracter
from univ_web_crawler import is_spurious_or_administrative_subject

logger = logging.getLogger(__name__)

CACHE_GUIAS_DB = os.path.join(DATA_DIR, "cache_guias_docentes.db")


class SubjectGuideCache:
    """
    Gestor de persistencia en SQLite WAL para guías docentes.
    Garantiza deduplicación institucional (N:M): asignaturas compartidas entre grados
    (ej. Cálculo de la UCA o Álgebra en la UAH) se descargan y analizan exactamente UNA sola vez.
    Permite búsqueda dual tanto por URL exacta como por clave compuesta canónica (universidad_codigo + codigo_asignatura).
    """
    def __init__(self, db_path: str = CACHE_GUIAS_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guias_docentes (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    universidad_codigo TEXT,
                    codigo_asignatura TEXT,
                    nombre TEXT,
                    datos_json TEXT NOT NULL,
                    fecha_extraccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_guias_url ON guias_docentes(url);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_guias_univ_asig ON guias_docentes(universidad_codigo, codigo_asignatura);")
            conn.commit()

    def get(self, url: str = None, u_code: str = None, asig_code: str = None) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if url:
                    url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
                    cursor.execute("SELECT datos_json FROM guias_docentes WHERE url_hash = ?", (url_hash,))
                    row = cursor.fetchone()
                    if row:
                        return json.loads(row[0])

                if u_code and asig_code:
                    cursor.execute(
                        "SELECT datos_json FROM guias_docentes WHERE universidad_codigo = ? AND codigo_asignatura = ? ORDER BY fecha_extraccion DESC LIMIT 1",
                        (str(u_code).zfill(3), str(asig_code).strip())
                    )
                    row = cursor.fetchone()
                    if row:
                        return json.loads(row[0])
        except Exception as e:
            logger.warning(f"Error al leer caché de guía docente: {e}")
        return None

    def set(self, url: str, data: dict, u_code: str = "", asig_code: str = "", nombre: str = ""):
        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO guias_docentes 
                    (url_hash, url, universidad_codigo, codigo_asignatura, nombre, datos_json, fecha_extraccion)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (url_hash, url, str(u_code).zfill(3) if u_code else "", str(asig_code).strip() if asig_code else "", nombre, json.dumps(data, ensure_ascii=False)))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error al escribir caché de guía docente: {e}")


# =============================================================================
# MOTOR UNIVERSAL DE RESOLUCIÓN CANÓNICA DE GUÍAS DOCENTES (FAST-PATH)
# =============================================================================

def generate_subject_slug(name: str) -> str:
    """Genera un slug limpio y normalizado (sin tildes, con guiones) para rutas URL."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"[^\w\s-]", "", ascii_text).strip()
    return re.sub(r"[\s_]+", "-", clean)


def resolve_candidate_subject_guide_urls(
    elem: dict, 
    u_code: str, 
    u_web: str = "", 
    d_code: str = "",
    academic_year: str = "2025-26"
) -> list:
    """
    Generador universal de URLs candidatas para guías docentes del EEES.
    Combina URLs explícitas ya extraídas con patrones institucionales generalizados.
    """
    candidates = []
    seen = set()

    def _add_url(u: str):
        if not u:
            return
        norm = normalize_url(u)
        if norm and norm not in seen and norm.startswith("http"):
            seen.add(norm)
            candidates.append(norm)

    # 1. URL explícita ya detectada en el plan web o BOE
    url_directa = elem.get("url_guia_docente")
    if url_directa:
        _add_url(url_directa)

    asig_code = elem.get("codigo_asignatura") or elem.get("codigo")
    asig_nombre = elem.get("nombre_elemento", "")
    slug = generate_subject_slug(asig_nombre)

    # Inferir código numérico de asignatura si está embebido en el nombre
    if not asig_code:
        m_code = re.match(r"^(\d{4,8})\s*[-–_:]\s*(.+)$", asig_nombre)
        if m_code:
            asig_code = m_code.group(1)
            asig_nombre = m_code.group(2).strip()

    u_code_padded = str(u_code).zfill(3)

    # 2. Patrones Generales del Sistema Universitario Español (SUE)
    parsed_domain = urlparse(u_web).netloc.lower() if u_web else ""
    if not parsed_domain:
        DOMAIN_BY_UCODE = {
            "025": "uca.es", "002": "uah.es", "003": "ua.es", "009": "ucm.es",
            "010": "uam.es", "011": "upm.es", "012": "uc3m.es", "014": "uva.es",
            "015": "usal.es", "017": "us.es", "018": "uma.es", "019": "ugr.es",
            "020": "uco.es", "024": "uv.es", "026": "uab.cat", "029": "upc.edu",
            "030": "udg.edu", "031": "udl.cat", "032": "urv.cat", "033": "upf.edu",
            "034": "unex.es", "035": "udc.es", "036": "usc.es", "037": "uvigo.gal",
            "038": "uniovi.es", "039": "unican.es", "040": "unirioja.es", "041": "unavarra.es",
            "042": "ehu.eus", "043": "unav.edu", "050": "nebrija.com", "051": "universidadeuropea.com"
        }
        domain = DOMAIN_BY_UCODE.get(u_code_padded, "")
    else:
        domain = parsed_domain

    if domain:
        # Patrón General A: Portal centralizado de programas docentes
        if asig_code:
            _add_url(f"https://asignaturas.{domain}/{academic_year}/{asig_code}")
            _add_url(f"https://guias.{domain}/{academic_year}/{asig_code}")
            _add_url(f"https://secretaria.{domain}/docencia/guia/{asig_code}")
            _add_url(f"https://cv1.cpd.{domain}/ConsPlanesEstudio/cvFichaAsigRedir.asp?asig={asig_code}")

        # Patrón General B: Portal de estudios por slug y código
        if slug and asig_code:
            _add_url(f"https://www.{domain}/es/estudios/estudios-oficiales/grados/asignatura/{slug}-{asig_code}/")
            _add_url(f"https://www.{domain}/estudios/asignatura/{slug}-{asig_code}/")

        # Patrón General C: Repositorio de descargas PDF oficiales de facultad
        if asig_code and d_code:
            _add_url(f"https://www.{domain}/shared/es/estudios/estudios-oficiales/grados/.galleries/Programs-En/{asig_code}_{d_code}_{academic_year}_en.pdf")
            _add_url(f"https://www.{domain}/shared/es/estudios/estudios-oficiales/grados/.galleries/Programs-Es/{asig_code}_{d_code}_{academic_year}_es.pdf")
            _add_url(f"https://www.{domain}/descargas/guias/{asig_code}.pdf")

    return candidates


# =============================================================================
# PARSERS ESPECIALIZADOS DE GUÍAS DOCENTES (HTML & PDF STREAM IN-RAM)
# =============================================================================

def parse_uca_subject_guide(soup: BeautifulSoup, url: str) -> dict:
    """
    Extrae la guía docente estructurada del portal centralizado de la UCA (asignaturas.uca.es).
    """
    res = {
        "url_guia_docente": url,
        "fuente": "UCA - Portal Programas Docentes",
        "codigo_asignatura": "",
        "nombre_asignatura": "",
        "curso_academico": "2025-26",
        "idioma": "Castellano",
        "departamento": "",
        "area_conocimiento": "",
        "creditos": {"teoria": 0.0, "practicas": 0.0, "total_ects": 6.0},
        "horas_presenciales": {"teoria": 0.0, "otras": 0.0, "total": 150.0},
        "temario": [],
        "sistema_evaluacion": [],
        "criterios_evaluacion": "",
        "profesorado": [],
        "actividades_docentes": [],
        "resultados_aprendizaje": []
    }

    # Encabezado: Código y Nombre
    title_elem = soup.find("h2")
    if title_elem:
        m_t = re.search(r"<\s*(\d+)\s*\|\s*([^>]+)>", title_elem.get_text())
        if m_t:
            res["codigo_asignatura"] = m_t.group(1).strip()
            res["nombre_asignatura"] = sanitize_subject_name(m_t.group(2).strip())

    # Bloque de metadatos generales
    info_div = soup.find("div", class_="info-asignatura")
    if info_div:
        text_info = info_div.get_text(separator=" ", strip=True)
        m_dept = re.search(r"Departamento:\s*([^|]+)\|?\s*([A-Za-zÁÉÍÓÚáéíóúñ\s]+)", text_info)
        if m_dept:
            res["departamento"] = m_dept.group(2).strip()
        m_area = re.search(r"Área:\s*([^|]+)\|?\s*([A-Za-zÁÉÍÓÚáéíóúñ\s]+)", text_info)
        if m_area:
            res["area_conocimiento"] = m_area.group(2).strip()
        m_idioma = re.search(r"Idioma:\s*([A-Za-zÁÉÍÓÚáéíóúñ]+)", text_info)
        if m_idioma:
            res["idioma"] = m_idioma.group(1).strip().capitalize()
        m_ct = re.search(r"Créd\.\s*Teoría:\s*([\d,]+)", text_info)
        if m_ct:
            res["creditos"]["teoria"] = float(m_ct.group(1).replace(",", "."))
        m_cp = re.search(r"Créd\.\s*Prácticas:\s*([\d,]+)", text_info)
        if m_cp:
            res["creditos"]["practicas"] = float(m_cp.group(1).replace(",", "."))
        m_ects = re.search(r"Créd\.\s*ECTS:\s*([\d,]+)", text_info)
        if m_ects:
            res["creditos"]["total_ects"] = float(m_ects.group(1).replace(",", "."))

    # Temario (Tabla id="temario")
    temario_table = soup.find("table", id="temario")
    if temario_table:
        for tr in temario_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                orden = tds[0].get_text(strip=True)
                td_text = tds[1].get_text(separator="\n", strip=True)
                lineas = [l.strip() for l in td_text.splitlines() if l.strip()]
                if lineas:
                    bloque_titulo = lineas[0]
                    subtemas = lineas[1:] if len(lineas) > 1 else []
                    if not is_spurious_or_administrative_subject(bloque_titulo):
                        res["temario"].append({
                            "orden": orden,
                            "titulo": bloque_titulo,
                            "contenidos": subtemas
                        })

    # Sistema de evaluación
    eval_table = soup.find("table", id=lambda x: x and "procedimientos_evaluacion" in x)
    if eval_table:
        for tr in eval_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                tarea = tds[1].get_text(strip=True)
                tecnicas = tds[2].get_text(strip=True)
                ponderacion_str = tds[3].get_text(strip=True)
                try:
                    pond_val = float(ponderacion_str.replace(",", ".").replace("%", ""))
                except ValueError:
                    pond_val = 0.0
                res["sistema_evaluacion"].append({
                    "tarea": tarea,
                    "instrumentos": tecnicas,
                    "ponderacion_porcentaje": pond_val
                })

    # Criterios de evaluación e IA Generativa
    crit_input = soup.find("input", attrs={"name": "criterios_evaluacion"})
    if crit_input and crit_input.get("value"):
        raw_val = crit_input["value"]
        clean_crit = BeautifulSoup(raw_val, "html.parser").get_text(separator="\n", strip=True)
        res["criterios_evaluacion"] = clean_crit

    # Profesorado
    prof_table = soup.find("table", id="profesorado")
    if prof_table:
        for tr in prof_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                apellidos = f"{tds[0].get_text(strip=True)} {tds[1].get_text(strip=True)}".strip()
                nombre = tds[2].get_text(strip=True)
                categoria = tds[3].get_text(strip=True)
                es_coord = bool(tr.find("i", class_="text-primary"))
                res["profesorado"].append({
                    "nombre_completo": f"{nombre} {apellidos}".strip(),
                    "categoria": categoria,
                    "coordinador": es_coord
                })

    return res


def parse_generic_eees_subject_guide(soup: BeautifulSoup, url: str) -> dict:
    """
    Parser semántico modular para guías docentes del EEES en formato HTML genérico
    (UPC, UPF, UAB, UV, UPM, UNED, etc.).
    """
    res = {
        "url_guia_docente": url,
        "fuente": "Portal Oficial Universidad",
        "codigo_asignatura": "",
        "nombre_asignatura": "",
        "idioma": "Castellano",
        "temario": [],
        "sistema_evaluacion": [],
        "criterios_evaluacion": "",
        "profesorado": [],
        "bibliografia": [],
        "competencias": []
    }

    h1 = soup.find("h1")
    if h1:
        res["nombre_asignatura"] = sanitize_subject_name(h1.get_text(strip=True))

    SECTIONS_MAP = {
        "temario": ["temario", "continguts", "contenidos", "programa", "syllabus", "bloques temáticos", "plà docent"],
        "evaluacion": ["evaluación", "avaluació", "evaluation", "sistema de evaluación", "criteris d'avaluació"],
        "profesorado": ["profesorado", "professorat", "equip docent", "equipo docente", "teaching staff", "coordinación", "professors", "profesores"],
        "bibliografia": ["bibliografía", "bibliografia", "bibliography", "referencias", "recursos d'aprenentatge"],
        "competencias": ["competencias", "competències", "learning outcomes", "resultados de aprendizaje"]
    }

    headings = soup.find_all(["h2", "h3", "h4", "dt", "strong", "legend"])
    for h in headings:
        h_text = h.get_text(strip=True).lower()
        
        # 1. Temario
        if any(kw in h_text for kw in SECTIONS_MAP["temario"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "table", "p", "dd"])
            if next_node:
                items = next_node.find_all(["li", "p", "tr"])
                for it in items:
                    txt = it.get_text(strip=True)
                    if txt and 4 <= len(txt) <= 250 and not is_spurious_or_administrative_subject(txt):
                        res["temario"].append({"titulo": txt, "contenidos": []})
        
        # 2. Evaluación
        elif any(kw in h_text for kw in SECTIONS_MAP["evaluacion"]):
            next_node = h.find_next_sibling(["div", "table", "p", "ul", "dd"])
            if next_node:
                res["criterios_evaluacion"] = next_node.get_text(separator="\n", strip=True)
        
        # 3. Profesorado
        elif any(kw in h_text for kw in SECTIONS_MAP["profesorado"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "table", "p", "dd"])
            if next_node:
                for it in next_node.find_all(["li", "tr", "p"]):
                    p_txt = it.get_text(strip=True)
                    if p_txt and 4 <= len(p_txt) <= 80:
                        res["profesorado"].append({"nombre_completo": p_txt, "coordinador": False})
        
        # 4. Bibliografía
        elif any(kw in h_text for kw in SECTIONS_MAP["bibliografia"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "p", "dd"])
            if next_node:
                for it in next_node.find_all(["li", "p"]):
                    b_txt = it.get_text(strip=True)
                    if b_txt and 6 <= len(b_txt) <= 300:
                        res["bibliografia"].append(b_txt)

    return res


def parse_subject_guide_pdf_stream(pdf_bytes: bytes, url: str) -> dict:
    """
    Extrae temarios, evaluación y profesorado directamente desde el flujo binario de un PDF en RAM (0 I/O en disco).
    """
    res = {
        "url_guia_docente": url,
        "fuente": "Guía Docente Oficial PDF",
        "codigo_asignatura": "",
        "nombre_asignatura": "",
        "idioma": "Castellano",
        "departamento": "",
        "creditos": {"teoria": 0.0, "practicas": 0.0, "total_ects": 6.0},
        "temario": [],
        "sistema_evaluacion": [],
        "criterios_evaluacion": "",
        "profesorado": [],
        "bibliografia": [],
        "competencias": []
    }

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = [p.extract_text() or "" for p in reader.pages]
        full_text = "\n".join(pages_text)
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]

        # 1. Metadatos generales (Nombre, Código, ECTS, Departamento)
        for l in lines[:30]:
            m_name = re.search(r"(?:Course Name|Asignatura|Nombre):\s*([^\n|]+)", l, re.IGNORECASE)
            if m_name and not res["nombre_asignatura"]:
                res["nombre_asignatura"] = sanitize_subject_name(m_name.group(1).strip())

            m_code = re.search(r"(?:Code|Código):\s*(\d{4,8})", l, re.IGNORECASE)
            if m_code and not res["codigo_asignatura"]:
                res["codigo_asignatura"] = m_code.group(1).strip()

            m_ects = re.search(r"(?:ECTS|Créditos|Credits):\s*([\d,.]+)", l, re.IGNORECASE)
            if m_ects:
                try:
                    res["creditos"]["total_ects"] = float(m_ects.group(1).replace(",", "."))
                except ValueError:
                    pass

            m_dept = re.search(r"(?:Department|Departamento|Área):\s*([^\n|]+)", l, re.IGNORECASE)
            if m_dept and not res["departamento"]:
                res["departamento"] = m_dept.group(1).strip()

        # 2. Temario / Units / Blocks
        for l in lines:
            m_unit = re.search(r"^(Unit\s+\d+|Tema\s+\d+|Bloque\s+[I|V|X\d]+|Módulo\s+\d+)[:.\-–\s]+(.+)$", l, re.IGNORECASE)
            if m_unit:
                u_label = m_unit.group(1).strip()
                u_title = m_unit.group(2).strip()
                if not is_spurious_or_administrative_subject(u_title):
                    res["temario"].append({
                        "orden": u_label,
                        "titulo": u_title,
                        "contenidos": []
                    })

        # 3. Evaluación
        eval_lines = []
        in_eval = False
        for l in lines:
            if re.search(r"(?:5\.\s*ASSESSMENT|EVALUACIÓN|EVALUATION|SISTEMA DE EVALUACIÓN)", l, re.IGNORECASE):
                in_eval = True
                continue
            if in_eval and re.search(r"(?:6\.\s*BIBLIOGRAPHY|BIBLIOGRAFÍA|7\.\s*DOCENCIA|PROFESORADO)", l, re.IGNORECASE):
                in_eval = False
                break
            if in_eval:
                eval_lines.append(l)
                # Detectar pruebas evaluables y porcentajes
                m_pond = re.search(r"([A-Za-zÁÉÍÓÚáéíóúñ\s,–\-]{4,50})\s*[:=–]\s*(\d{1,2}(?:[.,]\d+)?)\s*%", l)
                if m_pond:
                    tarea_nom = m_pond.group(1).strip()
                    pond_val = float(m_pond.group(2).replace(",", "."))
                    if not any(ev["tarea"] == tarea_nom for ev in res["sistema_evaluacion"]):
                        res["sistema_evaluacion"].append({
                            "tarea": tarea_nom,
                            "instrumentos": "",
                            "ponderacion_porcentaje": pond_val
                        })

        if eval_lines and not res["criterios_evaluacion"]:
            res["criterios_evaluacion"] = "\n".join(eval_lines[:12])

        # 4. Profesorado / Lecturers
        for l in lines:
            m_prof = re.search(r"(?:Lecturers?|Profesorado|Teaching staff):\s*([^\n]+)", l, re.IGNORECASE)
            if m_prof:
                profs_raw = m_prof.group(1).split(",")
                for p in profs_raw:
                    p_clean = p.strip()
                    if 4 <= len(p_clean) <= 60 and not any(p_clean == x["nombre_completo"] for x in res["profesorado"]):
                        res["profesorado"].append({"nombre_completo": p_clean, "coordinador": False})

    except Exception as e:
        logger.warning(f"Error al procesar stream PDF de guía docente: {e}")

    return res


def parse_subject_guide(url: str, content: bytes, content_type: str = "") -> dict:
    """
    Enrutador inteligente y unificado para analizar guías docentes tanto en formato HTML como en flujo binario PDF.
    """
    is_pdf = url.lower().endswith(".pdf") or "application/pdf" in content_type.lower() or content.startswith(b"%PDF")
    if is_pdf:
        return parse_subject_guide_pdf_stream(content, url)
    
    # Si es HTML
    try:
        html_text = content.decode("utf-8", errors="replace")
    except Exception:
        html_text = str(content)

    soup = BeautifulSoup(html_text, "html.parser")
    if "asignaturas.uca.es" in url:
        return parse_uca_subject_guide(soup, url)
    else:
        return parse_generic_eees_subject_guide(soup, url)


# =============================================================================
# EJECUTOR PRINCIPAL DE LA FASE 1 - PARTE 4
# =============================================================================

def run_phase1_part4(max_workers: int = 4, limit_univ: int = None, limit_degrees: int = None, force: bool = False):
    """
    FASE 1 - PARTE 4: Extracción de temarios, evaluación y contenido de guías docentes.
    Recorre los planes de estudio en planes_estudio/*.json, resuelve URLs canónicas
    con Fast-Path universal, descarga las guías docentes mediante deduplicación dual en SQLite WAL
    y almacena el contenido estructurado.
    """
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 4: GUÍAS DOCENTES Y TEMARIOS EEES")
    print("======================================================================")

    cache = SubjectGuideCache()
    downloader = RUCTDownloader()

    plan_files = [
        os.path.join(PLANES_DIR, f)
        for f in os.listdir(PLANES_DIR)
        if f.endswith(".json")
    ]

    total_degrees = len(plan_files)
    print(f" -> {total_degrees} planes de estudio a inspeccionar en disco.")

    processed_guides = 0
    cached_hits = 0
    enriched_degrees = 0
    start_time = time.time()
    seen_univs = set()

    for idx, p_path in enumerate(plan_files, 1):
        if limit_degrees and idx > limit_degrees:
            break

        try:
            with open(p_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            continue

        d_code = data.get("codigo_estudio", "")
        d_title = data.get("titulo", "")
        u_code = data.get("universidad_codigo", "")
        u_name = data.get("universidad_nombre", "")
        u_web = data.get("web", "") or data.get("web_fuente_directa_url", "")

        if limit_univ and len(seen_univs) >= limit_univ and u_code not in seen_univs:
            continue
        if u_code:
            seen_univs.add(u_code)

        plan = data.get("plan_estudios", {})
        elementos = plan.get("elementos_curriculares", [])

        if not elementos:
            continue

        degree_modified = False

        for elem in elementos:
            asig_code = elem.get("codigo_asignatura") or elem.get("codigo")
            asig_name = elem.get("nombre_elemento", "")

            # 1. Comprobación Dual en Caché SQLite WAL (URL o clave compuesta institucional)
            url_directa = elem.get("url_guia_docente")
            cached_data = cache.get(url=url_directa, u_code=u_code, asig_code=asig_code)
            if cached_data and not force:
                elem["guia_docente"] = cached_data
                cached_hits += 1
                degree_modified = True
                continue

            # 2. Resolución de URLs candidatas mediante el Fast-Path Universal
            candidate_urls = resolve_candidate_subject_guide_urls(
                elem=elem,
                u_code=u_code,
                u_web=u_web,
                d_code=d_code
            )

            # 3. Descarga y parsing híbrido en memoria (HTML / PDF stream)
            for c_url in candidate_urls:
                try:
                    resp = downloader.get(c_url)
                    if resp and resp.status_code == 200:
                        c_type = resp.headers.get("Content-Type", "")
                        parsed_guide = parse_subject_guide(c_url, resp.content, c_type)
                        
                        final_asig_code = parsed_guide.get("codigo_asignatura") or asig_code or ""
                        cache.set(
                            url=c_url,
                            data=parsed_guide,
                            u_code=u_code,
                            asig_code=final_asig_code,
                            nombre=asig_name
                        )
                        elem["guia_docente"] = parsed_guide
                        elem["url_guia_docente"] = c_url
                        processed_guides += 1
                        degree_modified = True
                        break
                except SkipUniversityException:
                    print(f" [AVISO CORTOCIRCUITO] Omitiendo guías de la universidad [{u_code}] por sobrecarga del servidor.")
                    break
                except Exception as e:
                    logger.debug(f"Error al descargar guía '{c_url}': {e}")

        if degree_modified:
            atomic_json_dump(data, p_path)
            enriched_degrees += 1

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "=" * 70)
    print("      FASE 1 - PARTE 4 FINALIZADA CON ÉXITO")
    print("======================================================================")
    print(f" -> Titulaciones enriquecidas con temario: {enriched_degrees}")
    print(f" -> Guías docentes descargadas de la red:  {processed_guides}")
    print(f" -> Guías recuperadas de caché (N:M):      {cached_hits}")
    print(f" -> Tiempo total invertido:                {elapsed} seg")
    print("======================================================================")
