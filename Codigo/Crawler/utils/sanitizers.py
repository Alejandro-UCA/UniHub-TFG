import re
import unicodedata
from functools import lru_cache
from bs4 import BeautifulSoup
from core.config import (
    HEADER_KEYWORDS,
    INVALID_SUBJECT_KEYWORDS,
    INVALID_METADATA_LABELS,
    REVERSED_SPANISH_MARKERS,
)

RE_UNREVERSE_COMMON_PATTERNS = [
    re.compile(r"\bodarG\b"),
    re.compile(r"\brets[aá]M\b", re.IGNORECASE),
    re.compile(r"\baígolocisP\b"),
    re.compile(r"\barutangisA\b"),
    re.compile(r"\bsoicivres\b"),
    re.compile(r"\bsoitid[eé]rC\b", re.IGNORECASE),
    re.compile(r"\bsotiderC\b", re.IGNORECASE),
    re.compile(r"\bsoicapstE\b", re.IGNORECASE),
    re.compile(r"\baicneucoD\b", re.IGNORECASE),
    re.compile(r"\bsoidutsE\b", re.IGNORECASE),
    re.compile(r"\bsopeT\b", re.IGNORECASE),
    re.compile(r"\bnalP\b"),
    re.compile(r"\bsoicatpO\b", re.IGNORECASE),
    re.compile(r"\bsairatagilbO\b", re.IGNORECASE),
    re.compile(r"\bacis[aá]B\b", re.IGNORECASE),
    re.compile(r"\bselanoicaN\b", re.IGNORECASE),
    re.compile(r"\bsecitc[aá]rP\b", re.IGNORECASE),
    re.compile(r"\bsoludaM\b", re.IGNORECASE),
    re.compile(r"\bsairetaM\b", re.IGNORECASE),
    re.compile(r"\bsosruC\b", re.IGNORECASE),
    re.compile(r"\bseretca[rR]\b", re.IGNORECASE),
    re.compile(r"\bsecitcarP\b", re.IGNORECASE)
]

RE_MULTIPLE_SPACES = re.compile(r"[ \t]+")
RE_CLEAN_SUBJECT_NAME = re.compile(r"^[\s\-•*0-9.)]+|\s+$")
RE_SUMMARY_LABEL = re.compile(
    r"^(?:formaci[oó]n\s+b[aá]sica|b[aá]sic[ao]s?|obligatori[ao]s?|optativ[ao]s?|"
    r"cr[eé]ditos\s+(?:b[aá]sicos|obligatorios|optativos)|materias\s+(?:b[aá]sicas|obligatorias|optativas)|"
    r"asignaturas\s+(?:b[aá]sicas|obligatorias|optativas)|cr[eé]ditos\s+totales|"
    r"total\s+(?:de\s+)?cr[eé]ditos|total|reconocimiento\s+(?:de\s+)?cr[eé]ditos|"
    r"actividades\s+art[ií]culo\s+12\.8.*|pr[aá]cticas\s+acad[eé]micas\s+externas\s+optativas)"
    r"\s*(?:\([a-z0-9\s]+\))?$",
    re.IGNORECASE,
)
RE_HEADER_GARBAGE = re.compile(r"^(?:(?:FB|OB|OP|PE|TFG|TFM|B|O)\s*)+$", re.IGNORECASE)
RE_TABLE_HEADER_NOISE = re.compile(
    r"^(?:n[º°\.]*\s*ctos|n[º°\.]*\s*cr[eé]ditos|c[oó]digo|ects|car[aá]cter|curso|cuatrimestre|semestre)\b",
    re.IGNORECASE,
)
RE_TEMPORALITY_HEADING = re.compile(
    r"^(?:(?:primer|segundo|tercer|cuarto|quinto|sexto|1(?:er|º|a)?|2(?:do|º|a)?|3(?:er|º|a)?|4(?:to|º|a)?|5(?:to|º|a)?|6(?:to|º|a)?)\s+"
    r"(?:semestre|cuatrimestre)|temporalidad(?:\s+de\s+las?\s+asignaturas?)?|"
    r"distribuci[oó]n\s+temporal(?:\s+de\s+las?\s+asignaturas?)?)$",
    re.IGNORECASE,
)

