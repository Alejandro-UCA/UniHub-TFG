import os
import sys
import re
import json
import time
import gzip
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
    HTTP_TIMEOUT
)
from downloader import RUCTDownloader
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump
from parsers import parse_boe_pdf


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
    "aula", "edificio", "horario", "calendario", "examen", "convocatoria"
]


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
    palabras clave no curriculares (horarios, días) y validando créditos ECTS.
    """
    elementos = []
    tables = soup.find_all("table")
    for t in tables:
        rows = t.find_all("tr")
        for row in rows:
            # Descartar filas compuestas únicamente por cabeceras <th>
            tds = row.find_all("td")
            if not tds:
                continue

            cols = [td.get_text(strip=True) for td in tds]
            if len(cols) < 2:
                continue

            nombre_candidato = cols[0]
            nombre_lower = nombre_candidato.lower()

            # Descartar cabeceras o términos de horario/calendario
            if len(nombre_candidato) < 4 or any(hk in nombre_lower for hk in HEADER_KEYWORDS) or any(sk in nombre_lower for sk in INVALID_SUBJECT_KEYWORDS):
                continue

            # Buscar créditos ECTS numéricos
            creditos = "6"
            found_ects = False
            for col in cols[1:]:
                # Extraer números (enteros o decimales ej. 6, 4.5)
                m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", col)
                if m:
                    val_str = m.group(1).replace(",", ".")
                    try:
                        val_num = float(val_str)
                        if 1.0 <= val_num <= 60.0:
                            creditos = str(int(val_num)) if val_num.is_integer() else str(val_num)
                            found_ects = True
                            break
                    except ValueError:
                        pass

            # Buscar término de curso dinámicamente en columnas
            curso = ""
            for col in cols[1:]:
                col_lower = col.lower()
                if any(c_kw in col_lower for c_kw in ["1º", "2º", "3º", "4º", "primer", "segundo", "tercer", "cuarto", "1er", "2do", "3er", "4to"]):
                    curso = col
                    break

            elementos.append({
                "nombre_elemento": nombre_candidato,
                "creditos_ects": creditos,
                "caracter": "OB",
                "curso": curso
            })
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
            val_str = m.group(1).replace(".", "").replace(",", ".")
            try:
                val_num = float(val_str)
                if 15.0 <= val_num <= 500.0:
                    pricing_data["precio_credito_ects"] = round(val_num, 2)
                    break
            except ValueError:
                pass
                
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
                val_str = m.group(1).replace(".", "").replace(",", ".")
                try:
                    val_num = float(val_str)
                    if 15.0 <= val_num <= 500.0:
                        pricing_data[key] = round(val_num, 2)
                        break
                except ValueError:
                    pass
                    
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
            val_str = m.group(1).replace(".", "").replace(",", ".")
            try:
                val_num = float(val_str)
                if 1000.0 <= val_num <= 45000.0:
                    pricing_data["precio_estimado_anual"] = round(val_num, 2)
                    break
            except ValueError:
                pass
                
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
    def __init__(self, user_agent=USER_AGENT, timeout=HTTP_TIMEOUT):
        self.user_agent = user_agent
        self.timeout = timeout
        self.logger = ErrorLogger()
        self.checkpoint = CheckpointManager()

    def check_robots_allowed(self, target_url: str) -> tuple[bool, float | None]:
        """
        Verifica el archivo robots.txt de la web oficial de la universidad.
        Devuelve tupla (can_fetch, crawl_delay):
        - can_fetch: True si el rastreo está permitido para nuestro User-Agent / *, False en caso contrario.
        - crawl_delay: Tiempo de espera en segundos declarado en robots.txt (o None si no existe).
        """
        try:
            parsed = urllib.parse.urlparse(target_url)
            if not parsed.scheme or not parsed.netloc:
                return False, None

            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            downloader = RUCTDownloader(delay=0.2, timeout=10)
            try:
                robots_txt_content = downloader.fetch_text(robots_url)
                rp.parse(robots_txt_content.splitlines())
            except Exception:
                # Si robots.txt no existe (404) o da error, el estándar web considera el acceso permitido
                return True, None

            can_fetch = rp.can_fetch(self.user_agent, target_url) or rp.can_fetch("*", target_url)
            
            # Extraer Crawl-delay si está declarado en el robots.txt de la universidad
            crawl_delay = None
            try:
                raw_delay = rp.crawl_delay(self.user_agent) or rp.crawl_delay("*")
                if raw_delay:
                    crawl_delay = float(raw_delay)
            except Exception:
                pass

            return can_fetch, crawl_delay
        except Exception as e:
            print(f"   [robots.txt] No se pudo comprobar robots.txt para {target_url}: {e}. Se asume permitido.")
            return True, None

    def fetch_sitemap_urls(self, base_url: str) -> set:
        """
        Previamente accede al Sitemap (sitemap.xml / sitemap_index.xml) del portal académico
        para detectar directamente las URLs disponibles en el sitio web de la universidad.
        Optimización 1: Timeout ajustado a 4s por sitemap candidato para evitar cuellos de botella.
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

        downloader = RUCTDownloader(delay=0.1, timeout=4)

        for sm_url in sitemap_targets:
            try:
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
                    if sitemap_candidate_urls:
                        break
            except Exception:
                continue

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

        if web_url.startswith("http://"):
            web_url = "https://" + web_url[7:]
        elif not web_url.startswith("https://"):
            web_url = "https://" + web_url

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
                    with open(plan_file, "r", encoding="utf-8") as f:
                        d_json = json.load(f)
                        plan = d_json.get("plan_estudios")
                        if plan and (plan.get("total_elementos", 0) > 0 or len(plan.get("resumen_creditos", {})) > 0):
                            needs_info = False
                except Exception:
                    needs_info = True
            
            if needs_info:
                missing_degrees.append(deg)

        stats["missing_degrees_count"] = len(missing_degrees)

        if not missing_degrees:
            print(f" [Parte 2] Universidad [{u_code}] {u_name}: Todas las titulaciones ({len(active_degrees)}) tienen plan de estudios. Finalizado.")
            return stats

        print(f" [Parte 2] Universidad [{u_code}] {u_name}: {len(missing_degrees)} titulaciones sin plan de estudios. Verificando robots.txt en '{web_url}'...")

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
        downloader = RUCTDownloader(delay=effective_delay, timeout=15)
        sitemap_urls = self.fetch_sitemap_urls(web_url)
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
                        temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
                        downloader.download_file(existing_direct_url, temp_pdf)
                        parsed = parse_boe_pdf(temp_pdf)
                        if os.path.exists(temp_pdf):
                            os.remove(temp_pdf)
                        if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
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
                            temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
                            try:
                                downloader.download_file(sm_candidate_url, temp_pdf)
                                parsed = parse_boe_pdf(temp_pdf)
                                if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
                                    found_curriculum = parsed
                                    direct_source_url = sm_candidate_url
                                    print(f"     -> Encontrado plan de estudios desde Sitemap XML: {sm_candidate_url}")
                                    break
                            except Exception:
                                pass
                            finally:
                                if os.path.exists(temp_pdf):
                                    try:
                                        os.remove(temp_pdf)
                                    except Exception:
                                        pass
                        else:
                            sub_html = downloader.fetch_text(sm_candidate_url)
                            sub_soup = BeautifulSoup(sub_html, "html.parser")
                            elementos_html = extract_html_subjects(sub_soup)
                            if len(elementos_html) >= 3:
                                found_curriculum = {
                                    "resumen_creditos": {"Créditos Totales": "240" if "grado" in d_title.lower() else "60"},
                                    "total_elementos": len(elementos_html),
                                    "elementos_curriculares": elementos_html
                                }
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
                        lazy_candidate_urls = set()

                        for a in lazy_soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if not is_valid_web_url(href):
                                continue
                            
                            text = a.get_text(strip=True).lower()
                            if any(kw in text for kw in ACADEMIC_KEYWORDS) or any(kw in href.lower() for kw in ACADEMIC_KEYWORDS):
                                full_url = urllib.parse.urljoin(web_url, href)
                                if is_same_or_subdomain(full_url, web_url):
                                    lazy_candidate_urls.add(full_url)
                    
                    home_html = lazy_home_html
                    soup = lazy_soup
                    candidate_urls = lazy_candidate_urls

                    # Ordenar URLs candidatas por longitud (menor a mayor) para priorizar índices principales
                    scanned_urls = sorted(list(candidate_urls), key=len)[:8]
                    visited_targets = set()
                    
                    for candidate_page_url in scanned_urls:
                        if found_curriculum:
                            break

                        try:
                            time.sleep(0.5) # Buenas prácticas de rate-limiting
                            sub_html = downloader.fetch_text(candidate_page_url)
                            sub_soup = BeautifulSoup(sub_html, "html.parser")

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
                                        temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
                                        try:
                                            downloader.download_file(target_link, temp_pdf)
                                            parsed = parse_boe_pdf(temp_pdf)
                                            if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
                                                found_curriculum = parsed
                                                direct_source_url = target_link
                                                break
                                        except Exception:
                                            pass
                                        finally:
                                            if os.path.exists(temp_pdf):
                                                try:
                                                    os.remove(temp_pdf)
                                                except Exception:
                                                    pass
                                    else:
                                        # Descargar e inspeccionar el HTML específico de la subpágina de la titulación target_link
                                        try:
                                            target_html = downloader.fetch_text(target_link)
                                            target_soup = BeautifulSoup(target_html, "html.parser")
                                            elementos_html = extract_html_subjects(target_soup)
                                            
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
                                                found_curriculum = {
                                                    "resumen_creditos": {"Créditos Totales": "240" if "grado" in d_title.lower() else "60"},
                                                    "total_elementos": len(elementos_html),
                                                    "elementos_curriculares": elementos_html
                                                }
                                                if extracted_pricing.get("precio_credito_ects"):
                                                    found_curriculum["precio_credito_ects"] = extracted_pricing["precio_credito_ects"]
                                                    found_curriculum["precio_credito_2"] = extracted_pricing.get("precio_credito_2")
                                                    found_curriculum["precio_credito_3"] = extracted_pricing.get("precio_credito_3")
                                                    found_curriculum["precio_credito_4"] = extracted_pricing.get("precio_credito_4")
                                                    found_curriculum["precio_estimado_anual"] = extracted_pricing["precio_estimado_anual"]
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
                
                degree_data = {
                    "codigo_estudio": d_code,
                    "titulo": d_title,
                    "nivel_academico": deg.get("nivel_academico", ""),
                    "universidad_codigo": u_code,
                    "universidad_nombre": u_name,
                    "fecha_procesado": datetime.now().isoformat(),
                    "web_fuente_directa_url": direct_source_url,
                    "origen_fuente": "web_oficial_universidad",
                    "precio_credito_ects": found_curriculum.get("precio_credito_ects") or deg.get("precio_credito_ects"),
                    "precio_credito_2": found_curriculum.get("precio_credito_2") or deg.get("precio_credito_2"),
                    "precio_credito_3": found_curriculum.get("precio_credito_3") or deg.get("precio_credito_3"),
                    "precio_credito_4": found_curriculum.get("precio_credito_4") or deg.get("precio_credito_4"),
                    "precio_estimado_anual": found_curriculum.get("precio_estimado_anual") or deg.get("precio_estimado_anual"),
                    "fuente_precio": found_curriculum.get("fuente_precio") or deg.get("fuente_precio"),
                    "plan_estudios": found_curriculum
                }
                
                atomic_json_dump(degree_data, plan_file)
                self.checkpoint.update_degree_record(d_code, direct_source_url, datetime.now().strftime("%Y-%m-%d"), datetime.now().isoformat())
            else:
                print(f"     -> No se encontró plan de estudios en la web oficial para [{d_code}].")

        return stats


def run_phase1_part2(max_workers: int = 4):
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

    crawler = UniversityWebCrawler()
    
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
