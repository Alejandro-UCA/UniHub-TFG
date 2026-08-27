import os
import sys
import re
import io
import json
import time
import sqlite3
import hashlib
import logging
import threading
import unicodedata
import contextlib
from urllib.parse import urljoin, urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import pypdf

from config import (
    PLANES_DIR,
    UNIVERSIDADES_JSON,
    USER_AGENT,
    REQUEST_DELAY,
    WEB_CRAWLER_WORKERS,
    SQLITE_CONNECT_TIMEOUT,
    SUBJECT_GUIDE_CACHE_DB,
    SUBJECT_GUIDE_CACHE_LIMIT,
    MAX_RESPONSE_SIZE_BYTES,
    DOWNLOAD_CHUNK_SIZE,
    FULL_REVALIDATION,
    TARGET_UNIVERSITY_CODES,
)
from downloader import RUCTDownloader, SkipUniversityException, normalize_url
from checkpoint import atomic_json_dump, load_json_safe
from parsers import sanitize_subject_name, classify_subject_caracter
from univ_web_crawler import is_spurious_or_administrative_subject
from phase_common import iter_plan_files
from crawl_ledger import CrawlLedger

logger = logging.getLogger(__name__)

CACHE_GUIAS_DB = SUBJECT_GUIDE_CACHE_DB