_RE_UNWANTED_CHARS = re.compile(r"[\u00a0\u200b\r\n\t]+")
_RE_MULTISPACE = re.compile(r"\s+")
_RE_ORDINAL_START = re.compile(r"^(?:\d{1,3}[\.\-\)]|[a-zA-Z][\.\)])\s+")
_RE_SECRETARIA_CODE = re.compile(r"^(?:\d{4,6}|[A-Z]{1,3}\d{3,5})\s*[-–—:]\s*(.+)$")
_RE_DOT_LEADERS = re.compile(r"\s*\.{2,}\s*")
_RE_FOOTNOTES = re.compile(r"\s*(?:[\*\†\#\^\~]+|\(\d{1,2}\)|\[[a-zA-Z\d]\])\s*$")
_RE_PUNCT_START = re.compile(r"^[\(\[\*\-\.\,\;\:\/\\_]+")
_RE_PUNCT_END = re.compile(r"[\*\-\.\,\;\:\/\\_]+$")
_RE_CARACTER_SUFFIX = re.compile(
    r"\s*\b(FB|FBA|OB|OBL|OP|OPT|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU|MX)\s*$",
    re.IGNORECASE,
)

_MOJIBAKE_MAPPINGS = [
    (chr(0xC3) + chr(0xA1), chr(0xE1)),
    (chr(0xC3) + chr(0xA9), chr(0xE9)),
    (chr(0xC3) + chr(0xAD), chr(0xED)),
    (chr(0xC3) + chr(0xB3), chr(0xF3)),
    (chr(0xC3) + chr(0xBA), chr(0xFA)),
    (chr(0xC3) + chr(0xB1), chr(0xF1)),
    (chr(0xC3) + " ", chr(0xE0)),
    (chr(0xC3) + chr(0xA0), chr(0xE0)),
    (chr(0xC3) + chr(0xA8), chr(0xE8)),
    (chr(0xC3) + chr(0xB2), chr(0xF2)),
    (chr(0xC3) + chr(0xA7), chr(0xE7)),
    (chr(0xC3) + chr(0xAF), chr(0xEF)),
    (chr(0xC3) + chr(0xBC), chr(0xFC)),
    (chr(0xC2) + chr(0xB7), chr(0xB7)),
]

_ACADEMIC_LANG_LEXICONS = {
    "ca": {
        "words": {
            "assignatura", "assignatures", "grau", "graus", "màster", "màsters",
            "curs", "quadrimestre", "crèdits", "optativa", "optatives", "obligatòria",
            "obligatòries", "formació", "bàsica", "treball", "pràctiques", "menció",
            "dret", "enginyeria", "química", "física", "economia", "empresa", "comunicació",
            "ciències", "salut", "educació", "història", "llengua", "matemàtiques",
            "pla", "destudis", "lassignatura", "dalgorismes", "estructures", "dades", "algorismes"
        },
        "diacritics": {"·", "ŀ", "à", "è", "ò", "ï", "ü", "ç"}
    },
    "gl": {
        "words": {
            "materia", "materias", "grao", "graos", "posgrao", "posgraos", "doutoramento",
            "ano", "cuadrimestre", "créditos", "optativa", "optativas", "obrigatoria",
            "obrigatorias", "formación", "básica", "traballo", "prácticas", "mención",
            "dereito", "enxeñaría", "química", "física", "economía", "empresa", "comunicación",
            "ciencias", "saúde", "educación", "historia", "lingua", "matemáticas", "xeoloxía"
        },
        "diacritics": set()
    },
    "eu": {
        "words": {
            "irakasgaia", "irakasgaiak", "gradua", "graduak", "masterra", "masterrak",
            "doktoregoa", "maila", "lauhilekoa", "kredituak", "hautazkoa", "derrigorrezkoa",
            "oinarrizko", "prestakuntza", "lana", "praktikak", "aipamena", "zuzenbidea",
            "ingeniaritza", "kimika", "fisika", "ekonomia", "enpresa", "komunicazioa",
            "zientziak", "osasuna", "hezkuntza", "historia", "hizkuntza", "matematika"
        },
        "diacritics": set()
    },
    "en": {
        "words": {
            "subject", "subjects", "course", "courses", "degree", "degrees", "bachelor",
            "master", "phd", "year", "semester", "credits", "ects", "elective", "compulsory",
            "mandatory", "basic", "training", "thesis", "internship", "internships", "major",
            "law", "engineering", "chemistry", "physics", "economics", "business", "communication",
            "science", "sciences", "health", "education", "history", "language", "mathematics"
        },
        "diacritics": set()
    },
    "es": {
        "words": {
            "asignatura", "asignaturas", "grado", "grados", "máster", "másteres",
            "curso", "cuatrimestre", "créditos", "optativa", "optativas", "obligatoria",
            "obligatorias", "formación", "básica", "trabajo", "prácticas", "mención",
            "derecho", "ingeniería", "química", "física", "economia", "empresa", "comunicación",
            "ciencias", "salud", "educación", "historia", "lengua", "matemáticas"
        },
        "diacritics": {"á", "é", "í", "ó", "ú", "ñ"}
    }
}


