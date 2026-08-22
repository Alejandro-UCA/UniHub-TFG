import os
import sys
import re
import json
import time
import gzip
import threading
import requests
import urllib.parse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import concurrent.futures
from datetime import datetime

from config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    USER_AGENT,
    REQUEST_DELAY,
    HTTP_TIMEOUT,
    WEB_ROBOTS_FALLBACK_DELAY,
    SITEMAP_FETCH_TIMEOUT,
    WEB_SEARCH_SUBPAGES_LIMIT,
    PRIVATE_ECTS_MIN,
    PRIVATE_ECTS_MAX,
    PRIVATE_ANNUAL_MIN,
    PRIVATE_ANNUAL_MAX,
    WEB_CRAWLER_WORKERS,
    ROBOTS_CACHE_TTL_SECONDS,
    LAZY_SCANNED_PAGES_CACHE_LIMIT,
    ROBOTS_CHECK_TIMEOUT,
    WIKIPEDIA_API_URL,
    WIKIDATA_API_URL
)
from downloader import RUCTDownloader
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump, load_json_safe
from parsers import (
    parse_boe_pdf,
    classify_subject_caracter,
    is_curriculum_complete,
    get_curriculum_completeness_status
)


# Lista ampliada de palabras clave y sinónimos para portales académicos y planes de estudio
ACADEMIC_KEYWORDS = [
    "grado", "grados", "máster", "másteres", "master", "masteres",
    "doctorado", "doctorados", "titulación", "titulaciones", "estudio", "estudios",
    "enseñanza", "enseñanzas", "oferta-academica", "oferta_academica", "oferta-formativa",
    "plan-de-estudios", "plan_estudios", "plan-estudios", "planes-de-estudio",
    "guia-docente", "guias-docentes", "asignaturas", "programas", "curriculo",
    "currículo", "pensum", "malla-curricular", "titulos-oficiales", "estudios-oficiales"
]

HEADER_KEYWORDS = [
    "asignatura", "materia", "nombre", "crédito", "credito", "ects",
    "curso", "carácter", "caracter", "tipo", "código", "codigo", "guía", "guia"
]

INVALID_SUBJECT_KEYWORDS = [
    "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado",
    "aula", "edificio", "horario", "calendario", "examen", "convocatoria",
    # Calificaciones, notas y trámites administrativos de secretaría
    "suspenso", "aprobado", "notable", "sobresaliente", "matrícula de honor", "matricula de honor",
    "calificación cualitativa", "calificacion cualitativa", "calificación numérica", "calificacion numerica",
    "calificación estándar", "calificacion estandar", "escala de calificaciones", "tabla de equivalencias",
    "baremo", "convalidación", "convalidacion", "reconocimiento de créditos", "reconocimiento de creditos",
    "buscar por", "1º apellido", "2º apellido", "listado simple", "listado detallado"
]


