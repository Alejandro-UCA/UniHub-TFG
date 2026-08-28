import re
import unicodedata
from functools import lru_cache
from bs4 import BeautifulSoup
from config import (
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
    """Verifica que una tabla HTML sea verdaderamente curricular y no un formulario o tabla de cookies."""
    if not table_tag:
        return False
    if table_tag.find(["input", "select", "textarea", "button", "form"]):
        return False
    txt = table_tag.get_text(separator=" ", strip=True).lower()
    
    discard_markers = [
        "calificación cualitativa", "calificacion cualitativa", "escala de calificaciones",
        "tabla de equivalencias", "tabla de convalidaciones", "reconocimiento de créditos",
        "responsable del tratamiento", "delegado de protección", "política de cookies",
        "politica de cookies", "formación a medida", "horario de clases"
    ]
    if any(m in txt for m in discard_markers):
        return False

    cookie_markers = ["_ga", "_gid", "_fbp", "cookie", "cookies", "consentimiento", "caducidad"]
    if any(m in txt for m in cookie_markers) and not any(cm in txt for cm in ["asignatura", "assignatura", "materia", "irakasgaia", "subject", "course"]):
        return False

    curricular_markers = [
        "asignatura", "materia", "denominaci", "ects", "crédito", "credito",
        "carácter", "caracter", "semestre", "cuatrimestre", "guía docente",
        "assignatura", "credits", "curs", "tipus", "quadrimestre", "guia docent",
        "asineira", "creditos", "cuadrimestre", "irakasgaia", "kredituak", "subject", "course", "syllabus"
    ]
    return any(m in txt for m in curricular_markers)


@lru_cache(maxsize=1024)
def normalize_cuatrimestre(raw: str) -> str:
    """Normaliza cadenas de cuatrimestre/semestre a valores estandarizados (1C, 2C, Anual)."""
    if not raw:
        return "1C"
    r = unreverse_text(str(raw)).lower().strip()
    if any(k in r for k in ["anual", "1-2", "1 y 2", "1 i 2"]):
        return "Anual"
    if any(k in r for k in ["2", "2c", "2s", "2º", "2o", "segundo", "segon", "2n", "2n q", "2n s", "q2", "s2", "2do"]):
        return "2C"
    if any(k in r for k in ["1", "1c", "1s", "1º", "1o", "primer", "1r", "1r q", "1r s", "q1", "s1", "1er"]):
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
    if any(k in s_nom for k in ["trabajo fin de grado", "treball de final de grau", "tfg", "traballo de fin de grao", "gradu amaierako lana", "bachelor thesis"]):
        return "TFG"
    if any(k in s_nom for k in ["trabajo fin de máster", "trabajo fin de master", "treball de final de màster", "tfm", "master thesis"]):
        return "TFM"
    if any(k in s_nom for k in ["prácticas externas", "practicas externas", "pràctiques externes", "prácticas en empresa", "external internships"]):
        return "PE"

    if not raw_caracter:
        return default

    c = unreverse_text(str(raw_caracter)).upper().strip()
    if re.search(r"\b(?:FB|FBA|FORMACI[OÓÒ]N?\s+B[AÁÀ]SICA|OINARRIZKOA|BASIC TRAINING)\b", c):
        return "FB"
    if re.search(r"\b(?:OP|OPT|OPTATIV[AO]S?|OPTATIUS?|HAUTAZKOA?|ELECTIVE|OPTIONAL)\b", c):
        return "OP"
    if re.search(r"\b(?:PE|PEX|PR[AÁÀ]CTICAS?\s*(?:EXTERNAS?)?|PR[AÀ]CTIQUES?\s*(?:EXTERNES?)?|KANPOKO\s+PRAKTIKAK|INTERNSHIP|PLACEMENT)\b", c):
        return "PE"
    if re.search(r"\b(?:TFG|TFM|TRABAJO\s+(?:DE\s+)?FIN|TREBALL\s+FI(?:NAL)?|BACHELOR\s+THESIS|MASTER\s+THESIS)\b", c):
        return "TFG/TFM"
    if re.search(r"\b(?:OB|OBL|OBLIGATORI[AO]S?|OBLIGAT[ÒO]RI[AO]S?|DERRIGORREZKOA|COMPULSORY|MANDATORY)\b", c):
        return "OB"

    return default


def extract_subjects_from_card_blocks(text_or_soup, base_url: str = "") -> list:
    """Extrae asignaturas estructuradas a partir de bloques/tarjetas de texto o DOM."""
    if not text_or_soup:
        return []
    card_blocks = None
    if isinstance(text_or_soup, str):
        text = text_or_soup
    else:
        # Mantener la frontera DOM de cada tarjeta. Unir todo el documento en
        # un único bloque pierde la cabecera de las tarjetas posteriores.
        card_nodes = text_or_soup.select(
            ".card-item, .subject-card, [data-subject], [data-asignatura]"
        )
        if card_nodes:
            card_blocks = [node.get_text(separator="\n") for node in card_nodes]
            text = ""
        else:
            text = text_or_soup.get_text(separator="\n")

    results = []
    blocks = card_blocks if card_blocks is not None else re.split(r"\n\s*\n+", text.strip())
    
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        
        first_line = lines[0]
        m_head = re.match(r"^([A-Z0-9]{2,8})\s*[-–—:]\s*(.+)$", first_line, re.IGNORECASE)
        if not m_head:
            continue
        
        cod_asig = m_head.group(1).strip()
        nom_asig = sanitize_subject_name(m_head.group(2).strip())
        if not nom_asig or is_spurious_or_administrative_subject(nom_asig):
            continue
        
        curso_val = "1"
        cuat_val = "1C"
        caracter_val = "OB"
        creditos_val = None
        
        for line in lines[1:]:
            l_low = line.lower()
            if "curs" in l_low or "curso" in l_low or "semestre" in l_low or "cuatrimestre" in l_low or "formaci" in l_low or "obligat" in l_low or "optat" in l_low:
                c_norm, _ = normalize_curso(line)
                if c_norm:
                    curso_val = c_norm
                cuat_val = normalize_cuatrimestre(line)
                caracter_val = classify_subject_caracter(line, nom_asig)
            
            m_num = re.search(r"^(\d+(?:[.,]\d+)?)(?:\s+|$)", line)
            if m_num and ("crèdits" in block.lower() or "créditos" in block.lower() or "ects" in block.lower() or len(lines) >= 3):
                creditos_val = m_num.group(1).replace(",", ".")
        
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