def detect_academic_language(text: str) -> str:
    """
    Detecta automáticamente el idioma académico predominante en un texto, título o temario.
    Devuelve código ISO: 'es' (Español), 'ca' (Català/Valencià), 'gl' (Galego), 'eu' (Euskara), 'en' (English).
    """
    if not text:
        return "es"
    raw_lower = text.lower().strip()
    words = re.findall(r"\b[a-záéíóúñàèòïüç·ŀ]+\b", raw_lower)
    if not words:
        return "es"

    scores = {"ca": 0, "gl": 0, "eu": 0, "en": 0, "es": 0}

    for char in raw_lower:
        if char in {"·", "ŀ", "ï", "ü", "ç", "à", "è", "ò"}:
            scores["ca"] += 3
        elif char == "ñ":
            scores["es"] += 1
            scores["gl"] += 1

    for w in words:
        for lang, lexicon in _ACADEMIC_LANG_LEXICONS.items():
            if w in lexicon["words"]:
                scores[lang] += 2

    for w in words:
        if w.endswith("itzak") or w.endswith("egia") or w.endswith("tasuna") or w.endswith("tegia") or w.endswith("koak"):
            scores["eu"] += 4
        elif w.endswith("ció") or w.endswith("ions") or w.endswith("itzar") or w == "destudis" or w == "lassignatura" or w == "dalgorismes" or w == "dades":
            scores["ca"] += 3
        elif w.endswith("ción") or w.endswith("ciones"):
            scores["es"] += 2
        elif w.endswith("cións") or w.endswith("amento") or w.endswith("amentos"):
            scores["gl"] += 3
        elif w.endswith("tion") or w.endswith("tions") or w.endswith("ing"):
            scores["en"] += 2

    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score >= 2:
        return best_lang

    return "es"


def unreverse_text(text: str) -> str:
    """
    Desespeja y normaliza texto invertido generado por matrices tipográficas espejadas
    de publicaciones oficiales del BOE entre 2007 y 2014.
    """
    if not text:
        return ""
    lines = str(text).replace("\x00", "").splitlines()
    restored = []
    reverse_vocabulary = {
        "anexo", "mundo", "historia", "estudios", "creditos", "graduado",
        "graduada", "master", "grado", "derecho", "psicologia", "informatica",
        "ingenieria", "ciencia", "semestral", "total", "basica", "obligatorias",
        "optativas", "medieval", "libros", "grandes", "asignatura", "materia",
    }
    for line in lines:
        clean = line.strip()
        low = clean.lower()
        reverse_hits = sum(
            1 for word in re.findall(r"[^\W\d_]+", clean, re.UNICODE)
            if unicodedata.normalize("NFKD", word[::-1].lower()).encode("ascii", "ignore").decode() in reverse_vocabulary
        )
        should_reverse = (
            any(marker in low for marker in REVERSED_SPANISH_MARKERS)
            or any(pattern.search(clean) for pattern in RE_UNREVERSE_COMMON_PATTERNS)
            or reverse_hits >= 2
        )
        restored.append(clean[::-1].strip() if should_reverse else clean)
    return "\n".join(restored)


def sanitize_string_value(val) -> str:
    """Sanitiza y limpia cadenas de texto de caracteres nulos y espacios múltiples."""
    if val is None:
        return ""
    s = str(val).replace("\x00", "").strip()
    return RE_MULTIPLE_SPACES.sub(" ", s)


def sanitize_subject_name(name: str) -> str:
    """Normaliza un nombre preservando correctamente las lenguas cooficiales."""
    if not name:
        return ""
    normalized = unicodedata.normalize("NFC", str(name).strip())
    for bad_sequence, correct_character in _MOJIBAKE_MAPPINGS:
        normalized = normalized.replace(bad_sequence, correct_character)
    normalized = unreverse_text(normalized)
    normalized = _RE_UNWANTED_CHARS.sub(" ", normalized)
    normalized = _RE_MULTISPACE.sub(" ", normalized).strip()
    normalized = _RE_ORDINAL_START.sub("", normalized).strip()
    code_match = _RE_SECRETARIA_CODE.match(normalized)
    if code_match:
        normalized = code_match.group(1).strip()
    normalized = _RE_DOT_LEADERS.sub(" ", normalized).strip()
    normalized = _RE_FOOTNOTES.sub("", normalized).strip()
    normalized = _RE_PUNCT_START.sub("", normalized).strip()
    normalized = _RE_PUNCT_END.sub("", normalized).strip()
    normalized = _RE_CARACTER_SUFFIX.sub("", normalized).strip()
    return normalized.rstrip(".,;:-_ ")


def curriculum_element_key(name: str) -> str:
    """Genera una clave conservadora para deduplicar nombres curriculares.

    Algunas resoluciones del BOE repiten la misma asignatura en una tabla de
    temporalidad, con artículos opcionales (por ejemplo, ``en Ingeniería`` /
    ``en la Ingeniería``). Se eliminan sólo conectores gramaticales; se
    preservan los términos académicos y los números que distinguen materias.
    """
    normalized = unicodedata.normalize("NFKD", sanitize_subject_name(name).lower())
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    grammatical_connectors = {"a", "al", "de", "del", "el", "en", "la", "las", "los", "y"}
    return " ".join(token for token in tokens if token not in grammatical_connectors)