def score_academic_candidate_url(url: str, link_text: str, academic_level: str, title_keywords: list = None) -> int:
    """
    Calcula la prioridad semántica de una URL candidata (0-100+):
    - Prioridad Alta (80-100): Portales de catálogo oficiales según el nivel académico (grados, másteres, doctorados).
    - Prioridad Media (40-60): Portales de oferta académica general y planes de estudio.
    - Prioridad Baja (1-10): Rutas administrativas o de servicios (nunca descartadas, pero evaluadas al final si no hay alternativa).
    """
    u_low = url.lower()
    t_low = (link_text or "").lower()
    level_low = (academic_level or "").lower()
    score = 10  # Puntuación base para cualquier enlace interno alcanzable
    
    # 1. Portales de catálogo específicos según el nivel académico (Prioridad Máxima)
    if "grado" in level_low:
        if any(kw in u_low for kw in ["grados-y-dobles-grados", "dobles-grados", "/grados", "/grado/", "/estudios/grado", "oferta-academica/grados", "oferta-formativa/grados"]):
            score += 90
        elif "grado" in t_low or "grados" in t_low:
            score += 70
    elif "master" in level_low or "máster" in level_low:
        if any(kw in u_low for kw in ["masteres-universitarios", "masteres-oficiales", "/masteres", "/master/", "/posgrado", "/postgrado"]):
            score += 90
        elif "master" in t_low or "máster" in t_low or "posgrado" in t_low:
            score += 70
    elif "doctor" in level_low:
        if any(kw in u_low for kw in ["programas-de-doctorado", "/doctorado", "/doctorados", "/escuela-doctorado"]):
            score += 90
        elif "doctorado" in t_low or "doctor" in t_low:
            score += 70

    # 2. Portales generales de oferta académica y planes de estudio (Prioridad Media)
    if any(kw in u_low for kw in ["oferta-academica", "oferta_academica", "oferta-formativa", "planes-de-estudio", "plan_estudios", "titulos-oficiales", "estudios-oficiales", "malla-curricular"]):
        score += 50
    if any(kw in t_low for kw in ["oferta académica", "oferta academica", "planes de estudio", "titulaciones oficiales", "estudios oficiales"]):
        score += 40

    # 3. Coincidencia con palabras clave del título de la titulación concreta
    if title_keywords and any(kw.lower() in u_low or kw.lower() in t_low for kw in title_keywords):
        score += 40

    # 4. Rutas administrativas o servicios generales: PRIORIDAD MÁS BAJA (No se eliminan, se evalúan al final)
    admin_service_patterns = [
        "/administracion", "/oficina-del-estudiante", "/servicios", "/alojamiento",
        "/transporte", "/seguro-escolar", "/becas", "/pau", "/noticias", "/prensa",
        "/eventos", "/actividades", "/categoria", "/wp-content", "/galeria", "/agenda"
    ]
    if any(p in u_low for p in admin_service_patterns):
        score = max(1, score - 80)

    return score


