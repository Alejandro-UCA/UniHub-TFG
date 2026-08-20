import os
import io
import re
import hashlib
from datetime import datetime
import xlrd
from bs4 import BeautifulSoup
import pdfplumber
import pypdf
from downloader import normalize_url
from functools import lru_cache

# -----------------------------------------------------------------------------
# GLOBAL PRE-COMPILED REGEX PATTERNS (OPT-02: Pre-compilación de Regex)
# -----------------------------------------------------------------------------
RE_CREDIT_SUMMARY = [
    ("Formación Básica", re.compile(r"(?:formaci[oó]n b[aá]sica|fb)\s*[:\.\-]?\s*(\d+)", re.IGNORECASE)),
    ("Obligatorias", re.compile(r"(?:obligatoria[s]?|ob)\s*[:\.\-]?\s*(\d+)", re.IGNORECASE)),
    ("Optativas", re.compile(r"(?:optativa[s]?|op)\s*[:\.\-]?\s*(\d+)", re.IGNORECASE)),
    ("Prácticas Externas", re.compile(r"(?:pr[aá]ctica[s]?|pe)\s*[:\.\-]?\s*(\d+)", re.IGNORECASE)),
    ("Trabajo Fin de Grado / Máster", re.compile(r"(?:trabajo fin de|tfg|tfm)\s*[:\.\-]?\s*(\d+)", re.IGNORECASE)),
    ("Créditos Totales", re.compile(r"(?:total|cr[eé]ditos totales)\s*[:\.\-]?\s*(\d+)", re.IGNORECASE))
]

RE_ECTS_NUMBER = re.compile(r"\b(\d+(?:[\.,]\d+)?)\b")
RE_CURSO_NUM = re.compile(r"\b[1-6][ºº°]?\b")
RE_LEGAL_NOISE = re.compile(r"^(decreto|orden|bocm|boe|decreto-ley|ley|real decreto|resolución|ordenatorio)\b", re.IGNORECASE)
RE_ECTS_CLEAN = re.compile(r"(\d+(?:[\.,]\d+)?)")
RE_TEXT_SUBJECT_LINE = re.compile(r"^([A-ZÁÉÍÓÚÑa-záéíóúñ0-9\s\-\,\.\(\)]{5,70})\s+(\d+(?:[\.,]\d+)?)\s+(FB|OB|OP|PE|TFG|TFM|Obligatoria|Optativa|Básica)\b", re.IGNORECASE)
RE_MULTIPLE_SPACES = re.compile(r"\s+")
RE_PARENTHESES_STRIP = re.compile(r"\s*\(.*?\)")


def unreverse_text(text: str) -> str:
    """
    Detecta y corrige texto espejado/invertido proveniente de matrices tipográficas inversas en PDFs antiguos.
    Ejemplo: 'aígolocisP ne odarG' -> 'Grado en Psicología'.
    """
    if not text:
        return ""
    t = str(text).strip()
    if any(t.endswith(rev) for rev in ["odarG", "retsáM", "retsaM", "aígolocisP", "acitámrofnI", "aicneiC", "ohcereD"]) or any(rev in t for rev in [" ne odarG", " ne retsáM", " aL ne "]):
        return t[::-1]
    return t