def is_spurious_or_administrative_subject(text: str, ects_val: float = None, caracter: str = "OB") -> bool:
    """
    Identifica si una línea es ruido administrativo, pie de página, escala de notas o texto de formulario.
    """
    if not text:
        return True
    t_clean = sanitize_subject_name(text)
    t_low = t_clean.lower()
    
    if len(t_clean) < 3 or len(t_clean) > 130:
        return True

    if t_clean.isdigit():
        return True

    if t_low.startswith(("http://", "https://")) or "www." in t_low:
        return True
    # «Gestión de despachos» es una materia; «Despacho 302» es un contacto.
    if re.search(r"\bdespacho\s*(?:n[úu]m(?:ero)?\.?\s*)?[:#-]?\s*\d+\b", t_low) or t_low == "despacho":
        return True
    if re.match(r"^(?:FBA|FB|OBL|OB|OPT|OP|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU)\s+\d+\s+\d+$", t_clean, re.I):
        return True

    credits = None
    if ects_val is not None:
        try:
            credits = float(ects_val)
        except (TypeError, ValueError):
            credits = None
    normalized_character = (caracter or "OB").upper()
    is_final_or_internship = normalized_character in {"TFG", "TFM", "TFG/TFM", "PE"} or any(
        marker in t_low for marker in ("trabajo fin", "treball fi", "tfg", "tfm", "practic", "pràctic", "externa", "proyecto")
    )
    if credits is not None and (credits <= 0 or credits > 30 or (credits > 12 and not is_final_or_internship)):
        return True

    if any(t_low == hk for hk in HEADER_KEYWORDS):
        return True
    if RE_TEMPORALITY_HEADING.match(t_clean):
        return True
    if any(sk in t_low for sk in INVALID_SUBJECT_KEYWORDS):
        return True
    if t_low in INVALID_METADATA_LABELS and normalized_character not in {"PE", "TFG", "TFM", "TFG/TFM"}:
        return True

    discard_patterns = [
        r"^(?:anexo|bolet[ií]n|b\.?o\.?e\.?|resoluci[oó]n|p[aá]gina|cve:|boe-a-)",
        r"^(?:total|totales|suma|cr[eé]ditos\s+totales|distribuci[oó]n)",
        r"^(?:curso\s+[1-6]|primer\s+curso|segundo\s+curso|tercer\s+curso|cuarto\s+curso)",
        r"^\d+\s+optativas?(?:\s+de\s+(?:menci[oó]n|itinerario))?$",
        r"^(?:menci[oó]n|itinerarios?|especialidad|orientaci[oó]n|perfil)(?:\s+(?:en|de|sobre|para)\b|\s*:|$)",
        r"^(?:centro|modalidad|idioma|cuota|precio|importe|coste|matr[ií]cula|plazas|duraci[oó]n)\b",
        r"(?:se\s+ofertar[aá]n|car[aá]cter\s+optativo|a\s+elegir\s+entre|oferta\s+de\s+optativas)",
        r"^(?:grado|graduado|graduada|m[aá]ster|doctorado|programa\s+de\s+doctorado)\s+en\b",
        r"^(?:el\s+rector|la\s+rectora|facultad\s+de|escuela\s+de|campus\s+de|centro\s+de|departamento\s+de|departament\s+de|secci[oó]n\s+departamental|instituto\s+universitario|[aá]rea\s+de\s+conocimiento)\b",
        r"^(?:acreditaci[oó]n\s+de|requisito\s+de|competencia\s+en\s+lengua|prueba\s+de\s+nivel|exigencia\s+de\s+idioma|nivel\s+[abc][12]|horario\s+de|tutor[ií]as?|atenci[oó]n\s+(?:a\s+)?alumnos?|turno\s+de)\b",
        r"^(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
    ]
    if any(re.search(pattern, t_low) for pattern in discard_patterns):
        return True
    if normalized_character not in {"PE", "TFG", "TFM", "TFG/TFM"} and RE_SUMMARY_LABEL.match(t_clean):
        return True
    if RE_HEADER_GARBAGE.match(t_clean) or RE_TABLE_HEADER_NOISE.match(t_clean):
        return True
    if re.search(r"([A-Za-zÀ-ÿ])\1{3,}", t_clean):
        return True
    if not re.search(r"[A-Za-zÀ-ÿ]{3,}", t_clean):
        return True

    return False