class SubjectGuideCache:
    """
    Caché de alto rendimiento L1 (RAM) + L2 (SQLite WAL) para guías docentes.
    Permite búsqueda dual tanto por URL exacta como por clave compuesta canónica (universidad_codigo + codigo_asignatura).
    """
    _local = threading.local()

    MAX_L1_ENTRIES = SUBJECT_GUIDE_CACHE_LIMIT

    def __init__(self, db_path: str = CACHE_GUIAS_DB):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._l1_url_cache = {}
        self._l1_comp_cache = {}
        self._negative_urls = set()
        self._init_db()

    def _prune_l1_caches(self):
        """Poda las cachés en RAM cuando exceden MAX_L1_ENTRIES para evitar consumo excesivo de memoria."""
        if len(self._l1_url_cache) > self.MAX_L1_ENTRIES:
            keys_to_remove = list(self._l1_url_cache.keys())[:self.MAX_L1_ENTRIES // 2]
            for k in keys_to_remove:
                self._l1_url_cache.pop(k, None)
        if len(self._l1_comp_cache) > self.MAX_L1_ENTRIES:
            keys_to_remove = list(self._l1_comp_cache.keys())[:self.MAX_L1_ENTRIES // 2]
            for k in keys_to_remove:
                self._l1_comp_cache.pop(k, None)
        if len(self._negative_urls) > self.MAX_L1_ENTRIES:
            self._negative_urls = set(list(self._negative_urls)[self.MAX_L1_ENTRIES // 2:])

    def _get_conn(self):
        conns = getattr(self._local, "guide_conns", None)
        if conns is None:
            conns = {}
            self._local.guide_conns = conns
        if self.db_path not in conns:
            if self.db_path and self.db_path != ":memory:":
                dir_path = os.path.dirname(os.path.abspath(self.db_path))
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=SQLITE_CONNECT_TIMEOUT)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA mmap_size=268435456;")
            conn.execute("PRAGMA cache_size=-64000;")
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
            conns[self.db_path] = conn
        return conns[self.db_path]

    def _init_db(self):
        self._get_conn()

    def get(self, url: str = None, u_code: str = None, asig_code: str = None) -> dict:
        with self._lock:
            if url:
                url_clean = url.strip()
                if url_clean in self._negative_urls:
                    return None
                if url_clean in self._l1_url_cache:
                    return self._l1_url_cache[url_clean]

            if u_code and asig_code:
                comp_key = f"{str(u_code).zfill(3)}:{str(asig_code).strip()}"
                if comp_key in self._l1_comp_cache:
                    return self._l1_comp_cache[comp_key]

        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            if url:
                url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
                cursor.execute("SELECT datos_json FROM guias_docentes WHERE url_hash = ?", (url_hash,))
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    with self._lock:
                        self._l1_url_cache[url.strip()] = data
                        self._prune_l1_caches()
                    return data

            if u_code and asig_code:
                comp_key = f"{str(u_code).zfill(3)}:{str(asig_code).strip()}"
                cursor.execute(
                    "SELECT datos_json FROM guias_docentes WHERE universidad_codigo = ? AND codigo_asignatura = ? ORDER BY fecha_extraccion DESC LIMIT 1",
                    (str(u_code).zfill(3), str(asig_code).strip())
                )
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    with self._lock:
                        self._l1_comp_cache[comp_key] = data
                        self._prune_l1_caches()
                    return data
        except Exception as e:
            logger.warning(f"Error al leer caché de guía docente: {e}")
        return None

    def mark_negative(self, url: str):
        if url:
            with self._lock:
                self._negative_urls.add(url.strip())
                self._prune_l1_caches()

    def set(self, url: str, data: dict, u_code: str = "", asig_code: str = "", nombre: str = ""):
        if not data:
            return
        with self._lock:
            if url:
                self._l1_url_cache[url.strip()] = data
            if u_code and asig_code:
                comp_key = f"{str(u_code).zfill(3)}:{str(asig_code).strip()}"
                self._l1_comp_cache[comp_key] = data
            self._prune_l1_caches()

        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        try:
            conn = self._get_conn()
            conn.execute("""
                INSERT OR REPLACE INTO guias_docentes 
                (url_hash, url, universidad_codigo, codigo_asignatura, nombre, datos_json, fecha_extraccion)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (url_hash, url.strip(), str(u_code).zfill(3) if u_code else "", str(asig_code).strip() if asig_code else "", nombre, json.dumps(data, ensure_ascii=False)))
            conn.commit()
        except Exception as e:
            logger.warning(f"Error al escribir en caché SQLite de guías docentes: {e}")

    def close(self):
        """Closes thread-local SQLite connection handles."""
        conns = getattr(self._local, "guide_conns", None)
        if conns:
            for conn in list(conns.values()):
                try:
                    conn.close()
                except Exception:
                    pass
            conns.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


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


def _academic_year_candidates(academic_year: str, count: int = 3) -> list[str]:
    """Devuelve el curso solicitado y cursos anteriores para usar como respaldo."""
    match = re.search(r"(20\d{2})", str(academic_year or ""))
    start_year = int(match.group(1)) if match else datetime.now().year - (1 if datetime.now().month < 9 else 0)
    return [f"{start_year - offset}-{str(start_year - offset + 1)[-2:]}" for offset in range(max(1, count))]


def resolve_candidate_subject_guide_urls(
    elem: dict, 
    u_code: str, 
    u_web: str = "", 
    d_code: str = "",
    academic_year: str = None
) -> list:
    """
    Generador universal de URLs candidatas para guías docentes del EEES.
    Combina URLs explícitas ya extraídas con patrones institucionales generalizados.
    """
    candidates = []
    seen = set()
    if not academic_year:
        academic_year = _academic_year_candidates(None, count=1)[0]
    year_candidates = _academic_year_candidates(academic_year)

    def _add_url(u: str):
        if not u:
            return
        norm = normalize_url(u)
        if norm and norm not in seen and norm.startswith("http"):
            seen.add(norm)
            candidates.append(norm)

    # 1. URL explícita ya detectada en el plan web o BOE. Si pertenece a un
    # curso antiguo se añade al final, para que no oculte una URL vigente.
    url_directa = elem.get("url_guia_docente")
    current_year = year_candidates[0]
    explicit_year_match = re.search(r"20\d{2}[-_/]?\d{2}", str(url_directa or ""))
    if url_directa and (not explicit_year_match or current_year in str(url_directa)):
        _add_url(url_directa)

    asig_code = elem.get("codigo_asignatura") or elem.get("codigo")
    asig_nombre = elem.get("nombre_elemento", "")

    # Inferir código numérico de asignatura si está embebido en el nombre
    if not asig_code:
        m_code = re.match(r"^(\d{4,8})\s*[-–_:]\s*(.+)$", asig_nombre)
        if m_code:
            asig_code = m_code.group(1)
            asig_nombre = m_code.group(2).strip()

    slug = generate_subject_slug(asig_nombre)
    u_code_padded = str(u_code).zfill(3)

    # 2. Mapeo Canónico de Dominios Institucionales del Sistema Universitario Español (SUE)
    DOMAIN_BY_UCODE = {
        "001": "uned.es", "002": "uah.es", "003": "ua.es", "008": "ub.edu", "009": "ucm.es",
        "010": "uam.es", "011": "upm.es", "012": "uc3m.es", "014": "uva.es",
        "015": "usal.es", "017": "us.es", "018": "uma.es", "019": "ugr.es",
        "020": "uco.es", "024": "uv.es", "025": "uca.es", "026": "uab.cat", "028": "uned.es",
        "029": "upc.edu", "030": "udg.edu", "031": "udl.cat", "032": "urv.cat", "033": "upf.edu",
        "034": "unex.es", "035": "udc.es", "036": "usc.es", "037": "uvigo.gal",
        "038": "uniovi.es", "039": "unican.es", "040": "unirioja.es", "041": "unavarra.es",
        "042": "ehu.eus", "043": "unav.edu", "044": "upv.es", "045": "urjc.es",
        "046": "upo.es", "047": "ull.es", "048": "upct.es", "049": "ulpgc.es",
        "050": "nebrija.com", "051": "universidadeuropea.com", "054": "uji.es", "055": "umh.es"
    }

    parsed_domain = urlparse(u_web).netloc.lower() if u_web else ""
    if not parsed_domain:
        domain = DOMAIN_BY_UCODE.get(u_code_padded, "")
    else:
        domain = parsed_domain

    if domain:
        clean_domain = re.sub(r"^www\.", "", domain)

        # Códigos variantes (original y sin ceros a la izquierda)
        code_variants = [asig_code] if asig_code else []
        if asig_code and asig_code.startswith("0"):
            code_variants.append(asig_code.lstrip("0"))

        # 3. Patrones Institucionales Especializados por Código de Universidad / Dominio
        for c_code in code_variants:
            if u_code_padded == "025" or "uca.es" in clean_domain:
                for year in year_candidates:
                    _add_url(f"https://asignaturas.uca.es/asig/{year}/{c_code}/")
                    _add_url(f"https://asignaturas.uca.es/{year}/{c_code}")
                _add_url(f"https://asignaturas.uca.es/asig/{c_code}/")
                _add_url(f"https://asignaturas.uca.es/{c_code}")

            elif u_code_padded == "010" or "uam.es" in clean_domain:
                for year in year_candidates:
                    if d_code:
                        _add_url(f"https://secretariavirtual.uam.es/doa/consultaPublica/look[conpub]MostrarGuiaDocenteAsignatura?codigoAsignatura={c_code}&planEstudio={d_code}&cursoAcademico={year}")
                    _add_url(f"https://secretariavirtual.uam.es/doa/consultaPublica/look[conpub]MostrarGuiaDocenteAsignatura?codigoAsignatura={c_code}&cursoAcademico={year}")
                if d_code:
                    _add_url(f"https://secretariavirtual.uam.es/doa/consultaPublica/look[conpub]MostrarGuiaDocenteAsignatura?codigoAsignatura={c_code}&planEstudio={d_code}")
                _add_url(f"https://secretariavirtual.uam.es/doa/consultaPublica/look[conpub]MostrarGuiaDocenteAsignatura?codigoAsignatura={c_code}")

            elif u_code_padded == "009" or "ucm.es" in clean_domain:
                _add_url(f"https://geapre.ucm.es/guia/verGuia.php?asig={c_code}")
                _add_url(f"https://estudios.ucm.es/guias/{c_code}")

            elif u_code_padded == "012" or "uc3m.es" in clean_domain:
                _add_url(f"https://aplicaciones.uc3m.es/cpa/dspMuestraFicha?g=1&asig={c_code}&idioma=1")
                _add_url(f"https://aplicaciones.uc3m.es/cpa/dspMuestraFicha?asig={c_code}")

            elif u_code_padded == "024" or "uv.es" in clean_domain:
                for year in year_candidates:
                    _add_url(f"https://webges.uv.es/uvGuiaDocenteWeb/guia?asignatura={c_code}&curso={year}")
                _add_url(f"https://webges.uv.es/uvGuiaDocenteWeb/guia?asignatura={c_code}")

            elif u_code_padded == "026" or "uab.cat" in clean_domain:
                for year in year_candidates:
                    _add_url(f"https://guies.uab.cat/guies_docents/public/{year}/{c_code}.pdf")
                _add_url(f"https://guies.uab.cat/guies_docents/public/{c_code}.pdf")

            elif u_code_padded == "029" or "upc.edu" in clean_domain:
                if slug:
                    _add_url(f"https://www.upc.edu/es/grados/{slug}/plan-de-estudios/asignaturas/{c_code}")
                _add_url(f"https://www.upc.edu/es/grados/asignaturas/{c_code}")

            elif u_code_padded == "042" or "ehu.eus" in clean_domain:
                _add_url(f"https://www.ehu.eus/es/web/graduak/asignatura/-/asig/{c_code}")

            elif u_code_padded == "017" or "us.es" in clean_domain:
                _add_url(f"https://sevius.us.es/index.php?op=guia_docente&cod_asig={c_code}")

            elif u_code_padded == "045" or "urjc.es" in clean_domain:
                if d_code:
                    _add_url(f"https://gestion2.urjc.es/guiasdocentes/consulta?cod_asignatura={c_code}&cod_plan={d_code}")
                _add_url(f"https://gestion2.urjc.es/guiasdocentes/consulta?cod_asignatura={c_code}")

            elif u_code_padded == "035" or "udc.es" in clean_domain:
                if d_code:
                    _add_url(f"https://guiadocente.udc.es/guia_docent/index.php?centre=&ensenyament={d_code}&assignatura={c_code}")
                _add_url(f"https://guiadocente.udc.es/guia_docent/index.php?assignatura={c_code}")

            elif u_code_padded == "037" or "uvigo.gal" in clean_domain:
                _add_url(f"https://secretaria.uvigo.gal/uv/web/guias/{c_code}")

            elif u_code_padded in ["038", "054"] or "uji.es" in clean_domain:
                _add_url(f"https://sia.uji.es/sia/rest/guias/{c_code}")

            elif u_code_padded == "018" or "uma.es" in clean_domain:
                _add_url(f"https://oap.uma.es/guias_docentes/descargar_guia.php?asig={c_code}")
                _add_url(f"https://oap.uma.es/guias_docentes/ver_guia.php?asig={c_code}")

            # 4. Patrones Institucionales Genéricos del SUE
            _add_url(f"https://secretaria.{clean_domain}/docencia/guia/{c_code}")
            _add_url(f"https://cv1.cpd.{clean_domain}/ConsPlanesEstudio/cvFichaAsigRedir.asp?asig={c_code}")
            for year in year_candidates:
                _add_url(f"https://asignaturas.{clean_domain}/{year}/{c_code}")
                _add_url(f"https://guias.{clean_domain}/{year}/{c_code}")
                _add_url(f"https://guiasdocentes.{clean_domain}/{year}/{c_code}")

            if slug:
                _add_url(f"https://www.{clean_domain}/es/estudios/estudios-oficiales/grados/asignatura/{slug}-{c_code}/")
                _add_url(f"https://www.{clean_domain}/estudios/asignatura/{slug}-{c_code}/")

            if d_code:
                _add_url(f"https://www.{clean_domain}/descargas/guias/{c_code}.pdf")
                for year in year_candidates:
                    _add_url(f"https://www.{clean_domain}/shared/es/estudios/estudios-oficiales/grados/.galleries/Programs-En/{c_code}_{d_code}_{year}_en.pdf")
                    _add_url(f"https://www.{clean_domain}/shared/es/estudios/estudios-oficiales/grados/.galleries/Programs-Es/{c_code}_{d_code}_{year}_es.pdf")

    if url_directa:
        _add_url(url_directa)

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

        # 2. Temario / Units / Blocks / Section-bounded Contents
        in_contents = False
        for l in lines:
            if re.search(r"^(?:3\.\s*)?(?:COURSE\s+)?(?:CONTENTS|CONTENIDOS|TEMARIO|PROGRAMA|SYLLABUS)", l, re.IGNORECASE):
                in_contents = True
                continue
            if in_contents and re.search(r"^(?:4\.\s*)?(?:TEACHING|METODOLOGÍA|ACTIVIDADES|5\.\s*ASSESSMENT|EVALUACIÓN)", l, re.IGNORECASE):
                in_contents = False

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
            elif in_contents:
                clean_topic = re.sub(r"\b\d+\s*hours?\b.*$", "", l, flags=re.IGNORECASE).strip()
                clean_topic = re.sub(r"\b\d+\s*horas?\b.*$", "", clean_topic, flags=re.IGNORECASE).strip()
                if 4 <= len(clean_topic) <= 120 and not any(kw in clean_topic.lower() for kw in ["contents", "total number", "credits", "approved by", "school board"]):
                    if not is_spurious_or_administrative_subject(clean_topic):
                        if not any(t["titulo"] == clean_topic for t in res["temario"]):
                            res["temario"].append({
                                "orden": f"Bloque {len(res['temario']) + 1}",
                                "titulo": clean_topic,
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
                # Detectar instrumentos específicos (ej. PEI1, PEI2, PEF)
                elif re.search(r"\b(PEI\d*|PEF|Continuous assessment|Examen final|Evaluación continua)\b", l, re.IGNORECASE):
                    crit_nom = l.strip()
                    if 4 <= len(crit_nom) <= 80 and not any(ev["tarea"] == crit_nom for ev in res["sistema_evaluacion"]):
                        res["sistema_evaluacion"].append({
                            "tarea": crit_nom,
                            "instrumentos": "Criterio de evaluación oficial",
                            "ponderacion_porcentaje": 0.0
                        })

        if eval_lines and not res["criterios_evaluacion"]:
            res["criterios_evaluacion"] = "\n".join(eval_lines[:15])

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
# PROCESAMIENTO SECUENCIAL POR UNIVERSIDAD (CORTESÍA ÉTICA)
# =============================================================================

def _process_single_university_guides(u_code: str, degree_items: list, cache: SubjectGuideCache, downloader: RUCTDownloader, force: bool = False) -> dict:
    """
    Procesa de forma 100% secuencial y cortés todas las titulaciones de una única universidad.
    Garantiza que ningún dominio universitario reciba peticiones simultáneas.
    """
    stats = {
        "enriched_degrees": 0,
        "processed_guides": 0,
        "cached_hits": 0
    }
    revalidate_sources = bool(FULL_REVALIDATION or force)

    for item in degree_items:
        p_path = item["p_path"]
        data = item.get("data")
        if data is None:
            try:
                with open(p_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception as exc:
                logger.warning("No se pudo leer el plan %s: %s", p_path, exc)
                continue
        d_code = data.get("codigo_estudio", "")
        downloader.set_degree_context(d_code)
        u_web = data.get("web", "") or data.get("web_fuente_directa_url", "")
        plan = data.get("plan_estudios") or {}
        elementos = plan.get("elementos_curriculares") or []

        if not elementos:
            continue

        degree_modified = False

        for elem in elementos:
            asig_code = elem.get("codigo_asignatura") or elem.get("codigo")
            asig_name = elem.get("nombre_elemento", "")

            # 1. La caché sólo es respaldo. La URL conocida se vuelve a
            # resolver y consultar en cada ejecución para detectar cambios o
            # desplazamientos del contenido a otra URL.
            url_directa = elem.get("url_guia_docente")
            cached_data = cache.get(url=url_directa, u_code=u_code, asig_code=asig_code)
            if cached_data and not revalidate_sources:
                elem["guia_docente"] = cached_data
                stats["cached_hits"] += 1
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
            found_current_guide = False
            for c_url in candidate_urls:
                if getattr(downloader, "respect_robots", True):
                    allowed, _ = downloader.robots_policy.check(c_url)
                    if not allowed:
                        logger.info("[robots.txt] Guía docente omitida: %s", c_url)
                        continue
                resp = None
                try:
                    resp = downloader._request_with_retry(c_url, stream=True)
                    if resp and resp.status_code == 200:
                        c_type = resp.headers.get("Content-Type", "")
                        chunks, total = [], 0
                        for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                            if chunk:
                                total += len(chunk)
                                if total > MAX_RESPONSE_SIZE_BYTES:
                                    raise ValueError("Guía docente demasiado grande")
                                chunks.append(chunk)
                        body = b"".join(chunks)
                        downloader.store_response_content(c_url, resp, body)
                        parsed_guide = parse_subject_guide(c_url, body, c_type)
                        
                        has_content = (
                            len(parsed_guide.get("temario", [])) > 0 or
                            len(parsed_guide.get("sistema_evaluacion", [])) > 0 or
                            len(parsed_guide.get("profesorado", [])) > 0 or
                            len(parsed_guide.get("competencias", [])) > 0 or
                            bool(parsed_guide.get("resumen"))
                        )
                        if not has_content:
                            cache.mark_negative(c_url)
                            continue

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
                        elem["estado_guia_docente"] = "verificada"
                        elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                        stats["processed_guides"] += 1
                        degree_modified = True
                        found_current_guide = True
                        break
                except SkipUniversityException:
                    print(f" [AVISO CORTOCIRCUITO] Omitiendo guías de la universidad [{u_code}] por sobrecarga del servidor.")
                    break
                except Exception as e:
                    logger.debug(f"Error al descargar guía '{c_url}': {e}")
                finally:
                    if resp is not None:
                        try:
                            resp.close()
                        except Exception:
                            pass

            # Si ninguna fuente actual respondió o produjo contenido válido,
            # conservar la última guía fiable en vez de dejar un hueco.
            if not found_current_guide and cached_data:
                elem["guia_docente"] = cached_data
                elem["estado_guia_docente"] = "respaldo_ultima_fuente"
                elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                stats["cached_hits"] += 1
                degree_modified = True

        if degree_modified:
            atomic_json_dump(data, p_path)
            stats["enriched_degrees"] += 1

    return stats


def _process_university_guides_isolated(u_code, degree_items, cache, force=False, ledger=None):
    """Procesa una universidad con sesión y estado de circuit breaker propios."""
    downloader = RUCTDownloader(ledger=ledger, phase="fase1_parte4")
    downloader.reset_university_context(str(u_code))
    try:
        return _process_single_university_guides(u_code, degree_items, cache, downloader, force)
    finally:
        downloader.close()
        cache.close()


# =============================================================================
# EJECUTOR PRINCIPAL DE LA FASE 1 - PARTE 4
# =============================================================================

def run_phase1_part4(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
    target_univ_code: str = None,
    limit_univ: int = None,
    workers: int = None,
) -> dict:
    """
    FASE 1 - PARTE 4: Extracción de temarios, evaluación y contenido de guías docentes.
    Agrupa los planes de estudio por universidad y los procesa en paralelo (hasta max_workers universidades a la vez),
    manteniendo estricta cortesía secuencial por dominio.
    """
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 4: GUÍAS DOCENTES Y TEMARIOS EEES")
    print("======================================================================")

    if limit_universities is None:
        limit_universities = limit_univ
    if max_workers is None:
        max_workers = workers
    if max_workers is None:
        max_workers = WEB_CRAWLER_WORKERS
    max_workers = max(1, int(max_workers))

    cache = SubjectGuideCache()
    ledger = CrawlLedger()
    try:
        if not os.path.exists(PLANES_DIR):
            print(f" -> [AVISO] Directorio de planes {PLANES_DIR} no existe en disco. Omitiendo enriquecimiento.")
            return {
                "status": "skipped",
                "reason": "missing_plans_directory",
                "total_planes_inspeccionados": 0,
                "asignaturas_enriquecidas": 0,
            }

        plan_files = iter_plan_files(PLANES_DIR)
        universities = load_json_safe(UNIVERSIDADES_JSON, default=[])
        universities_map = {str(u.get("codigo")): u for u in universities if isinstance(u, dict) and u.get("codigo")} if isinstance(universities, list) else {}

        total_degrees = len(plan_files)
        print(f" -> {total_degrees} planes de estudio a inspeccionar en disco.")

        # Agrupar titulaciones por universidad para procesamiento concurrente seguro
        univ_groups = {}
        seen_univs = set()
        degrees_per_university = {}
        total_enqueued = 0

        for p_path in plan_files:
            try:
                with open(p_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            u_code = data.get("universidad_codigo", "000")
            if TARGET_UNIVERSITY_CODES and str(u_code).zfill(3) not in TARGET_UNIVERSITY_CODES:
                continue
            if not data.get("web"):
                university_meta = universities_map.get(str(u_code))
                if university_meta and university_meta.get("web"):
                    data["web"] = university_meta["web"]

            if target_univ_code and str(u_code).zfill(3) != str(target_univ_code).zfill(3):
                continue

            if limit_universities is not None and len(seen_univs) >= max(0, limit_universities) and u_code not in seen_univs:
                continue

            if limit_degrees is not None and degrees_per_university.get(u_code, 0) >= max(0, limit_degrees):
                continue

            if u_code:
                seen_univs.add(u_code)

            if u_code not in univ_groups:
                univ_groups[u_code] = []

            univ_groups[u_code].append({
                "p_path": p_path,
            })
            degrees_per_university[u_code] = degrees_per_university.get(u_code, 0) + 1
            total_enqueued += 1

        print(f" -> {len(univ_groups)} universidades agrupadas para procesamiento en paralelo con {max_workers} trabajadores.")

        processed_guides = 0
        cached_hits = 0
        enriched_degrees = 0
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_university_guides_isolated, u_code, items, cache, force, ledger): u_code
                for u_code, items in univ_groups.items()
            }

            for completed, future in enumerate(as_completed(futures), start=1):
                u_code = futures[future]
                try:
                    res = future.result()
                    processed_guides += res.get("processed_guides", 0)
                    cached_hits += res.get("cached_hits", 0)
                    enriched_degrees += res.get("enriched_degrees", 0)
                except Exception as exc:
                    print(f" [ERROR PARTE 4] Excepción en universidad [{u_code}]: {exc}")
                if progress_emitter is not None:
                    progress_emitter.update_university(
                        completed,
                        len(univ_groups),
                        str(u_code),
                        str(u_code),
                    )

        elapsed = round(time.time() - start_time, 2)
        print("\n" + "=" * 70)
        print("      FASE 1 - PARTE 4 FINALIZADA CON ÉXITO")
        print("======================================================================")
        print(f" -> Titulaciones enriquecidas con temario: {enriched_degrees}")
        print(f" -> Guías docentes descargadas de la red:  {processed_guides}")
        print(f" -> Aciertos en caché SQLite WAL (0ms):    {cached_hits}")
        print(f" -> Tiempo total de procesamiento:        {elapsed}s\n")

        return {
            "status": "completed",
            "plans_inspected": total_enqueued,
            "enriched_degrees": enriched_degrees,
            "processed_guides": processed_guides,
            "cached_hits": cached_hits,
            "elapsed_s": elapsed
        }
    finally:
        try:
            cache.close()
        except Exception:
            pass
        try:
            ledger.close()
        except Exception:
            pass