def sanitize_string_value(val: str) -> str:
    """
    Sanea de forma universal y transversal cualquier valor de texto de universidades, titulaciones y planes:
    1. Corrige texto invertido/espejado.
    2. Elimina caracteres invisibles (\u00a0, \u200b) y saltos de línea.
    3. Colapsa espacios múltiples en un único espacio.
    4. Elimina puntuación final huérfana (. , ; :).
    """
    if not val:
        return ""
    s = unreverse_text(str(val).strip())
    s = re.sub(r"[\u00a0\u200b\t\r\n]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.rstrip(";:,").strip()


def parse_universities_xls(filepath: str) -> list:
    """
    Parses the XLS file downloaded from RUCT containing the list of universities.
    Returns a list of dictionaries with cleaned university details.
    """
    wb = xlrd.open_workbook(filepath)
    sheet = wb.sheet_by_index(0)
    
    if sheet.nrows == 0:
        return []
    
    headers = [str(cell).strip() for cell in sheet.row_values(0)]
    universities = []
    
    for r in range(1, sheet.nrows):
        row = sheet.row_values(r)
        row_dict = {}
        for idx, header in enumerate(headers):
            val = str(row[idx]).strip() if idx < len(row) else ""
            if header in ["Código", "CÃ³digo"] and val.endswith(".0"):
                val = val[:-2].zfill(3)
            row_dict[header] = val
        
        code = row_dict.get("Código", row_dict.get("CÃ³digo", ""))
        name = row_dict.get("Universidad", "")
        tipo = row_dict.get("Tipo", "")
        ccaa = row_dict.get("Comunidad Autónoma", row_dict.get("Comunidad AutÃ³noma", ""))
        url = row_dict.get("URL", "")
        
        if code and name:
            universities.append({
                "codigo": code.zfill(3),
                "nombre": sanitize_string_value(name),
                "tipo": sanitize_string_value(tipo),
                "comunidad_autonoma": sanitize_string_value(ccaa),
                "municipio": sanitize_string_value(row_dict.get("Municipio", "")),
                "provincia": sanitize_string_value(row_dict.get("Provincia", "")),
                "web": url.strip(),
                "email": row_dict.get("EMail", "").strip(),
                "telefono": sanitize_string_value(row_dict.get("Teléfono 1", row_dict.get("TelÃ©fono 1", "")))
            })
            
    # Ordenación prioritaria: Universidades Públicas primero, Privadas después
    def get_univ_priority(u):
        tipo_lower = u.get("tipo", "").lower()
        if "pública" in tipo_lower or "publica" in tipo_lower:
            return 0
        return 1

    universities.sort(key=get_univ_priority)
    return universities


def parse_degrees_xls(filepath: str) -> list:
    """
    Parses the XLS file downloaded from RUCT for a specific university.
    1. FILTERS OUT INACTIVE / EXTINGUISHED DEGREES.
    2. DEDUPLICATES RENOVATED DEGREES within the same university:
       If multiple active versions of the same title exist, keeps ONLY the latest / renovated version.
    """
    wb = xlrd.open_workbook(filepath)
    sheet = wb.sheet_by_index(0)
    
    if sheet.nrows == 0:
        return []
    
    headers = [str(cell).strip() for cell in sheet.row_values(0)]
    raw_active_degrees = []
    
    for r in range(1, sheet.nrows):
        row = sheet.row_values(r)
        row_dict = {}
        for idx, header in enumerate(headers):
            val = str(row[idx]).strip() if idx < len(row) else ""
            if header in ["Código", "CÃ³digo"] and val.endswith(".0"):
                val = val[:-2]
            row_dict[header] = val
        
        code = row_dict.get("Código") or row_dict.get("CÃ³digo") or ""
        title = row_dict.get("Título") or row_dict.get("TÃ­tulo") or ""
        nivel = row_dict.get("Nivel académico") or row_dict.get("Nivel acadÃ©mico") or ""
        estado = (
            row_dict.get("Estado") or 
            row_dict.get("Estado del título") or 
            row_dict.get("Estado del tÃ­tulo") or 
            row_dict.get("Estado del estudio") or 
            row_dict.get("Situación") or 
            row_dict.get("SituaciÃ³n") or ""
        )
        
        # Helper para normalización estricta de acentos y distorsiones de codificación UTF-8
        import unicodedata
        def normalize_text(text: str) -> str:
            if not text:
                return ""
            t = text.lower().strip()
            t = t.replace("Ã³", "o").replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i").replace("Ãº", "u").replace("Ã±", "n")
            t = unicodedata.normalize('NFKD', t)
            t = ''.join(c for c in t if not unicodedata.combining(c))
            return t

        estado_norm = normalize_text(estado)
        nivel_norm = normalize_text(nivel)
        title_norm = normalize_text(title)

        # 1. LISTA NEGRA AMPLIADA (Términos que denotan inactividad, extinción o desestimación)
        blacklist = [
            "extinguid", "extincion", "extinta", "extinto",
            "no vigente", "sin docencia", "baja",
            "derogad", "cancelad", "eliminad", "revocad",
            "suspendid", "caducad", "desestimad", "sustituid",
            "no impartid", "sin efecto", "cierre", "cerrad", "archivo"
        ]
        has_blacklist = any(term in estado_norm for term in blacklist)

        # 2. LISTA BLANCA ESTRICTA (Términos explícitos de actividad, publicación en BOE o autorización real)
        whitelist = [
            "vigente", 
            "impartiendose", 
            "autorizad", 
            "renovad", 
            "acreditad", 
            "alta",
            "publicad",
            "b.o.e",
            "boe",
            "inscrit"
        ]
        has_whitelist = any(term in estado_norm for term in whitelist)

        # 3. RECHAZO DE NIVELES ACADÉMICOS Y TÍTULOS PRE-BOLONIA EXTEXTOS (LRU / RD 56/2005)
        legacy_levels = ["solo segundo ciclo", "ciclo corto", "ciclo largo", "primer ciclo", "primer y segundo ciclo", "pre-bolonia", "rd 56/2005"]
        is_legacy_level = any(leg in nivel_norm for leg in legacy_levels)

        legacy_title_prefixes = ["licenciado", "licenciada", "diplomado", "diplomada", "ingeniero tecnico", "ingeniera tecnica", "arquitecto tecnico", "arquitecta tecnica"]
        is_legacy_title = any(title_norm.startswith(prefix) for prefix in legacy_title_prefixes)

        # La titulación debe pertenecer a la Lista Blanca, NO estar en Lista Negra y NO ser un plan antiguo Pre-Bolonia (LRU)
        if code and title and has_whitelist and not has_blacklist and not is_legacy_level and not is_legacy_title:
            raw_active_degrees.append({
                "codigo_estudio": code.strip(),
                "titulo": sanitize_string_value(title),
                "nivel_academico": sanitize_string_value(nivel),
                "estado": sanitize_string_value(estado)
            })

    # Deduplicate renovated degrees within the same university
    def normalize_title(full_title: str) -> str:
        base = full_title.split(" por la ")[0].split(" por ")[0].strip().lower()
        return re.sub(r"\s+", " ", base)

    grouped_degrees = {}
    for deg in raw_active_degrees:
        norm_title = normalize_title(deg["titulo"])
        if norm_title not in grouped_degrees:
            grouped_degrees[norm_title] = deg
        else:
            existing_deg = grouped_degrees[norm_title]
            try:
                code_new = int(deg["codigo_estudio"])
                code_existing = int(existing_deg["codigo_estudio"])
                if code_new > code_existing:
                    grouped_degrees[norm_title] = deg
            except ValueError:
                pass

    return list(grouped_degrees.values())


def parse_degree_detail_html(html_content: str) -> dict:
    """
    Parses the HTML of the degree detail page to verify real-time status and extract all BOE PDF links.
    Returns a dictionary with is_extinct (bool), exact status text, and candidate BOE links.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    full_text_lower = soup.get_text().lower()

    # Extraer el texto exacto del estado desde la celda de la tabla HTML (ej. Estado del título:)
    status_text = ""
    for tr in soup.find_all("tr"):
        th = tr.find(["th", "td"])
        if th and any(k in th.get_text().lower() for k in ["estado", "situación", "situacion", "vigencia"]):
            tds = tr.find_all("td")
            if tds:
                status_text = tds[-1].get_text(strip=True)
                break

    # Lista de términos de extinción e inactividad en la ficha HTML oficial en vivo
    extinction_markers = [
        "extinguid", "extincion", "extinta", "extinto",
        "sin docencia", "baja", "derogad", "cancelad",
        "eliminad", "revocad", "suspendid", "caducad",
        "desestimad", "sustituid", "no impartid", "sin efecto",
        "cierre", "cerrad", "archivo", "rd 56/2005"
    ]

    is_extinct = any(marker in full_text_lower for marker in extinction_markers) or any(marker in status_text.lower() for marker in extinction_markers)

    if is_extinct:
        return {
            "is_extinct": True,
            "status_text": status_text or "Extinguida",
            "latest_boe_url": None,
            "boe_date": None,
            "all_boe_links": [],
            "all_boe_candidates": []
        }

    boe_candidates = []
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        
        if "boe.es" in href.lower() or "boe" in text.lower() or ".pdf" in href.lower():
            # Solución 3: Excluir enlaces y documentos anteriores a 2009 (Planes Pre-Bolonia como licenciaturas o diplomaturas derogadas)
            if re.search(r"/(19\d\d|200[0-8])/", href) or re.search(r"A\d{5}-\d{5}\.pdf", href, re.IGNORECASE):
                continue

            date_obj = None
            text_date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
            if text_date_match:
                d, m, y = text_date_match.groups()
                try:
                    date_obj = datetime(int(y), int(m), int(d))
                except ValueError:
                    pass
            
            if not date_obj:
                url_date_match = re.search(r"(\d{4})/(\d{2})/(\d{2})", href)
                if url_date_match:
                    y, m, d = url_date_match.groups()
                    try:
                        date_obj = datetime(int(y), int(m), int(d))
                    except ValueError:
                        pass
            
            # Descartar BOEs históricos con fecha anterior a 2009
            if date_obj and date_obj < datetime(2009, 1, 1):
                continue

            if href.startswith("/"):
                href = "https://www.boe.es" + href

            # Clean malformed double protocol prefixes using centralized normalize_url
            href = normalize_url(href)
                
            boe_candidates.append({
                "url": href,
                "text": text,
                "date": date_obj,
                "boe_date": date_obj.strftime("%Y-%m-%d") if date_obj else None
            })
            
    if not boe_candidates:
        return {"latest_boe_url": None, "boe_date": None, "all_boe_links": [], "all_boe_candidates": []}
    
    sorted_candidates = sorted(
        boe_candidates,
        key=lambda c: c["date"] if c["date"] is not None else datetime(1970, 1, 1),
        reverse=True
    )
    
    latest = sorted_candidates[0]
        
    return {
        "latest_boe_url": latest["url"],
        "boe_date": latest["boe_date"],
        "all_boe_links": [c["url"] for c in sorted_candidates],
        "all_boe_candidates": sorted_candidates
    }


def normalize_cuatrimestre(cuat_raw: str) -> str:
    """
    Normaliza el cuatrimestre a un formato estándar legible (1C, 2C, Anual)
    preservando siempre de forma segura el valor original si no coincide exactamente,
    garantizando que ninguna asignatura quede huérfana o perdida (Solución 3).
    """
    if not cuat_raw:
        return ""
    c_str = str(cuat_raw).strip().lower()
    
    # 1. Anual
    if any(k in c_str for k in ["anual", "an", "1 y 2", "1 y 2º", "1-2", "curso completo", "anuales"]):
        return "Anual"
    
    # 2. Primer Cuatrimestre / Semestres impares (1, 3, 5, 7)
    if (
        c_str in ["1", "1º", "1.º", "1c", "1s", "1er", "primer", "primero", "1.er", "3", "5", "7", "s1", "c1"]
        or "1er" in c_str or "1º cuat" in c_str or "1.º cuat" in c_str or "1.º sem" in c_str 
        or "1er sem" in c_str or "primer cuat" in c_str or "primer sem" in c_str
        or "semestre 1" in c_str or "semestre 3" in c_str or "semestre 5" in c_str or "semestre 7" in c_str
        or "cuatrimestre 1" in c_str or "cuatrimestre 3" in c_str or "cuatrimestre 5" in c_str or "cuatrimestre 7" in c_str
    ):
        return "1C"
        
    # 3. Segundo Cuatrimestre / Semestres pares (2, 4, 6, 8)
    if (
        c_str in ["2", "2º", "2.º", "2c", "2s", "2do", "2º cuat", "2.º cuat", "2.º sem", "2do sem", "segundo", "segundo cuat", "segundo sem", "4", "6", "8", "s2", "c2"]
        or "2º" in c_str or "2do" in c_str or "segundo" in c_str
        or "semestre 2" in c_str or "semestre 4" in c_str or "semestre 6" in c_str or "semestre 8" in c_str
        or "cuatrimestre 2" in c_str or "cuatrimestre 4" in c_str or "cuatrimestre 6" in c_str or "cuatrimestre 8" in c_str
    ):
        return "2C"
        
    # Fallback seguro: mantener el texto original limpio
    return str(cuat_raw).strip()


def normalize_curso(curso_raw: str, current_materia: str = "", ects_val: float = 6.0) -> tuple:
    """
    Normaliza el campo curso de forma estricta (1, 2, 3, 4, 5, 6 o vacío).
    Si curso_raw contiene texto descriptivo de materia o asignatura (ej. 'Comunicación Oral y Escrita.'),
    lo traslada a la materia si esta estaba vacía, y limpia el curso a "".
    Retorna una tupla (curso_limpio, materia_actualizada).
    """
    if not curso_raw:
        return "", current_materia
    c_str = str(curso_raw).strip()
    c_low = c_str.lower()
    
    # 1. Comprobar desalineación de créditos ECTS (ej. si curso_raw es simplemente "6" o "5" igual a ects_val)
    if c_str.isdigit():
        c_val_int = int(c_str)
        if c_val_int == int(ects_val) and c_val_int >= 5 and not any(k in c_low for k in ["curso", "año", "curs", "º", "er", "to"]):
            return "", current_materia

    # 2. Detectar números ordinales o textuales en español/catalán (1º, 1er, primer, segon, etc.)
    if c_low in ["1", "1º", "1.º", "1er", "primer", "primero", "primer curso", "1r", "1r curs", "i", "curso 1", "año 1"]:
        return "1", current_materia
    if c_low in ["2", "2º", "2.º", "2do", "2n", "segundo", "segon", "segundo curso", "2n curs", "ii", "curso 2", "año 2"]:
        return "2", current_materia
    if c_low in ["3", "3º", "3.º", "3er", "3r", "tercer", "tercero", "tercer curso", "3r curs", "iii", "curso 3", "año 3"]:
        return "3", current_materia
    if c_low in ["4", "4º", "4.º", "4to", "4t", "cuarto", "quart", "cuarto curso", "4t curs", "iv", "curso 4", "año 4"]:
        return "4", current_materia
    if c_low in ["5", "5º", "5.º", "5to", "5è", "quinto", "cinquè", "quinto curso", "5è curs", "v", "curso 5", "año 5"]:
        return "5", current_materia
    if c_low in ["6", "6º", "6.º", "6to", "6è", "sexto", "sisè", "sexto curso", "6è curs", "vi", "curso 6", "año 6"]:
        return "6", current_materia

    # 3. Buscar si contiene un dígito aislado 1-6
    m = re.search(r"\b([1-6])\b", c_str)
    if m:
        c_num = int(m.group(1))
        if c_num == int(ects_val) and c_num >= 5 and not any(k in c_low for k in ["curso", "año", "curs"]):
            return "", current_materia
        return str(c_num), current_materia

    # 4. Si curso_raw es un texto largo (> 3 caracteres alfabéticos) y no es un curso numérico,
    # es un nombre de materia/módulo desalineado por la tabla del PDF
    if re.search(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}", c_str):
        if not current_materia or current_materia.strip() == "":
            current_materia = c_str
        return "", current_materia

    return "", current_materia


def sanitize_subject_name(raw_name: str) -> str:
    """
    Limpia y normaliza el nombre de una asignatura:
    1. Elimina texto invertido proveniente de matrices tipográficas.
    2. Elimina puntos guía de índice y rellenos tipográficos ('......').
    3. Separa códigos numéricos de secretaría de cabecera ('40147 - CÁLCULO I' -> 'CÁLCULO I').
    4. Elimina espacios múltiples o caracteres invisibles (\u00a0, \u200b).
    5. Elimina puntuación innecesaria al final (.,;:-).
    """
    if not raw_name:
        return ""
    name = unreverse_text(raw_name.strip())
    
    # Eliminar caracteres invisibles y colapsar espacios múltiples
    name = re.sub(r"[\u00a0\u200b\t]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    
    # Eliminar puntos guía de índice al final o en el cuerpo ('......')
    name = re.sub(r"\s*\.{2,}\s*", " ", name).strip()
    
    # Separar códigos numéricos de secretaría iniciales (ej: '40147 - CÁLCULO I' -> 'CÁLCULO I')
    m_code = re.match(r"^(\d{4,6}|[A-Z]\d{3,4})\s*[-–—]\s*(.+)$", name)
    if m_code:
        name = m_code.group(2).strip()
        
    # Eliminar puntuación sobrante de cierre de párrafo
    name = name.rstrip(".,;:- ")
    return name


def parse_boe_pdf(pdf_filepath) -> dict:
    """
    Extracts METICULOUS curriculum data (resumen creditos, asignaturas, modulos, materias, 
    unidades formativas, bloques, ECTS, carácter, curso, cuatrimestre) from a BOE PDF.
    Supports both disk file path (str) and in-memory bytes/io.BytesIO objects (OPT-04).
    Calculates SHA256 digest of PDF stream for negative caching (OPT-06).
    """
    resumen_creditos = {}
    elementos_curriculares = []
    raw_text_parts = []

    # Prepare stream or file source
    if isinstance(pdf_filepath, bytes):
        pdf_stream = io.BytesIO(pdf_filepath)
        pdf_sha256 = hashlib.sha256(pdf_filepath).hexdigest()
    elif isinstance(pdf_filepath, io.BytesIO):
        pdf_stream = pdf_filepath
        pdf_bytes = pdf_filepath.getvalue()
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    else:
        pdf_stream = pdf_filepath
        pdf_sha256 = None
        if os.path.exists(pdf_filepath):
            try:
                h = hashlib.sha256()
                with open(pdf_filepath, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                pdf_sha256 = h.hexdigest()
            except Exception:
                pass

    try:
        reader = pypdf.PdfReader(pdf_stream)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                raw_text_parts.append(text)
    except Exception as e:
        print(f"   [AVISO] error pypdf: {e}")

    full_text = "\n".join(raw_text_parts)

    # Fallback for scanned image PDFs: Use local OCR when vector text layer is missing or empty
    if len(full_text.strip()) < 50 and isinstance(pdf_filepath, str) and os.path.exists(pdf_filepath):
        try:
            from ocr_parser import OCRPDFParser
            ocr_parser = OCRPDFParser()
            ocr_text = ocr_parser.extract_text_via_ocr(pdf_filepath)
            if len(ocr_text.strip()) >= 50:
                full_text = ocr_text
        except Exception:
            pass

    # 1. Parse Credit Summary Table (using pre-compiled RE_CREDIT_SUMMARY)
    for label, pattern in RE_CREDIT_SUMMARY:
        match = pattern.search(full_text)
        if match:
            resumen_creditos[label] = match.group(1)

    # 2. Extract Structured Curriculum Tables with pdfplumber (OPT-02)
    try:
        if isinstance(pdf_stream, io.BytesIO):
            pdf_stream.seek(0)

        with pdfplumber.open(pdf_stream) as pdf:
            current_modulo = ""
            current_materia = ""

            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    subject_col_idx = -1
                    materia_col_idx = -1
                    ects_col_idx = -1
                    caracter_col_idx = -1
                    curso_col_idx = -1
                    cuatrimestre_col_idx = -1
                    
                    for row in table:
                        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                            continue
                        
                        clean_row = [RE_MULTIPLE_SPACES.sub(" ", str(cell).strip()) if cell else "" for cell in row]
                        row_str = " ".join(clean_row).lower()

                        # Detect header rows to establish column mapping
                        if any(hk in row_str for hk in ["asignatura", "denominaci", "materia", "crédito", "credito", "ects", "carácter", "caracter", "curso", "módulo", "modulo"]):
                            for idx, cell_str in enumerate(clean_row):
                                c_lower = cell_str.lower()
                                if any(kw in c_lower for kw in ["asignatura", "denominaci", "nombre", "actividad formativa", "unidad curricular"]):
                                    subject_col_idx = idx
                                elif any(kw in c_lower for kw in ["materia", "módulo", "modulo"]) and "asignatura" not in c_lower:
                                    materia_col_idx = idx
                                elif any(kw in c_lower for kw in ["crédito", "credito", "ects"]):
                                    ects_col_idx = idx
                                elif any(kw in c_lower for kw in ["carácter", "caracter", "tipo", "tipología"]):
                                    caracter_col_idx = idx
                                elif any(kw in c_lower for kw in ["curso", "año"]):
                                    curso_col_idx = idx
                                elif any(kw in c_lower for kw in ["cuatrimestre", "semestre", "periodo", "temporalidad"]):
                                    cuatrimestre_col_idx = idx
                            continue

                        if "módulo" in row_str or "modulo" in row_str:
                            current_modulo = clean_row[0] if clean_row else ""
                            continue
                        if "materia" in row_str and len(clean_row) == 1:
                            current_materia = clean_row[0] if clean_row else ""
                            continue

                        # Check for subject row containing ECTS credit numbers
                        ects_match = None
                        caracter = "OB"
                        curso = ""
                        cuatrimestre = ""

                        # If specific columns were mapped
                        if ects_col_idx != -1 and ects_col_idx < len(clean_row) and clean_row[ects_col_idx]:
                            m = RE_ECTS_NUMBER.search(clean_row[ects_col_idx])
                            if m:
                                ects_match = m.group(1)

                        if caracter_col_idx != -1 and caracter_col_idx < len(clean_row) and clean_row[caracter_col_idx]:
                            c_cell = clean_row[caracter_col_idx].lower()
                            if "básica" in c_cell or "basica" in c_cell or "fb" in c_cell:
                                caracter = "FB"
                            elif "optativa" in c_cell or "op" in c_cell:
                                caracter = "OP"
                            elif "práctica" in c_cell or "practica" in c_cell or "pe" in c_cell or "externa" in c_cell:
                                caracter = "PE"
                            elif any(k in c_cell for k in ["tfg", "tfm", "trabajo fin", "trabajo de fin", "trabajo final", "proyecto fin", "proyecto de fin"]):
                                caracter = "TFG/TFM"

                        if curso_col_idx != -1 and curso_col_idx < len(clean_row):
                            curso = clean_row[curso_col_idx]

                        if cuatrimestre_col_idx != -1 and cuatrimestre_col_idx < len(clean_row):
                            cuatrimestre = clean_row[cuatrimestre_col_idx]

                        # Fallback search across all cells if not mapped
                        for cell in clean_row:
                            if not ects_match:
                                m = RE_ECTS_NUMBER.search(cell)
                                if m:
                                    try:
                                        if float(m.group(1).replace(",", ".")) in [1, 1.5, 2, 3, 4, 4.5, 5, 6, 7.5, 8, 9, 10, 12, 14, 15, 18, 20, 24, 30]:
                                            ects_match = m.group(1)
                                    except ValueError:
                                        pass

                            cell_lower = cell.lower()
                            if caracter == "OB":
                                if "básica" in cell_lower or "basica" in cell_lower or "fb" in cell_lower:
                                    caracter = "FB"
                                elif "optativa" in cell_lower or "op" in cell_lower:
                                    caracter = "OP"
                                elif "práctica" in cell_lower or "practica" in cell_lower or "pe" in cell_lower or "externa" in cell_lower:
                                    caracter = "PE"
                                elif any(k in cell_lower for k in ["tfg", "tfm", "trabajo fin", "trabajo de fin", "trabajo final", "proyecto fin", "proyecto de fin"]):
                                    caracter = "TFG/TFM"

                            if not curso and RE_CURSO_NUM.search(cell):
                                curso = cell
                            if not cuatrimestre and ("cuatrimestre" in cell_lower or "semestre" in cell_lower):
                                cuatrimestre = cell

                        # Identify subject name column
                        final_subject_name = ""
                        if subject_col_idx != -1 and subject_col_idx < len(clean_row):
                            final_subject_name = clean_row[subject_col_idx]
                        elif len(clean_row) > 1 and (len(clean_row[0]) <= 4 or RE_CURSO_NUM.match(clean_row[0]) or clean_row[0].isdigit()) and len(clean_row[1]) > 3:
                            final_subject_name = clean_row[1]
                        elif len(clean_row) > 0:
                            final_subject_name = clean_row[0]

                        # If materia is in column 0 and subject is in column 1
                        if materia_col_idx != -1 and materia_col_idx < len(clean_row):
                            current_materia = clean_row[materia_col_idx]

                        # Fallback heuristic: if subject column equals current materia, use adjacent column
                        if len(clean_row) > 1 and final_subject_name.lower() == current_materia.lower():
                            final_subject_name = clean_row[1]

                        final_subject_name = sanitize_subject_name(final_subject_name)
                        # Strict validation of subject name
                        if (
                            final_subject_name 
                            and len(final_subject_name) > 3 
                            and not RE_LEGAL_NOISE.search(final_subject_name)
                            and not bool(re.search(r"^(anexo|plan de estudios|bolet[ií]n oficial|ministerio|universidad|cve:|http|p[aá]gina|total\s+cr[eé]ditos|resumen|estructura general|distribuci[oó]n|observaciones)\b", final_subject_name, re.IGNORECASE))
                            and not bool(re.search(r"^(grado|graduado|graduada|máster|master)\s+.*?\s+por\s+la\s+universi", final_subject_name, re.IGNORECASE))
                            and not bool(re.search(r"^(el rector|la rectora|el secretario general|la secretaria general|por delegaci[oó]n|el decano|la decana|el director|la directora|ante m[ií]|doy fe|firmado|visto bueno|v\.º\s*b\.º)\b", final_subject_name, re.IGNORECASE))
                            and not final_subject_name.strip().lower() in ["asignatura", "carácter", "caracter", "créditos", "creditos", "curso", "materia", "módulo", "modulo", "ects", "tipo", "total", "grau", "màster", "master", "mencion", "mención"]
                            and not bool(re.search(r"([A-ZÁÉÍÓÚÑ])\1{2,}", final_subject_name))
                            and bool(re.search(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}", final_subject_name))
                            and len(final_subject_name) <= 150
                        ):
                            clean_ects = "6"
                            if ects_match:
                                m_ects = RE_ECTS_CLEAN.search(str(ects_match))
                                if m_ects:
                                    clean_ects = m_ects.group(1).replace(",", ".")

                            try:
                                ects_float = float(clean_ects)
                            except ValueError:
                                ects_float = 6.0

                            # Solución 1: Exclusión ultra-segura de filas de resumen global de créditos
                            # (ej. "Formación Básica: 60", "Obligatorias: 147", "Optativas: 18", "Créditos Totales: 240")
                            # NO afecta a asignaturas compuestas reales como "Química Básica" o "Derecho de Obligaciones"
                            name_norm = re.sub(r"[^\w\s]", "", final_subject_name).strip().lower()
                            is_summary_row = False
                            if ects_float >= 20.0:
                                global_summary_labels = [
                                    "basico", "basica", "formacion basica", "formación básica",
                                    "obligatorio", "obligatoria", "obligatorias", "materias obligatorias", "asignaturas obligatorias",
                                    "optativo", "optativa", "optativas", "materias optativas", "asignaturas optativas",
                                    "total", "totales", "total creditos", "total de creditos", "creditos totales"
                                ]
                                if name_norm in global_summary_labels:
                                    is_summary_row = True
                                    resumen_creditos[final_subject_name] = str(clean_ects)
                                elif name_norm in ["practicas externas", "practicas en empresa", "practicas curriculares"] and ects_float > 35.0:
                                    is_summary_row = True
                                    resumen_creditos[final_subject_name] = str(clean_ects)

                            if is_summary_row:
                                continue

                            # Solución 2: Saneamiento estricto del campo curso y rescate de materia
                            clean_curso, current_materia = normalize_curso(curso, current_materia, ects_val=ects_float)

                            elementos_curriculares.append({
                                "modulo": sanitize_string_value(current_modulo),
                                "materia": sanitize_string_value(current_materia),
                                "nombre_elemento": final_subject_name,
                                "creditos": clean_ects,
                                "creditos_ects": clean_ects,
                                "tipo": caracter,
                                "caracter": caracter,
                                "curso": clean_curso,
                                "cuatrimestre": normalize_cuatrimestre(cuatrimestre)
                            })
    except Exception as e:
        print(f"   [AVISO] pdfplumber table extraction fallback: {e}")

    # Fallback: Text-stream regex parser for PDFs without standard table grid borders
    if len(elementos_curriculares) == 0 and full_text:
        lines = full_text.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str or len(line_str) < 6:
                continue

            line_lower = line_str.lower()
            if any(hk in line_lower for hk in ["asignatura", "materia", "denominación", "carácter", "créditos", "ects", "curso", "página", "boletín"]):
                continue

            # Regex pattern for subject line using pre-compiled RE_TEXT_SUBJECT_LINE
            m = RE_TEXT_SUBJECT_LINE.search(line_str)
            if m:
                subj_name = m.group(1).strip()
                cred_val = m.group(2).replace(",", ".")
                car_str = m.group(3).upper()

                try:
                    if float(cred_val) in [3, 4.5, 6, 9, 12, 15, 18, 24, 30]:
                        elementos_curriculares.append({
                            "modulo": "",
                            "materia": "",
                            "nombre_elemento": subj_name,
                            "creditos_ects": cred_val,
                            "caracter": "FB" if "BÁSICA" in car_str or "FB" in car_str else ("OP" if "OPTATIVA" in car_str or "OP" in car_str else "OB"),
                            "curso": "",
                            "cuatrimestre": ""
                        })
                except ValueError:
                    pass

    return {
        "resumen_creditos": resumen_creditos,
        "total_elementos": len(elementos_curriculares),
        "elementos_curriculares": elementos_curriculares,
        "pdf_sha256": pdf_sha256
    }