def is_valid_curricular_table(table_tag) -> bool:
    """Verifica que una tabla HTML sea verdaderamente curricular y no un formulario de búsqueda, escala de notas, tabla de cookies ni baremo administrativo de convalidaciones (Multilingüe)."""
    if not table_tag or table_tag.find(["input", "select", "textarea", "button", "form"]):
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

    # Una tabla de adaptación entre un plan histórico y el vigente puede
    # contener filas y créditos plausibles, pero no representa el currículo
    # que debe publicarse para el título actual. Sólo se descarta cuando
    # aparecen marcadores emparejados de plan anterior y nuevo, para no
    # rechazar tablas curriculares que mencionen un plan de forma incidental.
    legacy_current_pairs = (
        ("plan de estudios de la licenciatura", "nuevo plan de estudios"),
        ("plan anterior", "nuevo plan"),
        ("plan antiguo", "plan nuevo"),
        ("previous plan", "new plan"),
        ("ancien plan", "nouveau plan"),
        ("pla anterior", "nou pla"),
    )
    if any(old_marker in txt and new_marker in txt for old_marker, new_marker in legacy_current_pairs):
        return False

    rows = table_tag.find_all("tr")
    header_text = " ".join(
        cell.get_text(" ", strip=True).lower()
        for row in rows[:2]
        for cell in row.find_all(["th", "td"])
    )
    subject_headers = (
        "asignatura", "assignatura", "asineira", "irakasgaia", "materia",
        "denominación", "denominacion", "nombre", "subject", "course", "module",
    )
    curricular_headers = (
        "crédito", "credito", "ects", "credit", "carácter", "caracter", "tipo",
        "tipus", "curso", "curs", "semestre", "cuatrimestre", "quadrimestre",
        "semester", "year", "level", "código", "codigo", "codi", "kredituak",
        "kreditu", "mota", "maila", "ikasturtea", "lauhilekoa",
    )
    has_subject_header = any(marker in header_text for marker in subject_headers)
    has_curricular_header = any(marker in header_text for marker in curricular_headers)

    explicit_subject_rows = 0
    rows_with_credits = 0
    explicit_credit_cells = 0
    rows_with_character = 0
    scan_rows = rows[1:] if (rows and any(cell.name == "th" for cell in rows[0].find_all(["th", "td"]))) else rows
    for row in scan_rows:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if not cells:
            continue
        row_text = " ".join(cells).lower()
        if any(re.search(rf"\b{re.escape(marker)}\b", row_text) for marker in subject_headers):
            explicit_subject_rows += 1
        row_has_explicit_credit = False
        for cell in cells:
            # Un número incrustado en una descripción (un año, una página,
            # una tarifa o el nombre de un docente) no es evidencia de ECTS.
            # Sólo se considera crédito una celda aislada con un valor dentro
            # del rango curricular, opcionalmente acompañada de su unidad.
            if re.fullmatch(
                r"\s*(?:[1-9]|[12]\d|30)(?:[.,]\d+)?\s*"
                r"(?:ects|cr[eé]ditos?|credits?)?\s*",
                cell,
                re.IGNORECASE,
            ):
                row_has_explicit_credit = True
                explicit_credit_cells += 1
                break
        if row_has_explicit_credit:
            rows_with_credits += 1
        if any(re.search(r"\b(?:FB|OB|OP|B|O|PE|TFG|TFM|TR|BA|OT|DER|OIN|HAU|OPT|OBL)\b", cell, re.IGNORECASE) for cell in cells):
            rows_with_character += 1

    has_adjacent_course_heading = False
    parent_heading = table_tag.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "caption", "legend", "button", "summary"])
    if parent_heading:
        h_txt = parent_heading.get_text().lower()
        if any(ck in h_txt for ck in ["curso", "curs", "ano", "año", "ikasturtea", "maila", "semestre", "cuatrimestre", "quadrimestre", "year", "term"]):
            has_adjacent_course_heading = True

    if not has_adjacent_course_heading:
        parent_tab = table_tag.find_parent(["div", "section", "article"], class_=lambda c: c and any(k in str(c).lower() for k in ["tab-pane", "tabcontent", "accordion", "collapse", "panel"]))
        if parent_tab:
            tab_id = parent_tab.get("id") or ""
            tab_trigger = table_tag.find_previous(["a", "button", "li"])
            if tab_trigger:
                t_txt = tab_trigger.get_text().lower()
                if any(ck in t_txt for ck in ["curso", "curs", "ano", "año", "ikasturtea", "maila", "semestre", "cuatrimestre", "quadrimestre", "year", "term"]):
                    has_adjacent_course_heading = True

    has_explicit_credit_header = any(
        marker in header_text
        for marker in ("crédito", "credito", "crèdits", "credits", "credit", "ects", "kredituak", "kreditu")
    )
    is_valid_structural_table = (
        (has_subject_header and has_curricular_header)
        or (has_subject_header and has_explicit_credit_header and rows_with_credits >= 2)
        or (
            rows_with_credits >= 2
            and (
                has_explicit_credit_header
                or rows_with_character >= 1
                or has_adjacent_course_heading
            )
        )
        or (explicit_subject_rows >= 2 and rows_with_credits >= 2)
    )
    if not is_valid_structural_table:
        # Fallback para tablas curriculares paralelas sin cabecera explícita:
        # algunas maquetas colocan dos asignaturas y sus cargas en cada fila,
        # precedidas solo por «curso»/«semestre». Se exigen varias filas con
        # al menos dos nombres y dos cargas plausibles para no convertir
        # listados administrativos de números en asignaturas.
        context_markers = (
            "curso", "curs", "año", "ano", "semestre", "cuatrimestre",
            "asignatura", "assignatura", "materia", "crédito", "credito",
            "ects", "subject", "course",
        )
        has_curriculum_context = any(marker in txt for marker in context_markers)
        parallel_rows = 0
        for row in rows[1:]:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if not cells:
                continue
            numeric_cells = 0
            text_cells = 0
            for cell in cells:
                compact = re.sub(r"\s+", " ", cell).strip()
                if re.fullmatch(r"(?:\d{1,2}(?:[.,]\d{1,2})?)", compact):
                    try:
                        if 1.0 <= float(compact.replace(",", ".")) <= 30.0:
                            numeric_cells += 1
                            continue
                    except ValueError:
                        pass
                if len(compact) >= 4 and not compact.isdigit():
                    text_cells += 1
            if numeric_cells >= 2 and text_cells >= 2:
                parallel_rows += 1
        if has_curriculum_context and parallel_rows >= 2:
            return True
    return is_valid_structural_table


