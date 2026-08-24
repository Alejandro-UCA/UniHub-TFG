import os
import sys
import re
import json
import time
import sqlite3
import hashlib
import logging
from urllib.parse import urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from config import (
    PLANES_DIR,
    DATA_DIR,
    USER_AGENT,
    REQUEST_DELAY,
    ASYNC_PREFETCH_WORKERS
)
from downloader import RUCTDownloader
from checkpoint import atomic_json_dump

logger = logging.getLogger(__name__)

CACHE_GUIAS_DB = os.path.join(DATA_DIR, "cache_guias_docentes.db")


class SubjectGuideCache:
    """
    Gestor de persistencia en SQLite WAL para guías docentes.
    Garantiza deduplicación institucional (N:M): asignaturas compartidas entre grados
    (ej. Cálculo de la UCA) se descargan y analizan exactamente UNA sola vez.
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_guias_univ ON guias_docentes(universidad_codigo);")
            conn.commit()

    def get(self, url: str) -> dict:
        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT datos_json FROM guias_docentes WHERE url_hash = ?", (url_hash,))
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
                """, (url_hash, url, u_code, asig_code, nombre, json.dumps(data, ensure_ascii=False)))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error al escribir caché de guía docente: {e}")


# =============================================================================
# PARSERS ESPECIALIZADOS DE GUÍAS DOCENTES (EEES / BOLONIA)
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
            res["nombre_asignatura"] = m_t.group(2).strip()

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
                # Parsear contenido del tema / bloque
                td_text = tds[1].get_text(separator="\n", strip=True)
                lineas = [l.strip() for l in td_text.splitlines() if l.strip()]
                if lineas:
                    bloque_titulo = lineas[0]
                    subtemas = lineas[1:] if len(lineas) > 1 else []
                    res["temario"].append({
                        "orden": orden,
                        "titulo": bloque_titulo,
                        "contenidos": subtemas
                    })

    # Sistema de evaluación (Tabla id="procedimientos_evaluacion_nuevo" o similar)
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

    # Criterios de evaluación e IA Generativa (input name="criterios_evaluacion")
    crit_input = soup.find("input", attrs={"name": "criterios_evaluacion"})
    if crit_input and crit_input.get("value"):
        raw_val = crit_input["value"]
        clean_crit = BeautifulSoup(raw_val, "html.parser").get_text(separator="\n", strip=True)
        res["criterios_evaluacion"] = clean_crit

    # Profesorado (Tabla id="profesorado")
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

    # Resultados de aprendizaje
    res_table = soup.find("table", id="resultados_aprendizaje")
    if res_table:
        for tr in res_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                res["resultados_aprendizaje"].append(tds[1].get_text(strip=True))

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

    # Intentar extraer nombre de asignatura del título
    h1 = soup.find("h1")
    if h1:
        res["nombre_asignatura"] = h1.get_text(strip=True)

    # Búsqueda por encabezados de sección estándar EEES
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
                    if txt and 4 <= len(txt) <= 200:
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


def parse_subject_guide(url: str, html: str) -> dict:
    """
    Enrutador inteligente para procesar la guía docente según el portal de origen.
    """
    soup = BeautifulSoup(html, "html.parser")
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
    Recorre los planes de estudio en planes_estudio/*.json, descarga las guías docentes
    mediante deduplicación en SQLite WAL y almacena el contenido enriquecido.
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
            url_guia = elem.get("url_guia_docente")
            # Si no tiene url_guia directa pero conocemos el portal UCA por código de titulación
            if not url_guia and u_code == "025" and elem.get("codigo_asignatura"):
                url_guia = f"https://asignaturas.uca.es/2025-26/{elem['codigo_asignatura']}"

            if not url_guia:
                continue

            # 1. Comprobar si ya está en caché SQLite WAL
            cached_data = cache.get(url_guia)
            if cached_data and not force:
                elem["guia_docente"] = cached_data
                cached_hits += 1
                degree_modified = True
                continue

            # 2. Descargar guía docente en vivo
            try:
                time.sleep(REQUEST_DELAY)
                headers = {"User-Agent": USER_AGENT}
                resp = downloader.session.get(url_guia, headers=headers, timeout=15)
                if resp.status_code == 200:
                    parsed_guide = parse_subject_guide(url_guia, resp.text)
                    cache.set(
                        url=url_guia,
                        data=parsed_guide,
                        u_code=u_code,
                        asig_code=parsed_guide.get("codigo_asignatura", ""),
                        nombre=elem.get("nombre_elemento", "")
                    )
                    elem["guia_docente"] = parsed_guide
                    processed_guides += 1
                    degree_modified = True
            except Exception as e:
                logger.warning(f"Error al descargar guía '{url_guia}': {e}")

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
