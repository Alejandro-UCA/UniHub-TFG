import os
import io
import re
import hashlib
import unicodedata
from datetime import datetime
import xlrd
from bs4 import BeautifulSoup
import pdfplumber
import pypdf
from config import (
    GRADO_STANDARD_ECTS,
    MASTER_MIN_ECTS,
    MEDICINA_ECTS,
    ESPECIALES_GRADO_ECTS,
    BOE_SCHEMA_CONCEPT_VOCABULARY,
    BOE_SPURIOUS_MARKERS
)

from downloader import normalize_url
from functools import lru_cache

# -----------------------------------------------------------------------------
# GLOBAL PRE-COMPILED REGEX PATTERNS (OPT-02: Pre-compilación de Regex)
# -----------------------------------------------------------------------------
SPANISH_STOP_WORDS = {
    # Spanish articles, prepositions, conjunctions, generics
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "a", "al", "por", "con", "sin", "sobre", "para", "entre", "hacia", "desde", "hasta", "segun", "tras", "durante", "mediante",
    "y", "e", "o", "u", "ni", "que", "como", "donde", "cuando",
    "graduado", "graduada", "graduados", "graduadas", "grado", "grados",
    "master", "masteres", "máster", "másteres",
    "doctor", "doctora", "doctorado", "doctorados",
    "titulo", "titulos", "titulacion", "titulaciones", "título", "títulos", "titulación", "titulaciones",
    "estudio", "estudios", "plan", "planes", "oficial", "oficiales",
    "universidad", "universidades", "universitaria", "universitarias", "universitario", "universitarios",
    "conducente", "conducentes", "obtencion", "obtención", "superacion", "superación",
    "anexo", "anexos", "resolucion", "resolución", "decreto", "orden", "acuerdo",
    "centro", "centros", "facultad", "facultades", "escuela", "escuelas",
    "programa", "programas", "ensenanzas", "enseñanzas", "ensenanza", "enseñanza",
    "rama", "ramas", "conocimiento", "conocimientos", "mencion", "mención", "menciones",
    "distribucion", "distribución", "creditos", "créditos", "resumen", "estructura",
    # Administrative & layout structural tokens
    "apartado", "materia", "materias", "asignatura", "asignaturas", "modulo", "módulo",
    "docon", "rector", "rectora", "secretario", "secretaria", "emilio", "lora", "tamayo",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    # English generics & connectives for bilingual resolutions (UC3M, UAB, UPF, etc.)
    "bachelor", "bachelors", "master", "masters", "doctor", "phd", "degree", "degrees",
    "and", "in", "of", "for", "with", "the", "an", "science", "sciences",
    "engineering", "studies", "study", "university", "business", "management", "international",
    "applied", "advanced", "official", "curriculum", "syllabus",
    # Catalan / Valenciano / Balear generics & connectives
    "grau", "graus", "estudis", "estudi", "pla", "plans", "oficial", "oficials",
    "universitat", "universitats", "universitari", "universitaris", "universitaria", "universitaries",
    "ciencies", "ciències", "socials", "juridiques", "jurídiques", "humanitats", "enginyeria", "enginyeries", "dels", "deles", "dela", "per", "amb",
    # Galician & Basque generics
    "grao", "graos", "estudos", "estudo", "plano", "planos", "universidade", "gradua", "graduak", "masterra", "unibertsitatea"
}