@lru_cache(maxsize=1024)
def normalize_cuatrimestre(raw: str) -> str:
    """Normaliza cadenas de cuatrimestre/semestre a valores estandarizados (1C, 2C, Anual)."""
    if not raw:
        return "1C"
    r = unreverse_text(str(raw)).lower().strip()

    # 1. Comprobar modalidad Anual
    if re.search(r"\b(?:anual|anualidad|anuals?|ambos|1-2|1\s*y\s*2|1\s*i\s*2|year-long|annual)\b", r):
        return "Anual"

    # 2. Comprobar declaraciones explícitas con prefijo o sufijo de semestre / cuatrimestre
    if re.search(r"(?:cuatrimestre|semestre|cuadrimestre|quadrimestre|lauhileko|sem|cuat|q|s)\s*[:=.-]?\s*(?:2|2º|2o|2n|2do|segundo|segon|segona|second)\b|\b(?:2|2º|2o|2n|2do|segundo|segon|segona|second)\s*(?:cuatrimestre|semestre|cuadrimestre|quadrimestre|lauhileko|sem|cuat|q|s)\b|\b(?:2c|2s|2º\s*s|2º\s*c|2n\s*q|2n\s*s|q2|s2|2\.\s*lauhilekoa)\b", r):
        return "2C"
    if re.search(r"(?:cuatrimestre|semestre|cuadrimestre|quadrimestre|lauhileko|sem|cuat|q|s)\s*[:=.-]?\s*(?:1|1º|1o|1r|1er|1ra|primer|primero|primera|first)\b|\b(?:1|1º|1o|1r|1er|1ra|primer|primero|primera|first)\s*(?:cuatrimestre|semestre|cuadrimestre|quadrimestre|lauhileko|sem|cuat|q|s)\b|\b(?:1c|1s|1º\s*s|1º\s*c|1r\s*q|1r\s*s|q1|s1|1\.\s*lauhilekoa)\b", r):
        return "1C"

    # 3. Comprobar ordinales o números sin prefijo de "curso"
    if re.search(r"\b(?:segundo|segon|segona|2n|2do|2º|2o)\b", r) and not re.search(r"\b(?:curso|curs|año|ano|ikasturte)\b", r):
        return "2C"
    if re.search(r"\b(?:primer|primero|primera|1r|1er|1º|1o)\b", r) and not re.search(r"\b(?:curso|curs|año|ano|ikasturte)\b", r):
        return "1C"
    if re.search(r"(?<!curso\s)(?<!curs\s)(?<!año\s)(?<!ano\s)\b2\b", r):
        return "2C"
    if re.search(r"(?<!curso\s)(?<!curs\s)(?<!año\s)(?<!ano\s)\b1\b", r):
        return "1C"

    return "1C"