def is_valid_curricular_table(table_tag) -> bool:
    """Verifica que una tabla HTML sea verdaderamente curricular y no un formulario de búsqueda ni una escala de notas."""
    if table_tag.find(["input", "select", "textarea"]):
        return False
    txt = table_tag.get_text(separator=" ", strip=True).lower()
    grading_scale_markers = [
        "calificación cualitativa", "calificacion cualitativa",
        "calificación numérica", "calificacion numerica",
        "calificación estándar", "calificacion estandar",
        "escala de calificaciones", "tabla de equivalencias",
        "buscar por...", "1º apellido", "2º apellido"
    ]
    if any(m in txt for m in grading_scale_markers):
        return False
    # Debe poseer al menos un indicador curricular en encabezados o texto
    curricular_markers = [
        "asignatura", "materia", "denominaci", "ects", "crédito", "credito",
        "carácter", "caracter", "semestre", "cuatrimestre", "guía docente", "guia docente"
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
    is_grado = "grado" in (degree_title or "").lower()
    return {
        "resumen_creditos": {"Créditos Totales": "240" if is_grado else "60"},
        "total_elementos": len(elementos_html),
        "elementos_curriculares": elementos_html
    }


def is_valid_web_url(href) -> bool:
    """Valida que un enlace sea HTTP/HTTPS y no un esquema especial (mailto, javascript, tel, ancla)."""
    if not href or not isinstance(href, str):
        return False
    h = href.strip().lower()
    if h.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:", "ftp:", "data:")):
        return False
    return True


def is_same_or_subdomain(target_url: str, base_url: str) -> bool:
    """Verifica si target_url pertenece al mismo dominio o a un subdominio oficial de la universidad."""
    try:
        t_netloc = urllib.parse.urlparse(target_url).netloc.lower().replace("www.", "")
        b_netloc = urllib.parse.urlparse(base_url).netloc.lower().replace("www.", "")
        if not t_netloc or not b_netloc:
            return False
        return t_netloc == b_netloc or t_netloc.endswith("." + b_netloc) or b_netloc.endswith("." + t_netloc)
    except Exception:
        return False


def extract_html_subjects(soup: BeautifulSoup) -> list:
    """
    Extrae elementos curriculares de tablas HTML evitando filas de cabecera (<th>),
    palabras clave no curriculares (horarios, días, notas) y validando créditos ECTS.
    Mejora: deduplica por nombre normalizado, detecta columnas de código/nombre y fusiona múltiples tablas.
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
            cols = [td.get_text(separator=" ", strip=True) for td in tds]
            if len(cols) < 2:
                continue

            row_str = " ".join(cols).lower()

            # Detect header row
            if any(hk in row_str for hk in ["asignatura", "denominaci", "materia", "crédito", "credito", "ects", "carácter", "caracter", "curso"]):
                for c_i, c_val in enumerate(cols):
                    c_low = c_val.lower()
                    if any(w in c_low for w in ["asignatura", "denominaci", "nombre", "actividad"]):
                        subj_col = c_i
                    elif any(w in c_low for w in ["crédito", "credito", "ects"]):
                        ects_col = c_i
                    elif any(w in c_low for w in ["carácter", "caracter", "tipo"]):
                        car_col = c_i
                    elif any(w in c_low for w in ["curso", "año"]):
                        curso_col = c_i
                continue

            # Candidate subject name
            nombre_candidato = ""
            if subj_col < len(cols) and len(cols[subj_col]) >= 4 and not cols[subj_col].isdigit():
                nombre_candidato = cols[subj_col]
            elif len(cols) > 1 and (len(cols[0]) <= 4 or cols[0].isdigit() or re.match(r"^[1-6][º°a-z]*$", cols[0].lower())) and len(cols[1]) >= 4:
                nombre_candidato = cols[1]
            elif len(cols) > 0:
                nombre_candidato = cols[0]

            nombre_candidato = re.sub(r"\s+", " ", nombre_candidato).strip()
            nombre_lower = nombre_candidato.lower()

            if (
                len(nombre_candidato) < 4 
                or any(hk in nombre_lower for hk in HEADER_KEYWORDS) 
                or any(sk in nombre_lower for sk in INVALID_SUBJECT_KEYWORDS)
                or not re.search(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}", nombre_candidato)
                or len(nombre_candidato) > 150
            ):
                continue

            # Normalizar nombre para deduplicación
            norm_name = nombre_lower
            if norm_name in seen_names:
                continue

            # Buscar créditos ECTS
            creditos = "6"
            if ects_col != -1 and ects_col < len(cols):
                m_c = re.search(r"\b(\d+(?:[.,]\d+)?)\b", cols[ects_col])
                if m_c:
                    creditos = m_c.group(1).replace(",", ".")
            else:
                for col in cols[1:]:
                    m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", col)
                    if m:
                        val_str = m.group(1).replace(",", ".")
                        try:
                            val_num = float(val_str)
                            if 1.0 <= val_num <= 60.0:
                                creditos = str(int(val_num)) if val_num.is_integer() else str(val_num)
                                break
                        except ValueError:
                            pass

            # Buscar carácter
            caracter = "OB"
            if car_col != -1 and car_col < len(cols):
                caracter = classify_subject_caracter(cols[car_col], default="OB")
            else:
                for col in cols:
                    car = classify_subject_caracter(col, default="")
                    if car:
                        caracter = car
                        break

            # Buscar curso
            curso = ""
            if curso_col != -1 and curso_col < len(cols):
                curso = cols[curso_col]
            else:
                for col in cols[1:]:
                    col_lower = col.lower()
                    if any(c_kw in col_lower for c_kw in ["1º", "2º", "3º", "4º", "primer", "segundo", "tercer", "cuarto", "1er", "2do", "3er", "4to"]):
                        curso = col
                        break

            elementos.append({
                "modulo": "",
                "materia": "",
                "nombre_elemento": nombre_candidato,
                "creditos_ects": creditos,
                "caracter": caracter,
                "curso": curso,
                "cuatrimestre": ""
            })
            seen_names.add(norm_name)
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

    def __init__(self, user_agent=USER_AGENT, timeout=HTTP_TIMEOUT, metrics_tracker=None):
        self.user_agent = user_agent
        self.timeout = timeout
        self.metrics_tracker = metrics_tracker
        self.logger = ErrorLogger()
        self.checkpoint = CheckpointManager()
        self.univ_file_lock = threading.Lock()

    def _try_parse_candidate_pdf(self, downloader: RUCTDownloader, pdf_url: str, d_code: str, d_title: str, u_name: str) -> dict | None:
        """Descarga, analiza con parse_boe_pdf y limpia con seguridad el archivo PDF temporal."""
        temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
        try:
            downloader.download_file(pdf_url, temp_pdf)
            parsed = parse_boe_pdf(temp_pdf, target_title=d_title, univ_name=u_name)
            if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
                return parsed
        except Exception:
            pass
        finally:
            if os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except Exception:
                    pass
        return None

    def rescue_university_url(self, univ_name: str) -> str:
        """
        Consulta la API pública de Wikipedia y Wikidata para recuperar el sitio web oficial de una institución.
        """
        headers = {
            "User-Agent": f"{USER_AGENT} requests"
        }
        search_url = WIKIPEDIA_API_URL
        search_params = {
            "action": "query", "list": "search", "srsearch": univ_name,
            "format": "json", "utf8": 1, "srlimit": 1
        }
        
        try:
            resp = requests.get(search_url, params=search_params, headers=headers, timeout=self.timeout)
            data = resp.json()
            if not data.get("query", {}).get("search"):
                return None
                
            title = data["query"]["search"][0]["title"]
            prop_params = {"action": "query", "prop": "pageprops", "titles": title, "format": "json"}
            prop_resp = requests.get(search_url, params=prop_params, headers=headers, timeout=self.timeout)
            prop_data = prop_resp.json()
            
            pages = prop_data.get("query", {}).get("pages", {})
            page = list(pages.values())[0]
            wikibase_item = page.get("pageprops", {}).get("wikibase_item")
            
            if not wikibase_item:
                return None
                
            wikidata_url = WIKIDATA_API_URL
            wd_params = {"action": "wbgetentities", "ids": wikibase_item, "props": "claims", "format": "json"}
            wd_resp = requests.get(wikidata_url, params=wd_params, headers=headers, timeout=self.timeout)
            wd_data = wd_resp.json()
            
            claims = wd_data.get("entities", {}).get(wikibase_item, {}).get("claims", {})
            website_claims = claims.get("P856", [])
            
            if website_claims:
                return website_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        except Exception:
            pass
        return None

    def check_robots_allowed(self, target_url: str) -> tuple[bool, float | None]:
        """
        Verifica el archivo robots.txt de la web oficial de la universidad con caché 24h.
        Devuelve tupla (can_fetch, crawl_delay):
        - can_fetch: True si el rastreo está permitido para nuestro User-Agent / *, False en caso contrario.
        - crawl_delay: Tiempo de espera en segundos declarado en robots.txt (o None si no existe).
        """
        try:
            parsed = urllib.parse.urlparse(target_url)
            if not parsed.scheme or not parsed.netloc:
                return False, None
            netloc = parsed.netloc
            now = time.time()
            # Caché 24h según RFC 9309 sección 2.4 (protegida por Lock entre hilos)
            with self._robots_lock:
                if netloc in self._robots_cache:
                    ts, can_fetch, crawl_delay = self._robots_cache[netloc]
                    if now - ts < self._robots_cache_ttl:
                        return can_fetch, crawl_delay

            robots_url = f"{parsed.scheme}://{netloc}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            downloader = RUCTDownloader(delay=REQUEST_DELAY, timeout=ROBOTS_CHECK_TIMEOUT)
            try:
                robots_txt_content = downloader.fetch_text(robots_url)
                rp.parse(robots_txt_content.splitlines())
            except Exception:
                # Si robots.txt no existe (404) o da error, el estándar web considera el acceso permitido
                with self._robots_lock:
                    self._robots_cache[netloc] = (now, True, None)
                return True, None
            finally:
                downloader.close()

            can_fetch = rp.can_fetch(self.user_agent, target_url) or rp.can_fetch("*", target_url)
            
            crawl_delay = None
            try:
                raw_delay = rp.crawl_delay(self.user_agent) or rp.crawl_delay("*")
                if raw_delay:
                    crawl_delay = float(raw_delay)
            except Exception:
                pass

            with self._robots_lock:
                self._robots_cache[netloc] = (now, can_fetch, crawl_delay)
            return can_fetch, crawl_delay
        except Exception as e:
            print(f"   [robots.txt] No se pudo comprobar robots.txt para {target_url}: {e}. Se asume permitido.")
            return True, None

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

        downloader = RUCTDownloader(delay=0.1, timeout=SITEMAP_FETCH_TIMEOUT, metrics_tracker=self.metrics_tracker)
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
                        except Exception:
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
                except Exception:
                    continue
        finally:
            downloader.close()

        return sitemap_candidate_urls

    def process_university_web(self, univ: dict, titulaciones_por_univ: dict) -> dict:
        """
        Procesa una universidad en la Parte 2:
        1. Comprueba si tiene web oficial.
        2. Identifica titulaciones sin plan de estudios.
        3. Verifica permiso en robots.txt.
        4. Accede previamente al Sitemap XML (si existe) y escanea el portal académico con sinónimos ampliados.
        """
        u_code = univ.get("codigo", "")
        u_name = univ.get("nombre", "")
        u_type = univ.get("tipo", "")
        web_url = univ.get("web", "").strip()

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
            print(f" [Parte 2] Universidad [{u_code}] {u_name}: Sin web oficial registrada. Finalizado.")
            return stats

        web_url = ensure_https_url(web_url)

        # Comprobar si la universidad fue previamente registrada en checkpoint como denegada por robots.txt
        if self.checkpoint.is_robots_denied_university(u_code):
            print(f" [BLOQUEO ROBOTS] Universidad [{u_code}] {u_name}: Previamente registrada en checkpoint como DENEGADA por robots.txt. Omitiendo.")
            stats["robots_allowed"] = False
            return stats

        # 2. Identificar titulaciones sin información del plan de estudios
        univ_data = titulaciones_por_univ.get(u_code, {})
        active_degrees = univ_data.get("titulaciones_vigentes", [])
        
        missing_degrees = []
        for deg in active_degrees:
            d_code = deg.get("codigo_estudio", "")
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
            
            needs_info = True
            if os.path.exists(plan_file):
                try:
                    d_json = load_json_safe(plan_file)
                    if is_curriculum_complete(d_json):
                        needs_info = False
                except Exception:
                    needs_info = True
            
            if needs_info:
                missing_degrees.append(deg)

        stats["missing_degrees_count"] = len(missing_degrees)

        if not missing_degrees:
            print(f" [Parte 2] Universidad [{u_code}] {u_name}: Todas las titulaciones ({len(active_degrees)}) tienen plan de estudios. Finalizado.")
            return stats

        print(f" [Parte 2] Universidad [{u_code}] {u_name}: {len(missing_degrees)} titulaciones sin plan de estudios. Verificando conectividad en '{web_url}'...")

        # 2.5 Test de conectividad y Protocolo de Rescate (Wikipedia API)
        conn_downloader = RUCTDownloader(delay=0.1, timeout=10)
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
                stats["robots_allowed"] = False
                return stats
        finally:
            conn_downloader.close()

        # 3. Conectarse a la web oficial (HTTPS) y comprobar robots.txt y Crawl-delay
        can_fetch, crawl_delay = self.check_robots_allowed(web_url)
        if not can_fetch:
            print(f" [BLOQUEO ROBOTS] Universidad [{u_code}] {u_name}: Crawling DENEGADO por robots.txt en {web_url}. Registrando en checkpoint y cancelando operación.")
            self.checkpoint.mark_robots_denied_university(u_code, web_url, "Crawling denegado por robots.txt")
            stats["robots_allowed"] = False
            return stats

        effective_delay = max(crawl_delay, 0.5) if crawl_delay and crawl_delay > 0 else 0.5
        delay_msg = f" (Crawl-delay declarado en robots.txt: {crawl_delay:.1f}s)" if crawl_delay else ""
        print(f" [PERMITIDO ROBOTS] Universidad [{u_code}] {u_name}: Crawling PERMITIDO por robots.txt{delay_msg}. Iniciando escaneo web...")

        # 4. Acceso previo al Sitemap XML del portal académico (respetando retardo oficial)
        downloader = RUCTDownloader(delay=effective_delay, timeout=15, metrics_tracker=self.metrics_tracker)
        downloader.reset_university_context(u_code)
        sitemap_urls = self.extract_sitemap_candidate_urls(web_url, missing_degrees=missing_degrees)
        if sitemap_urls:
            print(f"     -> {len(sitemap_urls)} URLs académicas indexadas extraídas del Sitemap XML de la universidad.")

        TITLE_STOPWORDS = {
            "grado", "grados", "máster", "másteres", "master", "masteres", "doctorado", "doctorados",
            "universitario", "oficial", "sobre", "entre", "para", "como", "esta", "este", "estos", "estas",
            "del", "los", "las", "por", "con", "una", "uno", "que", "sus", "mas", "más",
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
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")

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
                except Exception:
                    pass

            if existing_direct_url:
                try:
                    print(f"     -> Probando URL directa guardada previamente: {existing_direct_url}")
                    if existing_direct_url.lower().endswith(".pdf"):
                        parsed = self._try_parse_candidate_pdf(downloader, existing_direct_url, d_code, d_title, u_name)
                        if parsed:
                            found_curriculum = parsed
                            direct_source_url = existing_direct_url
                except Exception as e:
                    print(f"     -> Falló lectura de URL directa previa: {e}")

            title_keywords = [w for w in d_title.split() if len(w) >= 3 and w.lower() not in TITLE_STOPWORDS]

            # ESTRATEGIA 1: Escaneo priorizado de URLs obtenidas del Sitemap XML
            if not found_curriculum and sitemap_urls:
                sitemap_matches = [url for url in sitemap_urls if any(kw.lower() in url.lower() for kw in title_keywords)]
                for sm_candidate_url in sitemap_matches[:5]:
                    if found_curriculum:
                        break
                    try:
                        time.sleep(0.5)
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
                            if len(elementos_html) >= 3:
                                found_curriculum = build_html_curriculum_payload(elementos_html, d_title)
                                direct_source_url = sm_candidate_url
                                print(f"     -> Encontradas asignaturas HTML válidas desde Sitemap XML: {sm_candidate_url}")
                                break
                    except Exception as sm_err:
                        print(f"     -> Error al probar URL del Sitemap '{sm_candidate_url}': {sm_err}")

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
                    scanned_urls = [u for u, score in sorted_candidates[:12]]
                    visited_targets = set()
                    
                    for candidate_page_url in scanned_urls:
                        if found_curriculum:
                            break

                        try:
                            if candidate_page_url in lazy_scanned_pages_cache:
                                sub_html, sub_soup = lazy_scanned_pages_cache[candidate_page_url]
                            else:
                                time.sleep(0.5) # Buenas prácticas de rate-limiting
                                try:
                                    sub_html = downloader.fetch_text(candidate_page_url)
                                    sub_soup = BeautifulSoup(sub_html, "html.parser")
                                    if len(lazy_scanned_pages_cache) < LAZY_SCANNED_PAGES_CACHE_LIMIT:
                                        lazy_scanned_pages_cache[candidate_page_url] = (sub_html, sub_soup)
                                except Exception as fetch_err:
                                    lazy_scanned_pages_cache[candidate_page_url] = (None, None)
                                    raise fetch_err

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
                                            if len(elementos_html) >= 3:
                                                found_curriculum = build_html_curriculum_payload(elementos_html, d_title)
                                                direct_source_url = html_fallback_url
                                                break
                                        except Exception:
                                            pass
                                    else:
                                        # Descargar e inspeccionar el HTML específico de la subpágina de la titulación target_link
                                        try:
                                            target_html = downloader.fetch_text(target_link)
                                            target_soup = BeautifulSoup(target_html, "html.parser")
                                            elementos_html = extract_html_subjects(target_soup)

                                            # Fallback: If static HTML yields < 3 subjects, render with Playwright headless browser for SPA JavaScript portals
                                            if len(elementos_html) < 3:
                                                try:
                                                    from spa_crawler import SPALayoutCrawler
                                                    spa_crawler = SPALayoutCrawler.get_shared_instance()
                                                    rendered_html = spa_crawler.render_spa_page(target_link)
                                                    if rendered_html:
                                                        spa_soup = BeautifulSoup(rendered_html, "html.parser")
                                                        spa_elementos = extract_html_subjects(spa_soup)
                                                        if len(spa_elementos) >= 3:
                                                            elementos_html = spa_elementos
                                                            target_soup = spa_soup
                                                            target_html = rendered_html
                                                except Exception:
                                                    pass
                                            
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
                                                        except Exception:
                                                            pass

                                            if len(elementos_html) >= 3 or extracted_pricing:
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
                                        except Exception as t_err:
                                            print(f"     -> Error al examinar subpágina de titulación '{target_link}': {t_err}")
                        except Exception as sub_err:
                            print(f"     -> Excepción al escanear sub-página '{candidate_page_url}': {sub_err}")

                except Exception as crawl_err:
                    print(f"     -> Error al rastrear la web oficial para [{d_code}]: {crawl_err}")

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
                degree_data["web_fuente_directa_url"] = direct_source_url
                degree_data["origen_fuente"] = "web_oficial_universidad"
                degree_data["precio_credito_ects"] = found_curriculum.get("precio_credito_ects") or deg.get("precio_credito_ects")
                degree_data["precio_credito_2"] = found_curriculum.get("precio_credito_2") or deg.get("precio_credito_2")
                degree_data["precio_credito_3"] = found_curriculum.get("precio_credito_3") or deg.get("precio_credito_3")
                degree_data["precio_credito_4"] = found_curriculum.get("precio_credito_4") or deg.get("precio_credito_4")
                degree_data["precio_estimado_anual"] = found_curriculum.get("precio_estimado_anual") or deg.get("precio_estimado_anual")
                degree_data["fuente_precio"] = found_curriculum.get("fuente_precio") or deg.get("fuente_precio")
                
                # Diagnosticar completitud curricular del plan obtenido
                degree_data["plan_estudios"] = found_curriculum
                comp_status = get_curriculum_completeness_status(degree_data)
                found_curriculum["plan_completo"] = comp_status["is_complete"]
                found_curriculum["ects_totales_detectados"] = comp_status["total_ects_obtained"]
                found_curriculum["ects_exigidos"] = comp_status["required_ects"]
                
                atomic_json_dump(degree_data, plan_file)
                self.checkpoint.update_degree_record(d_code, direct_source_url, datetime.now().strftime("%Y-%m-%d"), datetime.now().isoformat())
            else:
                print(f"     -> No se encontró plan de estudios en la web oficial para [{d_code}].")

        downloader.close()
        return stats


def run_phase1_part2(max_workers: int = 4, metrics_tracker=None):
    """
    Punto de entrada principal para la Fase 1 - Parte 2:
    Rastrea las webs oficiales de las universidades de forma paralela para encontrar información faltante.
    """
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 2: ESCANEO PARALELO WEBS OFICIALES")
    print("======================================================================")

    if not os.path.exists(UNIVERSIDADES_JSON) or not os.path.exists(TITULACIONES_JSON):
        print(" [AVISO PARTE 2] No existen archivos de datos de universidades/titulaciones. Finalizando.")
        return

    with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
        universities = json.load(f)

    with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
        titulaciones_por_univ = json.load(f)

    print(f" -> {len(universities)} universidades a procesar en paralelo con {max_workers} trabajadores.")

    crawler = UniversityWebCrawler(metrics_tracker=metrics_tracker)
    
    total_missing = 0
    total_resolved = 0
    denied_by_robots = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(crawler.process_university_web, univ, titulaciones_por_univ): univ
            for univ in universities
        }

        for future in concurrent.futures.as_completed(futures):
            univ = futures[future]
            try:
                res = future.result()
                total_missing += res.get("missing_degrees_count", 0)
                total_resolved += res.get("resolved_degrees_count", 0)
                if not res.get("robots_allowed", True):
                    denied_by_robots += 1
            except Exception as exc:
                print(f" [ERROR PARTE 2] Excepción inesperada en universidad {univ.get('codigo')}: {exc}")
                crawler.logger.log_error("fase1_parte2_univ_web", univ.get("codigo", "ALL"), univ.get("web", ""), "Excepcion no controlada en escaneo web de universidad", str(exc))

    print("\n" + "=" * 70)
    print("      FASE 1 - PARTE 2 FINALIZADA DE FORMA METICULOSA Y RESPETUOSA")
    print("======================================================================")
    print(f" -> Universidades escaneadas:             {len(universities)}")
    print(f" -> Titulaciones sin plan iniciales:       {total_missing}")
    print(f" -> Titulaciones completadas desde web:    {total_resolved}")
    print(f" -> Cancelaciones por robots.txt:         {denied_by_robots}")

if __name__ == "__main__":
    run_phase1_part2()