RE_DEGREE_SECTION_MARKERS = [
    # 1. ANEXO I, ANEXO II (MODIFICACIÓN), etc.
    re.compile(r"(?:ANEXO\s+[IVX\d]+|ANEXO\b)\s*(?:\([^\)]+\))?\s*[:\.\-–—]?\s*(?:T[ií]tulo\s*:?\s*)?([^\n\r]+(?:\n[^\n\r]+)?)", re.IGNORECASE),
    # 2. Plan de estudios conducente al/del título oficial de... / Título: Máster Universitario en...
    re.compile(r"(?:plan de estudios (?:conducentes?\s+)?(?:a\s+la\s+obtenci[oó]n\s+)?(?:del|al)\s+t[ií]tulo\s+(?:oficial\s+)?de\s*:?|(?:el\s+)?t[ií]tulo\s*(?:\([^\)]+\))?\s*:?\s*|denominaci[oó]n\s+del\s+t[ií]tulo\s*:?)\s*([^\n\r]+(?:\n[^\n\r]+)?)", re.IGNORECASE),
    # 3. Direct degree headings: Graduado o Graduada en..., Máster Universitario en..., Grau en...
    re.compile(r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:Plan de Estudios por Asignaturas\s*:\s*)?(?:(?:El\s+)?T[ií]tulo\s+de\s+)?(?:Grado|Graduado(?:\s*[\/\(]a[\/\)]|\s+o\s+Graduada)?|Graduada|M[aá]ster(?:\s+Universitario)?|Master|Doctorado|Bachelor|Grau)\s+(?:en|in|de|d'|del)\s+([A-ZÁÉÍÓÚÑ][^\n\r]{3,120}(?:\n[^\n\r]{3,120})?)", re.IGNORECASE)
]


RE_PREAMBLE_REJECTION = re.compile(
    r"(?:resoluci[oó]n|acuerdo|orden|decreto|de\s+conformidad|visto\s+el|"
    r"relacionados\s+a\s+continuaci[oó]n|este\s+rectorado|publicar\s+(?:el|los)\s+plan|"
    r"aprobar\s+(?:el|los)\s+plan|haberse\s+establecido|una\s+vez\s+homologad|"
    r"homologado\s+por|inscrito\s+en\s+el\s+registro|previa\s+homologaci[oó]n|"
    r"consejo\s+de\s+ministros|consejo\s+de\s+gobierno|t[ií]tulos\s+oficiales\s+de\s+grado\s+siguientes|"
    r"siguientes\s+ense[ñn]anzas|siguientes\s+planes)\b",
    re.IGNORECASE
)
RE_HEADER_GARBAGE = re.compile(r"^(?:(?:FB|OB|OP|PE|TFG|TFM|B|O)\s*)+$", re.IGNORECASE)
RE_TABLE_HEADER_NOISE = re.compile(r"^(?:n[º°\.]*\s*ctos|n[º°\.]*\s*cr[eé]ditos|c[oó]digo|ects|car[aá]cter|curso|cuatrimestre|semestre)\b", re.IGNORECASE)
RE_SUMMARY_LABEL = re.compile(
    r"^(?:formaci[oó]n\s+b[aá]sica|b[aá]sic[ao]s?|obligatori[ao]s?|optativ[ao]s?|cr[eé]ditos\s+(?:b[aá]sicos|obligatorios|optativos)|materias\s+(?:b[aá]sicas|obligatorias|optativas)|asignaturas\s+(?:b[aá]sicas|obligatorias|optativas)|cr[eé]ditos\s+totales|total\s+(?:de\s+)?cr[eé]ditos|total|reconocimiento\s+(?:de\s+)?cr[eé]ditos|actividades\s+art[ií]culo\s+12\.8.*|pr[aá]cticas\s+acad[eé]micas\s+externas\s+optativas)\s*(?:\([a-z0-9\s]+\))?$",
    re.IGNORECASE
)

def is_section_matching(sec_kw: set, target_kw: set) -> bool:
    """
    Evalúa si un conjunto de palabras clave de sección corresponde a la titulación objetivo.
    Requiere al menos 50% de coincidencia léxica o 2 términos coincidentes para evitar colisiones.
    """
    if not sec_kw or not target_kw:
        return False
    intersection = target_kw.intersection(sec_kw)
    if not intersection:
        return False
    score = len(intersection) / len(target_kw)
    if len(target_kw) == 1:
        return len(intersection) == 1
    if len(target_kw) == 2:
        return len(intersection) >= 1 and score >= 0.5
    return len(intersection) >= 2 or score >= 0.5

def is_doctorate_program(nivel: str = "", titulo: str = "") -> bool:
    """Determina de forma unificada si una titulación corresponde a un programa oficial de doctorado (RD 99/2011)."""
    n_low = (nivel or "").lower()
    t_low = (titulo or "").lower()
    return "doctor" in n_low or "99/2011" in n_low or "doctor" in t_low or "phd" in t_low or "560" in n_low or "900" in n_low


def extract_degree_core_keywords(title: str, univ_name: str = "") -> set:
    """
    Extrae lemas y palabras clave discriminativas de una titulación excluyendo preposiciones,
    artículos y términos genéricos (grado, máster, universidad, plan, oficial, etc.).
    """
    if not title:
        return set()
    norm = title.lower()
    norm = unicodedata.normalize('NFKD', norm).encode('ASCII', 'ignore').decode('utf-8')
    words = re.findall(r'\b[a-z0-9]{3,}\b', norm)
    
    univ_words = set()
    if univ_name:
        u_norm = unicodedata.normalize('NFKD', univ_name.lower()).encode('ASCII', 'ignore').decode('utf-8')
        univ_words = set(re.findall(r'\b[a-z0-9]{3,}\b', u_norm))
    
    return set(w for w in words if w not in SPANISH_STOP_WORDS and w not in univ_words)


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


REVERSED_SPANISH_MARKERS = [
    "oxena", "odnum", "airotsih", "soidutse", "sotidérc", "sotiderc", "odaudarg", "adaudarg",
    "retsám", "retsam", "odarg", "ohcered", "aígolocisp", "acitámrofni", "aírenigneg",
    "airenigneg", "aicneic", "lartsemes", "latot", "acisáb", "acisab", "sairotagilbo", "savitatpo", "laveidem"
]


def unreverse_text(text: str) -> str:
    """
    Detecta y corrige texto espejado/invertido proveniente de matrices tipográficas inversas en PDFs antiguos.
    Ejemplo: 'aígolocisP ne odarG' -> 'Grado en Psicología'.
    """
    if not text:
        return ""
    lines = str(text).splitlines()
    unreversed_lines = []
    for line in lines:
        l_str = line.strip()
        l_lower = l_str.lower()
        if (
            any(rev in l_lower for rev in REVERSED_SPANISH_MARKERS)
            or any(l_str.endswith(rev) for rev in ["odarG", "retsáM", "retsaM", "aígolocisP", "acitámrofnI", "aicneiC", "ohcereD"])
            or any(rev in l_str for rev in [" ne odarG", " ne retsáM", " aL ne "])
        ):
            unreversed_lines.append(l_str[::-1])
        else:
            unreversed_lines.append(l_str)
    return "\n".join(unreversed_lines)


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


def clean_excel_code(raw_val: str, zfill_len: int = 0) -> str:
    """Limpia la distorsión numérica de celdas Excel (.0) y aplica zfill opcional."""
    val = str(raw_val).strip() if raw_val is not None else ""
    if val.endswith(".0"):
        val = val[:-2]
    return val.zfill(zfill_len) if zfill_len > 0 and val else val


def classify_subject_caracter(text: str, default: str = "OB") -> str:
    """Clasifica de forma unificada el carácter oficial de una asignatura (FB, OP, PE, TFG/TFM, OB) en ES, CA, GL, EU y EN."""
    if not text:
        return default
    t = text.lower().strip()
    if any(k in t for k in ["básica", "basica", "bàsica", "fb", "oinarrizko", "basic", "core", "formació bàsica", "formacion basica"]):
        return "FB"
    if any(k in t for k in ["optativa", "optatiu", "op", "hautazko", "optional", "elective"]):
        return "OP"
    if any(k in t for k in ["práctica", "practica", "pràctica", "pe", "externa", "externes", "kanpoko praktikak", "internship", "placement"]):
        return "PE"
    if any(k in t for k in ["tfg", "tfm", "trabajo fin", "trabajo de fin", "trabajo final", "treball final", "treball fi", "gral", "master amaierako", "bachelor thesis", "master thesis"]):
        return "TFG/TFM"
    if any(k in t for k in ["obligatoria", "obligatòria", "ob", "derrigorrezko", "compulsory", "mandatory"]):
        return "OB"
    return default



def get_required_degree_credits(nivel_academico: str, titulo: str, resumen_creditos: dict = None) -> float:
    """
    Calcula el número oficial de créditos ECTS exigidos por la normativa española
    (RD 1393/2007, RD 822/2021) para completar la titulación.
    1. Si existe 'Créditos Totales' en la tabla resumen del BOE o web, se extrae ese valor exacto.
    2. Si es Grado en Medicina: 360 ECTS.
    3. Si es Grado en Odontología, Farmacia, Veterinaria, Arquitectura o Doble Grado: 300 ECTS.
    4. Si es Grado estándar: 240 ECTS.
    5. Si es Máster:
       - Másteres Habilitantes de 120 ECTS (Ingeniería Industrial, Caminos, Telecomunicación, Aeronáutica, Agronómica, Naval).
       - Másteres Habilitantes de 90 ECTS (Abogacía, Psicología General Sanitaria).
       - Másteres de 60 ECTS (Profesorado, Arquitectura y generalidad de másteres de especialización).
    """
    if resumen_creditos and isinstance(resumen_creditos, dict):
        total_val = resumen_creditos.get("Créditos Totales") or resumen_creditos.get("Total") or resumen_creditos.get("total")
        if total_val:
            try:
                parsed_total = float(str(total_val).strip().replace(",", "."))
                if parsed_total >= 30.0:
                    return parsed_total
            except ValueError:
                pass

    nivel_lower = (nivel_academico or "").lower()
    titulo_lower = (titulo or "").lower()

    # Grados especiales
    if "medicina" in titulo_lower:
        return float(MEDICINA_ECTS)
    if any(k in titulo_lower for k in ["veterinaria", "farmacia", "odontología", "odontologia", "arquitectura"]):
        return float(ESPECIALES_GRADO_ECTS)
    if "doble" in titulo_lower or "simultaneidad" in titulo_lower or "pceo" in titulo_lower:
        return float(ESPECIALES_GRADO_ECTS)
    if "grado" in nivel_lower or "graduado" in nivel_lower or "graduada" in nivel_lower or "grau" in nivel_lower:
        return float(GRADO_STANDARD_ECTS)

    # Másteres
    if "máster" in nivel_lower or "master" in nivel_lower or "431" in nivel_lower:
        if any(k in titulo_lower for k in [
            "ingeniería industrial", "ingenieria industrial",
            "ingeniería de caminos", "ingenieria de caminos",
            "ingeniería de telecomunicación", "ingenieria de telecomunicacion", "ingeniería de telecomunicaciones",
            "ingeniería aeronáutica", "ingenieria aeronautica",
            "ingeniería agronómica", "ingenieria agronomica",
            "ingeniería naval", "ingenieria naval",
            "ingeniería de montes", "ingenieria de montes"
        ]):
            return 120.0
        if any(k in titulo_lower for k in [
            "abogacía", "abogacia", "abogacia y procura", "abogacía y procura",
            "psicología general sanitaria", "psicologia general sanitaria"
        ]):
            return 90.0
        return float(MASTER_MIN_ECTS)

    return float(GRADO_STANDARD_ECTS)


def compute_curriculum_total_ects(elementos_curriculares: list) -> float:
    """
    Calcula la suma acumulada de créditos ECTS de todas las asignaturas/elementos
    curriculares proporcionados.
    """
    if not elementos_curriculares or not isinstance(elementos_curriculares, list):
        return 0.0
    total = 0.0
    for elem in elementos_curriculares:
        if not isinstance(elem, dict):
            continue
        raw_val = elem.get("creditos_ects")
        if raw_val is not None:
            try:
                cleaned = str(raw_val).strip().replace(",", ".")
                m = re.search(r"\d+(?:\.\d+)?", cleaned)
                if m:
                    total += float(m.group(0))
            except ValueError:
                pass
    return round(total, 2)


def is_curriculum_complete(degree_data: dict) -> bool:
    """
    Valida matemáticamente si el plan de estudios de la titulación es completo.
    Comprueba si:
    1. Si es Doctorado (RD 99/2011), se considera completo por su estructura de tutela/investigación.
    2. Si es Grado o Máster, verifica que el plan exista, tenga asignaturas y que la suma de ECTS
       ofertados sea mayor o igual que los créditos mínimos exigidos por la titulación.
    """
    status = get_curriculum_completeness_status(degree_data)
    return status.get("is_complete", False)


def get_curriculum_completeness_status(degree_data: dict) -> dict:
    """
    Diagnostica y devuelve un reporte detallado del estado de completitud curricular de una titulación.
    """
    if not degree_data or not isinstance(degree_data, dict):
        return {
            "is_complete": False,
            "total_ects_obtained": 0.0,
            "required_ects": 240.0,
            "total_elementos": 0,
            "status": "sin_datos"
        }

    nivel = degree_data.get("nivel_academico", "")
    titulo = degree_data.get("titulo", "")
    nivel_lower = str(nivel).lower()
    titulo_lower = str(titulo).lower()

    # Doctorados (RD 99/2011)
    if is_doctorate_program(nivel, titulo):
        plan = degree_data.get("plan_estudios")
        has_doc_structure = plan is not None
        return {
            "is_complete": has_doc_structure,
            "total_ects_obtained": 0.0,
            "required_ects": 0.0,
            "total_elementos": len(plan.get("elementos_curriculares", [])) if (plan and isinstance(plan, dict)) else 0,
            "status": "doctorado_estructural" if has_doc_structure else "sin_plan"
        }

    plan = degree_data.get("plan_estudios")
    if not plan or not isinstance(plan, dict):
        required = get_required_degree_credits(nivel, titulo)
        return {
            "is_complete": False,
            "total_ects_obtained": 0.0,
            "required_ects": required,
            "total_elementos": 0,
            "status": "sin_plan"
        }

    elementos = plan.get("elementos_curriculares", [])
    total_elementos = len(elementos)
    resumen = plan.get("resumen_creditos", {})
    required = get_required_degree_credits(nivel, titulo, resumen)
    total_ects = compute_curriculum_total_ects(elementos)

    if total_elementos == 0:
        return {
            "is_complete": False,
            "total_ects_obtained": 0.0,
            "required_ects": required,
            "total_elementos": 0,
            "status": "solo_resumen" if len(resumen) > 0 else "sin_asignaturas"
        }

    if total_ects >= required:
        return {
            "is_complete": True,
            "total_ects_obtained": total_ects,
            "required_ects": required,
            "total_elementos": total_elementos,
            "status": "completo"
        }
    else:
        return {
            "is_complete": False,
            "total_ects_obtained": total_ects,
            "required_ects": required,
            "total_elementos": total_elementos,
            "status": "incompleto_parcial"
        }


def parse_universities_from_html(html_text: str) -> list:
    """
    Fallback parser for universities when RUCT returns an HTML table instead of a binary XLS.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    universities = []
    for tr in table.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if not tds or len(tds) < 2 or any(k in tds[0] for k in ["Código", "CÃ³digo", "Codigo"]):
            continue
        row_dict = dict(zip(headers, tds)) if len(headers) == len(tds) else {}
        code = clean_excel_code(row_dict.get("Código") or row_dict.get("CÃ³digo") or row_dict.get("Codigo") or tds[0], zfill_len=3)
        name = row_dict.get("Universidad") or (tds[1] if len(tds) > 1 else "")
        tipo = row_dict.get("Tipo") or (tds[2] if len(tds) > 2 else "")
        ccaa = row_dict.get("Comunidad Autónoma") or row_dict.get("Comunidad AutÃ³noma") or (tds[3] if len(tds) > 3 else "")
        url = row_dict.get("URL") or (tds[4] if len(tds) > 4 else "")
        if code and name:
            universities.append({
                "codigo": code,
                "nombre": sanitize_string_value(name),
                "tipo": sanitize_string_value(tipo),
                "comunidad_autonoma": sanitize_string_value(ccaa),
                "municipio": sanitize_string_value(row_dict.get("Municipio", "")),
                "provincia": sanitize_string_value(row_dict.get("Provincia", "")),
                "web": url.strip(),
                "email": row_dict.get("EMail", "").strip(),
                "telefono": sanitize_string_value(row_dict.get("Teléfono 1", row_dict.get("TelÃ©fono 1", "")))
            })
    return universities


def parse_universities_xls(filepath: str) -> list:
    """
    Parses the XLS file downloaded from RUCT containing the list of universities.
    Returns a list of dictionaries with cleaned university details.
    Includes automatic fallback to HTML table parsing if RUCT returned an HTML response.
    """
    try:
        wb = xlrd.open_workbook(filepath)
        sheet = wb.sheet_by_index(0)
    except Exception as xl_err:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                html_text = f.read()
            if "<table" in html_text.lower():
                parsed_html = parse_universities_from_html(html_text)
                if parsed_html:
                    return parsed_html
        except Exception:
            pass
        raise xl_err
    
    if sheet.nrows == 0:
        return []
    
    headers = [str(cell).strip() for cell in sheet.row_values(0)]
    universities = []
    
    for r in range(1, sheet.nrows):
        row = sheet.row_values(r)
        row_dict = {}
        for idx, header in enumerate(headers):
            val = str(row[idx]).strip() if idx < len(row) else ""
            if header in ["Código", "CÃ³digo"]:
                val = clean_excel_code(val, zfill_len=3)
            row_dict[header] = val
        
        code = clean_excel_code(row_dict.get("Código", row_dict.get("CÃ³digo", "")), zfill_len=3)
        name = row_dict.get("Universidad", "")
        tipo = row_dict.get("Tipo", "")
        ccaa = row_dict.get("Comunidad Autónoma", row_dict.get("Comunidad AutÃ³noma", ""))
        url = row_dict.get("URL", "")
        
        if code and name:
            universities.append({
                "codigo": code,
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


def parse_degrees_from_html(html_text: str) -> list:
    """
    Fallback parser for degrees when RUCT returns an HTML table instead of a binary XLS.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    raw_rows = []
    for tr in table.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if not tds or len(tds) < 2 or any(k in tds[0] for k in ["Código", "CÃ³digo", "Codigo"]):
            continue
        row_dict = dict(zip(headers, tds)) if len(headers) == len(tds) else {}
        code = clean_excel_code(row_dict.get("Código") or row_dict.get("CÃ³digo") or tds[0])
        title = row_dict.get("Título") or row_dict.get("TÃ­tulo") or (tds[1] if len(tds) > 1 else "")
        nivel = row_dict.get("Nivel académico") or row_dict.get("Nivel acadÃ©mico") or (tds[2] if len(tds) > 2 else "")
        estado = (
            row_dict.get("Estado") or 
            row_dict.get("Estado del título") or 
            row_dict.get("Estado del tÃ­tulo") or 
            row_dict.get("Situación") or 
            (tds[3] if len(tds) > 3 else "")
        )
        if code and title:
            raw_rows.append({"code": code, "title": title, "nivel": nivel, "estado": estado})
    return raw_rows


def parse_degrees_xls(filepath: str) -> list:
    """
    Parses the XLS file downloaded from RUCT for a specific university.
    1. FILTERS OUT INACTIVE / EXTINGUISHED DEGREES.
    2. DEDUPLICATES RENOVATED DEGREES within the same university:
       If multiple active versions of the same title exist, keeps ONLY the latest / renovated version.
    """
    is_html_fallback = False
    html_raw_rows = []
    try:
        wb = xlrd.open_workbook(filepath)
        sheet = wb.sheet_by_index(0)
    except Exception as xl_err:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                html_text = f.read()
            if "<table" in html_text.lower():
                html_raw_rows = parse_degrees_from_html(html_text)
                is_html_fallback = True
        except Exception:
            pass
        if not is_html_fallback:
            raise xl_err
    
    if not is_html_fallback and sheet.nrows == 0:
        return []
    
    raw_active_degrees = []
    
    if is_html_fallback:
        candidate_rows = html_raw_rows
    else:
        headers = [str(cell).strip() for cell in sheet.row_values(0)]
        candidate_rows = []
        for r in range(1, sheet.nrows):
            row = sheet.row_values(r)
            row_dict = {}
            for idx, header in enumerate(headers):
                val = str(row[idx]).strip() if idx < len(row) else ""
                if header in ["Código", "CÃ³digo"]:
                    val = clean_excel_code(val)
                row_dict[header] = val
            
            code = clean_excel_code(row_dict.get("Código") or row_dict.get("CÃ³digo") or "")
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
            candidate_rows.append({"code": code, "title": title, "nivel": nivel, "estado": estado})
        
    # Helper para normalización estricta de acentos y distorsiones de codificación UTF-8
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        t = text.lower().strip()
        t = t.replace("Ã³", "o").replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i").replace("Ãº", "u").replace("Ã±", "n")
        t = unicodedata.normalize('NFKD', t)
        t = ''.join(c for c in t if not unicodedata.combining(c))
        return t

    # 1. LISTA NEGRA AMPLIADA (Términos que denotan inactividad, extinción o desestimación)
    blacklist = [
        "extinguid", "extincion", "extinta", "extinto",
        "no vigente", "sin docencia", "baja",
        "derogad", "cancelad", "eliminad", "revocad",
        "suspendid", "caducad", "desestimad", "sustituid",
        "no impartid", "sin efecto", "cierre", "cerrad", "archivo"
    ]

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

    legacy_levels = ["solo segundo ciclo", "ciclo corto", "ciclo largo", "primer ciclo", "primer y segundo ciclo", "pre-bolonia", "rd 56/2005"]
    legacy_title_prefixes = ["licenciado", "licenciada", "diplomado", "diplomada", "ingeniero tecnico", "ingeniera tecnica", "arquitecto tecnico", "arquitecta tecnica"]

    for row_data in candidate_rows:
        code = row_data["code"]
        title = row_data["title"]
        nivel = row_data["nivel"]
        estado = row_data["estado"]

        estado_norm = normalize_text(estado)
        nivel_norm = normalize_text(nivel)
        title_norm = normalize_text(title)

        has_blacklist = any(term in estado_norm for term in blacklist)
        has_whitelist = any(term in estado_norm for term in whitelist)
        is_legacy_level = any(leg in nivel_norm for leg in legacy_levels)
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


def extract_link_context_priority(a_tag) -> tuple:
    """
    Determina la prioridad y categoría de un enlace en la ficha del RUCT analizando
    su contexto semántico (fieldset legend, etiquetas th/label/strong adyacentes y texto contenedor).
    
    Retorna una tupla: (prioridad_numerica, tipo_documento)
    Donde mayor prioridad_numerica indica mayor preferencia:
      - 100: "plan_correccion" (Modificaciones o correcciones del plan de estudios)
      - 90:  "plan_inicial" (Publicación oficial del plan de estudios en el BOE)
      - 30:  "boe_general" (Otros enlaces BOE genéricos como órdenes ministeriales)
      - 10:  "acuerdo_consejo_ministros" (Acuerdo administrativo de oficialización)
      - 0:   "tramite_autonomico_extincion" (Autorización regional, informe o extinción)
    """
    parent_tr = a_tag.find_parent("tr")
    parent_fieldset = a_tag.find_parent("fieldset")
    
    legend_text = ""
    if parent_fieldset:
        legend_tag = parent_fieldset.find("legend")
        if legend_tag:
            legend_text = legend_tag.get_text(strip=True).lower()

    th_text = ""
    if parent_tr:
        th_tag = parent_tr.find("th")
        if th_tag:
            th_text = th_tag.get_text(strip=True).lower()

    prev_label = a_tag.find_previous(["th", "label", "legend", "h3", "h4", "strong", "td"])
    prev_text = prev_label.get_text(strip=True).lower() if prev_label else ""

    container_text = parent_fieldset.get_text(separator=" ", strip=True).lower() if parent_fieldset else ""

    combined_context = f"{legend_text} {th_text} {prev_text} {container_text}"

    # Regla 1: Correcciones o modificaciones del plan de estudios -> PRIORIDAD 100
    if (
        "correcci" in legend_text or "modificaci" in legend_text or 
        "correcci" in th_text or "modificaci" in th_text or 
        "correcciones" in th_text or "corrección plan estudio" in combined_context or "correccion plan estudio" in combined_context
    ):
        return 100, "plan_correccion"

    # Regla 2: Publicación del plan de estudios en el BOE -> PRIORIDAD 90
    if (
        "publicación plan estudios" in prev_text or "publicacion plan estudios" in prev_text or
        "plan de estudios" in prev_text or "plan estudios" in prev_text or
        "publicación plan estudios" in combined_context or "publicacion plan estudios" in combined_context
    ) and "consejo de ministros" not in prev_text:
        return 90, "plan_inicial"

    # Regla 3: Acuerdo de Consejo de Ministros -> PRIORIDAD 10 (Administrativo, sin asignaturas)
    if "consejo de ministros" in prev_text or "acuerdo de consejo de ministros" in combined_context:
        return 10, "acuerdo_consejo_ministros"

    # Regla 4: Trámite autonómico o extinción -> PRIORIDAD 0
    if any(k in combined_context for k in ["autorización ccaa", "autorizacion ccaa", "extinción", "extincion", "renovación acreditación", "renovacion acreditacion"]):
        return 0, "tramite_autonomico_extincion"

    # Regla 5: Fallback general neutro para enlaces a BOE
    return 30, "boe_general"


def parse_degree_detail_html(html_content: str) -> dict:
    """
    Parses the HTML of the degree detail page to verify real-time status and extract all BOE PDF links.
    Returns a dictionary with is_extinct (bool), exact status text, and candidate BOE links ordered
    by semantic context priority (study plans and modifications first) and reverse chronological order.
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
            
            priority, doc_type = extract_link_context_priority(a)
                
            boe_candidates.append({
                "url": href,
                "text": text,
                "date": date_obj,
                "boe_date": date_obj.strftime("%Y-%m-%d") if date_obj else None,
                "priority": priority,
                "doc_type": doc_type
            })
            
    if not boe_candidates:
        return {"is_extinct": False, "latest_boe_url": None, "boe_date": None, "all_boe_links": [], "all_boe_candidates": []}
    
    # Multi-criterio: 1º Mayor prioridad contextual (Planes reales y correcciones antes que Acuerdos), 2º Fecha más reciente
    sorted_candidates = sorted(
        boe_candidates,
        key=lambda c: (c.get("priority", 0), c["date"] if c["date"] is not None else datetime(1970, 1, 1)),
        reverse=True
    )
    
    latest = sorted_candidates[0]
        
    return {
        "is_extinct": False,
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
    Limpia y normaliza exhaustivamente el nombre de una asignatura:
    1. Corrige artefactos de codificación UTF-8 rotos (Ã³, Ã¡, etc.).
    2. Elimina texto invertido proveniente de matrices tipográficas.
    3. Elimina caracteres invisibles y colapsa espacios/tabuladores/saltos de línea.
    4. Elimina numeración ordinal inicial de fila de tabla ('1. ', '4. ', '14 - ', 'a) ', 'B. ').
    5. Separa códigos numéricos o alfanuméricos de secretaría de cabecera ('40147 - CÁLCULO I' -> 'CÁLCULO I').
    6. Elimina puntos guía de índice ('......').
    7. Elimina llamadas a notas al pie finales (' *', ' **', ' (1)', ' [a]', ' †').
    8. Elimina puntuación residual al inicio y al final (.,;:-_/*\\).
    9. Elimina sufijos residuales de carácter pegados ('Gestión. OB' -> 'Gestión').
    """
    if not raw_name:
        return ""
    
    # 1. Corrección de distorsiones UTF-8
    name = str(raw_name).strip()
    name = (name.replace("Ã³", "ó").replace("Ã¡", "á").replace("Ã©", "é")
                .replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ")
                .replace("Ã", "í"))
    
    # 2. Desinvertir si viene de matriz tipográfica inversa
    name = unreverse_text(name)
    
    # 3. Eliminar caracteres invisibles y colapsar espacios/tabuladores/saltos de línea
    name = re.sub(r"[\u00a0\u200b\r\n\t]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    
    # 4. Eliminar numeración ordinal inicial de fila de tabla (ej: '4. Gestión de la Innovación' -> 'Gestión de la Innovación')
    name = re.sub(r"^(?:\d{1,3}[\.\-\)]|[a-zA-Z][\.\)])\s+", "", name).strip()
    
    # 5. Separar códigos numéricos o alfanuméricos de secretaría iniciales (ej: '40147 - CÁLCULO I' -> 'CÁLCULO I')
    m_code = re.match(r"^(?:\d{4,6}|[A-Z]{1,3}\d{3,5})\s*[-–—:]\s*(.+)$", name)
    if m_code:
        name = m_code.group(1).strip()
        
    # 6. Eliminar puntos guía de índice ('......')
    name = re.sub(r"\s*\.{2,}\s*", " ", name).strip()
    
    # 7. Eliminar llamadas a notas al pie al final (ej: ' *', ' **', ' (1)', ' (2)', ' [a]', ' †')
    name = re.sub(r"\s*(?:[\*\†\#\^\~]+|\(\d{1,2}\)|\[[a-zA-Z\d]\])\s*$", "", name).strip()
    
    # 8. Eliminar puntuación residual al inicio y al final
    name = re.sub(r"^[\(\[\*\-\.\,\;\:\/\\_]+", "", name).strip()
    name = re.sub(r"[\*\-\.\,\;\:\/\\_]+$", "", name).strip()
    
    # 9. Eliminar sufijos residuales de carácter pegados (ej: 'Gestión. OB' -> 'Gestión')
    name = re.sub(r"\s*\b(FB|FBA|OB|OBL|OP|OPT|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU|MX)\s*$", "", name, flags=re.IGNORECASE).strip()
    
    return name.rstrip(".,;:-_ ")


def is_spurious_or_administrative_subject(name: str, ects_val: float = 6.0, caracter: str = "OB") -> bool:
    """
    Evalúa si un elemento extraído corresponde a una frase administrativa, mención/itinerario agrupado,
    cabecera de sección, pie de página o dato espurio en lugar de una asignatura docente real.
    """
    if not name or len(name) < 3:
        return True
        
    name_clean = sanitize_subject_name(name)
    if len(name_clean) < 3:
        return True
        
    name_low = name_clean.lower()
    
    # 1. Regla de créditos máximos para asignaturas estándar (<= 12 ECTS en FB/OB/OP)
    if ects_val > 30.0:
        return True
    if ects_val > 12.0 and caracter not in ["TFG/TFM", "PE"] and not any(k in name_low for k in ["trabajo fin", "tfg", "tfm", "practic", "tesis"]):
        return True
    if ects_val <= 0.0:
        return True
        
    # 2. Cabeceras de Mención, Itinerario, Especialidad u Orientación (no son asignaturas sueltas)
    if re.match(r"^(?:menci[oó]n|itinerari[o|s]|especialidad|orientaci[oó]n|perfil)\s+(?:en|de|sobre|para)\b", name_low):
        return True
    if re.match(r"^(?:menci[oó]n|itinerari[o|s]|especialidad|orientaci[oó]n)$", name_low):
        return True
        
    # 3. Frases de elección u optatividad administrativa
    if any(phrase in name_low for phrase in [
        "a elegir entre", "al menos", "uno de los siguientes", "una de las siguientes",
        "oferta de optativas", "tabla de equivalencia", "reconocimiento de creditos",
        "reconocimiento de créditos", "artículo 12.8", "articulo 12.8", "normativa de",
        "condiciones de terminación", "condiciones de terminacion", "total créditos", "total creditos"
    ]):
        return True
        
    # 4. Marcadores de resumen de créditos o etiquetas de tabla
    if caracter != "PE" and caracter != "TFG/TFM" and RE_SUMMARY_LABEL.match(name_clean):
        return True
    if RE_HEADER_GARBAGE.match(name_clean) or RE_TABLE_HEADER_NOISE.match(name_clean):
        return True
        
    # 5. Prefijos de títulos oficiales o niveles (Grado, Máster, Doctorado)
    if re.match(r"^(?:grado|graduado|graduada|m[aá]ster|doctorado|programa\s+de\s+doctorado)\s+en\b", name_low):
        return True
        
    # 6. Órganos universitarios o fórmulas de firma
    if re.match(r"^(?:el\s+rector|la\s+rectora|el\s+secretario|la\s+secretaria|facultad\s+de|escuela\s+de|campus\s+de|centro\s+de)\b", name_low):
        return True
        
    # 7. Marcadores legales o boletines oficiales
    if re.match(r"^(?:anexo|bolet[ií]n|b\.?o\.?e\.?|dogc|bocm|bocyl|dogv|doe|cve:|http|www\.)\b", name_low):
        return True
        
    # 8. Solo dígitos o caracteres repetidos
    if re.match(r"^\d+$", name_clean) or re.search(r"([a-zA-ZáéíóúñÁÉÍÓÚÑ])\1{3,}", name_clean):
        return True
        
    # 9. Debe contener al menos una palabra de 3 letras alfabéticas
    if not re.search(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}", name_clean):
        return True
        
    return False



def parse_header_schema(header_line: str) -> list:
    """
    Construye dinámicamente el esquema de columnas del PDF a partir de la línea de encabezado.
    Devuelve la secuencia ordenada de conceptos detectados ('modulo', 'asignatura', 'tipo', 'creditos', etc.).
    """
    clean = header_line.lower().strip()
    clean = re.sub(r"^\d+(?:\.\d+)*\s*[-–—:]?\s*", "", clean)
    clean = clean.replace("estructura del plan de estudios", "").replace(":", "")
    tokens = re.findall(r'[a-záéíóúñç]+', clean)
    
    schema = []
    seen = set()
    for t in tokens:
        for concept, syns in BOE_SCHEMA_CONCEPT_VOCABULARY.items():
            if t in syns and concept not in seen:
                schema.append(concept)
                seen.add(concept)
                break
    return schema


def parse_boe_text_curriculum_dynamic(full_text: str, degree_title: str = "", level: str = "") -> dict:
    """
    Analizador dinámico de texto para resoluciones del BOE (RD 822/2021 y textos tabulados).
    Deduce el esquema de columnas del documento y extrae todas las asignaturas con sus módulos y créditos,
    garantizando 0 datos espurios.
    """
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    
    schema = []
    start_idx = -1
    for idx, line in enumerate(lines):
        s = parse_header_schema(line)
        if len(s) >= 2 and ("asignatura" in s or "materia" in s) and ("creditos" in s or "tipo" in s):
            schema = s
            start_idx = idx
            break
            
    if not schema or start_idx == -1:
        return {}
        
    extracted = []
    current_modulo = ""
    
    tipo_idx = schema.index("tipo") if "tipo" in schema else -1
    cred_idx = schema.index("creditos") if "creditos" in schema else -1
    tipo_before_cred = (tipo_idx != -1 and cred_idx != -1 and tipo_idx < cred_idx)
    
    if tipo_before_cred:
        re_pattern = re.compile(
            r"^(?:(?P<mod>[A-ZÁÉÍÓÚÑ][^.\n\t]+?)\.\s+)?(?P<name>[A-ZÁÉÍÓÚÑ][^.\n\t]+?(?:\.|\b))\s*(?P<car>FBA|FB|OBL|OB|OPT|OP|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU)\s+(?P<ects>\d+(?:[.,]\d+)?)(?:\s+(?P<extra>.*))?$",
            re.IGNORECASE
        )
    else:
        re_pattern = re.compile(
            r"^(?:(?P<mod>[A-ZÁÉÍÓÚÑ][^.\n\t]+?)\.\s+)?(?P<name>[A-ZÁÉÍÓÚÑ][^.\n\t]+?(?:\.|\b))\s*(?P<ects>\d+(?:[.,]\d+)?)\s+(?P<car>FBA|FB|OBL|OB|OPT|OP|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU)(?:\s+(?P<extra>.*))?$",
            re.IGNORECASE
        )
        
    seen_names = set()
    
    for line in lines[start_idx+1:]:
        l_low = line.lower()
        if any(term in l_low for term in BOE_SPURIOUS_MARKERS):
            continue
        if re.match(r"^\d+\.\d+\s+condiciones de terminación", l_low):
            break
            
        # Detectar módulo agrupador independiente
        if line.endswith(".") and not re.search(r"\b(FBA|FB|OBL|OB|OPT|OP|PE|TFG|TFM)\b", line) and not re.search(r"\b\d+\s*$", line):
            if len(line) > 3 and not any(term in l_low for term in BOE_SPURIOUS_MARKERS):
                current_modulo = line.rstrip(".")
                continue
                
        m = re_pattern.match(line)
        if m:
            prefix_mod = m.group("mod")
            if prefix_mod and len(prefix_mod) > 3:
                row_modulo = prefix_mod.strip()
            else:
                row_modulo = current_modulo
                
            s_name = m.group("name").strip().rstrip(".")
            s_car = m.group("car").upper()
            s_ects = m.group("ects").replace(",", ".")
            
            # Filtros estrictos anti-ruido
            if len(s_name) < 3 or any(term in s_name.lower() for term in BOE_SPURIOUS_MARKERS):
                continue
            if s_name.lower() in seen_names:
                continue
            seen_names.add(s_name.lower())
            
            car = classify_subject_caracter(s_car, default="OB")
                
            extracted.append({
                "modulo": row_modulo,
                "materia": row_modulo,
                "nombre_elemento": s_name,
                "creditos": s_ects,
                "creditos_ects": s_ects,
                "tipo": car,
                "caracter": car,
                "curso": "",
                "cuatrimestre": ""
            })
            
    is_grado = "grado" in (degree_title or "").lower()
    return {
        "resumen_creditos": {"Créditos Totales": str(GRADO_STANDARD_ECTS if is_grado else MASTER_MIN_ECTS)},
        "total_elementos": len(extracted),
        "elementos_curriculares": extracted
    }


def parse_boe_pdf(pdf_filepath, target_title: str = "", univ_name: str = "") -> dict:

    """
    Extracts METICULOUS curriculum data (resumen creditos, asignaturas, modulos, materias, 
    unidades formativas, bloques, ECTS, carácter, curso, cuatrimestre) from a BOE PDF.
    Supports multi-degree BOE resolution disambiguation (segmenting Anexos by degree title).
    Supports both disk file path (str) and in-memory bytes/io.BytesIO objects (OPT-04).
    Calculates SHA256 digest of PDF stream for negative caching (OPT-06).
    """
    resumen_creditos = {}
    elementos_curriculares = []
    seen_subject_map = {}
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
                raw_text_parts.append(unreverse_text(text))
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
                raw_text_parts = [full_text]
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # MULTI-DEGREE DISAMBIGUATION ENGINE:
    # Detect if the BOE resolution publishes multiple distinct degree curricula
    # (e.g. Anexo I: Informática, Anexo II: Marketing, Anexo III: Psicología).
    # -------------------------------------------------------------------------
    target_kw = extract_degree_core_keywords(target_title, univ_name)
    detected_sections = []
    
    for page_idx, p_text in enumerate(raw_text_parts):
        text_to_search = p_text
        if page_idx == 0:
            m_anexo = re.search(r"\bANEXO\b", p_text, re.IGNORECASE)
            if m_anexo:
                text_to_search = p_text[m_anexo.start():]
            else:
                m_sig = re.search(r"(?:El Rector|La Rectora|El Secretario General|La Secretaria General|El Director|La Directora)\b", p_text, re.IGNORECASE)
                if m_sig:
                    text_to_search = p_text[m_sig.end():]

        for pattern in RE_DEGREE_SECTION_MARKERS:
            for match in pattern.finditer(text_to_search):
                sec_raw = match.group(0).strip()
                if RE_PREAMBLE_REJECTION.search(sec_raw):
                    continue
                sec_kw = extract_degree_core_keywords(sec_raw, univ_name)
                if sec_kw and len(sec_kw) > 0:
                    detected_sections.append({
                        "page_idx": page_idx,
                        "raw": sec_raw,
                        "keywords": sec_kw
                    })

    # Check if multiple distinct degree sections exist
    is_multi_degree_doc = False
    if len(detected_sections) >= 2:
        for i in range(len(detected_sections)):
            for j in range(i + 1, len(detected_sections)):
                diff_i = detected_sections[i]["keywords"].difference(detected_sections[j]["keywords"])
                diff_j = detected_sections[j]["keywords"].difference(detected_sections[i]["keywords"])
                if diff_i and diff_j:
                    is_multi_degree_doc = True
                    break
            if is_multi_degree_doc:
                break

    page_inclusion_mask = [True] * len(raw_text_parts)
    has_any_match = False
    if is_multi_degree_doc and target_kw:
        current_state = False
        for page_idx in range(len(raw_text_parts)):
            for s in detected_sections:
                if s["page_idx"] == page_idx:
                    current_state = is_section_matching(s["keywords"], target_kw)
                    if current_state:
                        has_any_match = True
            page_inclusion_mask[page_idx] = current_state

        # If it is a multi-degree resolution and target degree is NOT present in any section, return 0 elements!
        if not has_any_match:
            return {
                "resumen_creditos": {},
                "total_elementos": 0,
                "elementos_curriculares": []
            }

    # 1. Parse Credit Summary Table (using text from relevant pages or full_text)
    relevant_text = "\n".join([raw_text_parts[i] for i in range(len(raw_text_parts)) if i < len(page_inclusion_mask) and page_inclusion_mask[i]]) or full_text
    for label, pattern in RE_CREDIT_SUMMARY:
        match = pattern.search(relevant_text)
        if match:
            resumen_creditos[label] = match.group(1)

    # 2. Extract Structured Curriculum Tables with pdfplumber (OPT-02)
    try:
        if isinstance(pdf_stream, io.BytesIO):
            pdf_stream.seek(0)

        with pdfplumber.open(pdf_stream) as pdf:
            current_modulo = ""
            current_materia = ""
            current_state = False if is_multi_degree_doc else True

            for page_idx, page in enumerate(pdf.pages):
                # Extract section headers with top vertical positions on this page for sub-page bounding
                page_headers = []
                if is_multi_degree_doc:
                    words = page.extract_words() or []
                    lines_by_top = {}
                    for w in words:
                        top_bucket = round(w["top"] / 6.0) * 6.0
                        if top_bucket not in lines_by_top:
                            lines_by_top[top_bucket] = []
                        lines_by_top[top_bucket].append(w["text"])

                    sorted_tops = sorted(lines_by_top.keys())
                    sorted_lines = [unreverse_text(" ".join(lines_by_top[t])) for t in sorted_tops]

                    for i in range(len(sorted_lines)):
                        combined_3_lines = " ".join(sorted_lines[i:min(i+3, len(sorted_lines))])
                        top_pos = sorted_tops[i]
                        for pattern in RE_DEGREE_SECTION_MARKERS:
                            m = pattern.search(combined_3_lines)
                            if m:
                                sec_raw = m.group(0).strip()
                                if not RE_PREAMBLE_REJECTION.search(sec_raw):
                                    sec_kw = extract_degree_core_keywords(sec_raw, univ_name)
                                    if sec_kw:
                                        page_headers.append({
                                            "top": top_pos,
                                            "keywords": sec_kw,
                                            "matches": is_section_matching(sec_kw, target_kw)
                                        })


                # Find tables with bounding boxes
                found_tables = page.find_tables()
                if not found_tables:
                    continue

                for t_obj in found_tables:
                    t_top = t_obj.bbox[1]

                    # If page has headers, update state based on headers located above this table
                    if is_multi_degree_doc and page_headers:
                        for h in page_headers:
                            if h["top"] <= t_top + 10:
                                current_state = h["matches"]

                    if is_multi_degree_doc and not current_state:
                        continue

                    table_data = t_obj.extract()
                    if not table_data:
                        continue

                    subject_col_idx = -1
                    materia_col_idx = -1
                    ects_col_idx = -1
                    caracter_col_idx = -1
                    curso_col_idx = -1
                    cuatrimestre_col_idx = -1

                    # Multiline row stitching pre-pass: merge fragmented text lines
                    merged_rows = []
                    for row in table_data:
                        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                            continue

                        clean_row = [unreverse_text(RE_MULTIPLE_SPACES.sub(" ", str(cell).strip())) if cell else "" for cell in row]
                        row_str = " ".join(clean_row).lower()

                        # Detect header rows to establish column mapping
                        if any(hk in row_str for hk in ["asignatura", "denominaci", "materia", "crédito", "credito", "ects", "carácter", "caracter", "curso", "módulo", "modulo"]):
                            is_materia_summary = any(mhk in row_str for mhk in ["por materias", "resumido (por materias)", "resumen por materias", "distribución en materias", "distribucion en materias", "tipo de materia"])
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
                                elif any(kw in c_lower for kw in ["curso", "curs", "año"]):
                                    curso_col_idx = idx
                                elif any(kw in c_lower for kw in ["cuatrimestre", "semestre", "periodo", "temporalidad"]):
                                    cuatrimestre_col_idx = idx

                            # Si la tabla solo contiene la columna Materia y carece de Asignatura,
                            # representa un desglose de materias agrupadas, no de asignaturas individuales.
                            # Se registran en resumen_creditos / materias y no en elementos_curriculares.
                            continue



                        # Check if this row is a continuation fragment
                        target_subj_col = subject_col_idx if (subject_col_idx != -1 and subject_col_idx < len(clean_row)) else (1 if len(clean_row) > 1 and len(clean_row[0]) <= 4 else 0)
                        target_subj_cell = clean_row[target_subj_col] if target_subj_col < len(clean_row) else ""
                        has_ects = any(RE_ECTS_NUMBER.search(c) for idx_c, c in enumerate(clean_row) if idx_c != target_subj_col)

                        is_fragment = (
                            not has_ects 
                            and len(target_subj_cell) > 0 
                            and (
                                target_subj_cell[0].islower() 
                                or target_subj_cell.lower().startswith(("la ", "el ", "los ", "las ", "de ", "del ", "para ", "en ", "y ", "a ", "con ", "sobre ", "por "))
                            )
                        )

                        if is_fragment and merged_rows:
                            prev = merged_rows[-1]
                            prev_col = subject_col_idx if (subject_col_idx != -1 and subject_col_idx < len(prev)) else (1 if len(prev) > 1 and len(prev[0]) <= 4 else 0)
                            if prev_col < len(prev) and prev[prev_col]:
                                prev[prev_col] = f"{prev[prev_col].rstrip(' :-,')} {target_subj_cell}".strip()
                                continue

                        merged_rows.append(clean_row)

                    for clean_row in merged_rows:
                        row_str = " ".join(clean_row).lower()
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

                        if ects_col_idx != -1 and ects_col_idx < len(clean_row) and clean_row[ects_col_idx]:
                            m = RE_ECTS_NUMBER.search(clean_row[ects_col_idx])
                            if m:
                                ects_match = m.group(1)

                        if caracter_col_idx != -1 and caracter_col_idx < len(clean_row) and clean_row[caracter_col_idx]:
                            caracter = classify_subject_caracter(clean_row[caracter_col_idx], default="OB")

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
                                caracter = classify_subject_caracter(cell_lower, default="OB")

                            if not curso and RE_CURSO_NUM.search(cell):
                                curso = cell
                            if not cuatrimestre and ("cuatrimestre" in cell_lower or "semestre" in cell_lower):
                                cuatrimestre = cell

                        # Identify subject name column
                        final_subject_name = ""
                        if subject_col_idx != -1 and subject_col_idx < len(clean_row):
                            final_subject_name = clean_row[subject_col_idx]
                        elif subject_col_idx == -1:
                            # La tabla carece de columna de asignaturas individuales (es un desglose de materias o módulos agregados)
                            # Se registra como resumen de créditos/materias y NO como asignaturas individuales docentes.
                            if ects_match:
                                mat_name = clean_row[materia_col_idx] if (materia_col_idx != -1 and materia_col_idx < len(clean_row)) else clean_row[0]
                                if mat_name and len(mat_name) > 2:
                                    resumen_creditos[sanitize_subject_name(mat_name)] = str(ects_match)
                            continue



                        # If materia is in a distinct column from subject
                        if materia_col_idx != -1 and materia_col_idx != subject_col_idx and materia_col_idx < len(clean_row):
                            current_materia = clean_row[materia_col_idx]

                        # Fallback heuristic: if subject column equals current materia and column 1 has text, use column 1
                        if len(clean_row) > 1 and materia_col_idx != subject_col_idx and final_subject_name.lower() == current_materia.lower():
                            if not RE_ECTS_NUMBER.match(clean_row[1]) and len(clean_row[1]) > 3:
                                final_subject_name = clean_row[1]

                        final_subject_name = sanitize_subject_name(final_subject_name)
                        
                        # Si no se detectó ningún número de créditos ECTS y la tabla carece de columnas curriculares, no es una tabla de plan docente
                        if not ects_match and ects_col_idx == -1 and caracter_col_idx == -1 and curso_col_idx == -1:
                            continue

                        clean_ects = "6"
                        if ects_match:
                            m_ects = RE_ECTS_CLEAN.search(str(ects_match))
                            if m_ects:
                                clean_ects = m_ects.group(1).replace(",", ".")

                        try:
                            ects_float = float(clean_ects)
                        except ValueError:
                            ects_float = 6.0

                        # Validación estricta y unificada contra datos espurios, materias agregadas y cabeceras administrativas
                        if is_spurious_or_administrative_subject(final_subject_name, ects_val=ects_float, caracter=caracter):
                            if ects_float > 0 and final_subject_name and len(final_subject_name) > 2:
                                resumen_creditos[final_subject_name] = str(clean_ects)
                            continue

                        clean_curso, current_materia = normalize_curso(curso, current_materia, ects_val=ects_float)
                        clean_cuat = normalize_cuatrimestre(cuatrimestre)

                        norm_name = re.sub(r"[^\w\s]", "", final_subject_name).strip().lower()
                        if norm_name in seen_subject_map:
                            idx_ex = seen_subject_map[norm_name]
                            if not elementos_curriculares[idx_ex]["curso"] and clean_curso:
                                elementos_curriculares[idx_ex]["curso"] = clean_curso
                            if not elementos_curriculares[idx_ex]["cuatrimestre"] and clean_cuat:
                                elementos_curriculares[idx_ex]["cuatrimestre"] = clean_cuat
                            if elementos_curriculares[idx_ex]["caracter"] == "OB" and caracter != "OB":
                                elementos_curriculares[idx_ex]["caracter"] = caracter
                                elementos_curriculares[idx_ex]["tipo"] = caracter
                        else:
                            seen_subject_map[norm_name] = len(elementos_curriculares)
                            elementos_curriculares.append({
                                "modulo": sanitize_string_value(current_modulo),
                                "materia": sanitize_string_value(current_materia),
                                "nombre_elemento": final_subject_name,
                                "creditos": str(clean_ects),
                                "creditos_ects": str(clean_ects),
                                "tipo": caracter,
                                "caracter": caracter,
                                "curso": clean_curso,
                                "cuatrimestre": clean_cuat
                            })

    except Exception as e:
        print(f"   [AVISO] pdfplumber table extraction fallback: {e}")

    # Fallback: Dynamic schema text parser for RD 822/2021 & unstructured text BOEs without vector table borders
    if len(elementos_curriculares) == 0 and full_text:
        dyn_res = parse_boe_text_curriculum_dynamic(full_text, target_title, "")
        if dyn_res and len(dyn_res.get("elementos_curriculares", [])) > 0:
            elementos_curriculares = dyn_res["elementos_curriculares"]
            if not resumen_creditos and dyn_res.get("resumen_creditos"):
                resumen_creditos = dyn_res["resumen_creditos"]

    # Fallback secondary: Text-stream regex parser for older unbordered PDF layouts
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
                subj_name = sanitize_subject_name(m.group(1).strip())
                cred_val = m.group(2).replace(",", ".")
                car_str = m.group(3).upper()

                if RE_HEADER_GARBAGE.match(subj_name) or RE_TABLE_HEADER_NOISE.match(subj_name):
                    continue

                try:
                    cred_float = float(cred_val)
                    if RE_SUMMARY_LABEL.match(subj_name) or (cred_float > 12.0 and car_str not in ["TFG", "TFM", "PE", "PEX"]):
                        resumen_creditos[subj_name] = str(cred_val)
                        continue

                    if cred_float in [1, 1.5, 2, 3, 4, 4.5, 5, 6, 7.5, 8, 9, 10, 12]:

                        final_car = classify_subject_caracter(car_str, default="OB")
                        elementos_curriculares.append({
                            "modulo": "",
                            "materia": "",
                            "nombre_elemento": subj_name,
                            "creditos": cred_val,
                            "creditos_ects": cred_val,
                            "tipo": final_car,
                            "caracter": final_car,
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