_RE_CURSO_NUM = re.compile(r"\b([1-6])(?:º|o|er|n|r|\.º)?\b|\b(primer|segundo|tercer|cuarto|quinto|sexto|primero|tercero|segon|primer|segona)\b|\b(i{1,3}|iv|v|vi)\b", re.IGNORECASE)
_ROMAN_MAP = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
_TEXT_ORDINAL_MAP = {
    "primer": "1", "primero": "1", "1r": "1",
    "segundo": "2", "segon": "2", "segona": "2", "2n": "2",
    "tercer": "3", "tercero": "3", "3r": "3",
    "cuarto": "4", "quart": "4", "quarta": "4",
    "quinto": "5", "cinque": "5", "cinquena": "5",
    "sexto": "6", "sise": "6", "sisena": "6"
}

def normalize_curso(raw: str, current_materia: str = "", ects_val: float = None) -> tuple[str, str]:
    """
    Normaliza el campo de curso devolviendo una tupla (curso_str, materia_rescatada):
    - Si el campo contiene un curso válido (1..6), devuelve ('1', current_materia).
    - Si contiene un texto largo descriptivo (tema/materia desplazada), devuelve ('', texto_materia).
    - Si el valor coincide con los créditos ECTS (desalineación), devuelve ('', current_materia).
    """
    if not raw:
        return ("", current_materia)
    r = unreverse_text(str(raw)).strip()
    r_low = r.lower()

    if ects_val is not None:
        try:
            if float(r.replace(",", ".")) == float(ects_val):
                return ("", current_materia)
        except (ValueError, TypeError):
            pass

    # Si es un texto largo que parece nombre de asignatura/materia (p.ej. "Comunicación Oral y Escrita.")
    if len(r) > 10 and not any(w in r_low for w in ["curso", "curs", "año", "ano", "primer", "segund"]):
        rescued = current_materia if current_materia else r
        return ("", rescued)

    m = _RE_CURSO_NUM.search(r_low)
    if m:
        num = m.group(1)
        word = m.group(2)
        roman = m.group(3)
        if num:
            return (num, current_materia)
        if word:
            return (_TEXT_ORDINAL_MAP.get(word.lower(), "1"), current_materia)
        if roman:
            return (_ROMAN_MAP.get(roman.lower(), "1"), current_materia)

    return ("", current_materia)


@lru_cache(maxsize=4096)
def classify_subject_caracter(raw_caracter: str, subject_name: str = "", default: str = "OB") -> str:
    """
    Clasifica el carácter de la asignatura en códigos normalizados:
    FB (Formación Básica), OB (Obligatoria), OP (Optativa), PE (Prácticas Externas), TFG/TFM (Trabajo Fin de Grado/Máster).
    """
    s_nom = (subject_name or "").lower()
    if any(k in s_nom for k in ["trabajo fin de grado", "treball de final de grau", "tfg", "traballo de fin de grao", "gradu amaierako lana", "bachelor thesis", "final degree project"]):
        return "TFG"
    if any(k in s_nom for k in ["trabajo fin de máster", "trabajo fin de master", "treball de final de màster", "tfm", "master thesis", "master amaierako lana"]):
        return "TFM"
    if any(k in s_nom for k in ["prácticas externas", "practicas externas", "pràctiques externes", "prácticas en empresa", "external internships", "kanpoko praktikak"]):
        return "PE"

    if not raw_caracter:
        return default

    c = unreverse_text(str(raw_caracter)).upper().strip()
    if re.search(r"\b(?:FB|FBA|FORMACI[OÓÒ]N?\s+B[AÁÀ]SICA|OINARRIZKOA|OIN|BASIC TRAINING|TR|TRONCAL|BA|B[AÁÀ]SICA)\b", c):
        return "FB"
    if re.search(r"\b(?:OP|OPT|OT|OPTATIV[AO]S?|OPTATIUS?|HAUTAZKOA?|HAU|ELECTIVE|OPTIONAL)\b", c):
        return "OP"
    if re.search(r"\b(?:PE|PEX|PR[AÁÀ]CTICAS?\s*(?:EXTERNAS?)?|PR[AÀ]CTIQUES?\s*(?:EXTERNES?)?|KANPOKO\s+PRAKTIKAK|KAN|INTERNSHIP|PLACEMENT|INT)\b", c):
        return "PE"
    if re.search(r"\b(?:TFG|TFM|TRABAJO\s+(?:DE\s+)?FIN|TREBALL\s+FI(?:NAL)?|BACHELOR\s+THESIS|MASTER\s+THESIS|MAL|AAL|BST|MST)\b", c):
        return "TFG/TFM"
    if re.search(r"\b(?:OB|OBL|OBLIGATORI[AO]S?|OBLIGAT[ÒO]RI[AO]S?|DERRIGORREZKOA|DER|COMPULSORY|MANDATORY|COMP|CORE)\b", c):
        return "OB"

    return default


def extract_subjects_from_card_blocks(text_or_soup, base_url: str = "") -> list:
    """Extrae asignaturas estructuradas a partir de bloques/tarjetas de texto o DOM.

    Soporta tarjetas con código prefijado (ej. '701001 - Álgebra') y tarjetas
    modernas con nombre directo de asignatura, extrayendo ECTS, curso y tipología.
    """
    if not text_or_soup:
        return []
    card_blocks = None
    if isinstance(text_or_soup, str):
        text = text_or_soup
    else:
        # Mantener la frontera DOM de cada tarjeta, soportando selectores académicos universales.
        card_nodes = text_or_soup.select(
            ".card-item, .subject-card, .subject-item, .asignatura-item, "
            "[data-subject], [data-asignatura], .materia-item, .plan-estudios-item, "
            ".item-asignatura, .course-item, li.asignatura, li.subject"
        )
        if card_nodes:
            card_blocks = [node.get_text(separator="\n") for node in card_nodes]
            text = ""
        elif hasattr(text_or_soup, "find") and text_or_soup.find("table"):
            # Si el documento tiene tablas pero no tarjetas explícitas, evitar falsos positivos
            return []
        else:
            text = text_or_soup.get_text(separator="\n")

    results = []
    seen_names = set()
    blocks = card_blocks if card_blocks is not None else re.split(r"\n\s*\n+", text.strip())
    
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        
        first_line = lines[0]
        cod_asig = ""
        nom_asig = ""
        
        m_head = re.match(r"^([A-Z0-9]{2,10})\s*[-–—:]\s*(.+)$", first_line, re.IGNORECASE)
        if m_head:
            cod_candidate = m_head.group(1).strip()
            if not (
                first_line.lower().startswith(("http://", "https://", "www."))
                or cod_candidate.lower() in {"http", "https", "www"}
                or "." in cod_candidate
            ):
                cod_asig = cod_candidate
                nom_asig = sanitize_subject_name(m_head.group(2).strip())

        if not nom_asig:
            # Soporte para tarjetas cuyo encabezado es directamente el nombre de la asignatura
            # Exige indicios curriculares en el bloque si no hay código explícito
            has_curric_hints = any(k in block.lower() for k in [
                "crèdits", "créditos", "creditos", "ects", "asignatura", "assignatura",
                "obligatoria", "optativa", "formación básica", "formacio basica", "1º curso", "2º curso", "3º curso", "4º curso"
            ])
            if has_curric_hints or card_blocks is not None:
                clean_first = sanitize_subject_name(first_line)
                if (
                    clean_first
                    and len(clean_first) >= 4
                    and len(clean_first) <= 120
                    and not clean_first.lower().startswith(("http://", "https://", "www."))
                    and not clean_first.isdigit()
                    and not is_spurious_or_administrative_subject(clean_first)
                ):
                    nom_asig = clean_first

        if not nom_asig or is_spurious_or_administrative_subject(nom_asig):
            continue

        key = curriculum_element_key(nom_asig)
        if not key or key in seen_names:
            continue
        seen_names.add(key)
        
        curso_val = "1"
        cuat_val = "1C"
        caracter_val = classify_subject_caracter("", nom_asig)
        creditos_val = None
        
        for line in lines:
            l_low = line.lower()
            if any(k in l_low for k in ["curs", "curso", "semestre", "cuatrimestre", "formaci", "obligat", "optat", "básica", "basica"]):
                c_norm, _ = normalize_curso(line)
                if c_norm:
                    curso_val = c_norm
                cuat_val = normalize_cuatrimestre(line)
                caracter_val = classify_subject_caracter(line, nom_asig)
            
            m_cr = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:cr[eèé]dits?|ects|cr\.?)\b", line, re.IGNORECASE)
            if m_cr:
                try:
                    val_flt = float(m_cr.group(1).replace(",", "."))
                    if 0.5 <= val_flt <= 60.0:
                        creditos_val = m_cr.group(1).replace(",", ".")
                except ValueError:
                    pass
            elif not creditos_val:
                m_num = re.search(r"^(\d+(?:[.,]\d+)?)(?:\s+|$)", line)
                if m_num and any(k in block.lower() for k in ["crèdits", "créditos", "ects"]) and len(lines) >= 2:
                    try:
                        val_flt = float(m_num.group(1).replace(",", "."))
                        if 0.5 <= val_flt <= 30.0:
                            creditos_val = m_num.group(1).replace(",", ".")
                    except ValueError:
                        pass
        
        results.append({
            "codigo_asignatura": cod_asig,
            "nombre_elemento": nom_asig,
            "tipo_elemento": "Asignatura",
            "creditos_ects": creditos_val,
            "creditos": float(creditos_val) if creditos_val else None,
            "caracter": caracter_val,
            "curso": curso_val,
            "cuatrimestre": cuat_val,
            "idioma": detect_academic_language(nom_asig)
        })
        
    return results
