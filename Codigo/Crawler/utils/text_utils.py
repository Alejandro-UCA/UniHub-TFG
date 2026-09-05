"""Utilidades centralizadas de normalización, saneamiento y análisis de texto.

Proporciona funciones canónicas para:
- Normalización Unicode NFKD y eliminación de tildes/diacríticos.
- Reparación de mojibake UTF-8 derivado de dobles codificaciones.
- Detección determinista de idiomas académicos oficiales y cooficiales (es, ca, gl, eu, en).
- Desespejado de texto invertido generado por matrices tipográficas BOE 2007-2014.
- Generación de slugs y tokens normalizados.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Expresiones regulares comunes
RE_MULTISPACE = re.compile(r"[\s\u00a0\u200b\r\n\t]+")
RE_ASCII_SLUG_CLEAN = re.compile(r"[^a-z0-9\-]+")
RE_UNWANTED_CHARS = re.compile(r"[\u00a0\u200b\r\n\t]+")

_MOJIBAKE_MAPPINGS = [
    (chr(0xC3) + chr(0xA1), chr(0xE1)),  # á
    (chr(0xC3) + chr(0xA9), chr(0xE9)),  # é
    (chr(0xC3) + chr(0xAD), chr(0xED)),  # í
    (chr(0xC3) + chr(0xB3), chr(0xF3)),  # ó
    (chr(0xC3) + chr(0xBA), chr(0xFA)),  # ú
    (chr(0xC3) + chr(0xB1), chr(0xF1)),  # ñ
    (chr(0xC3) + " ", chr(0xE0)),        # à con espacio
    (chr(0xC3) + chr(0xA0), chr(0xE0)),  # à
    (chr(0xC3) + chr(0xA8), chr(0xE8)),  # è
    (chr(0xC3) + chr(0xB2), chr(0xF2)),  # ò
    (chr(0xC3) + chr(0xA7), chr(0xE7)),  # ç
    (chr(0xC3) + chr(0xAF), chr(0xEF)),  # ï
    (chr(0xC3) + chr(0xBC), chr(0xFC)),  # ü
    (chr(0xC2) + chr(0xB7), chr(0xB7)),  # · (punt volat)
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


def clean_spaces(text: object) -> str:
    """Colapsa secuencias de espacios en blanco y caracteres de control en un único espacio."""
    if text is None:
        return ""
    return RE_MULTISPACE.sub(" ", str(text).replace("\x00", "")).strip()


def strip_combining_accents(text: object) -> str:
    """Elimina marcas de combinación diacrítica manteniendo caracteres base."""
    if text is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_unicode_text(text: object) -> str:
    """Normaliza texto eliminando marcas diacríticas y pasando a minúsculas limpias."""
    if not text:
        return ""
    stripped = strip_combining_accents(text)
    return clean_spaces(stripped.casefold())


def normalize_ascii_text(text: object) -> str:
    """Normaliza texto descartando caracteres no ASCII y acentos para cotejos estrictos."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text).lower())
    ascii_bytes = normalized.encode("ascii", "ignore")
    return clean_spaces(ascii_bytes.decode("ascii"))


def clean_ascii_slug(text: object) -> str:
    """Convierte un texto en un slug URL en minúsculas separado por guiones."""
    ascii_clean = normalize_ascii_text(text)
    slug = RE_ASCII_SLUG_CLEAN.sub("-", ascii_clean).strip("-")
    return slug


def repair_mojibake_utf8(text: str) -> str:
    """Repara secuencias de mojibake conocidas producidas por doble codificación UTF-8."""
    if not text:
        return ""
    res = unicodedata.normalize("NFC", str(text))
    for bad_sequence, correct_character in _MOJIBAKE_MAPPINGS:
        res = res.replace(bad_sequence, correct_character)
    if any(marker in res for marker in ("Ã", "Â", "â", "ð")):
        # Intento de decodificación segura
        try:
            candidate = res.encode("latin-1").decode("utf-8")
            if "\ufffd" not in candidate:
                res = candidate
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return res


def unreverse_boustrophedon_text(text: str) -> str:
    """Desespeja y normaliza texto invertido generado por matrices tipográficas espejadas del BOE."""
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
            if normalize_ascii_text(word[::-1]) in reverse_vocabulary
        )
        should_reverse = (
            any(pattern.search(clean) for pattern in RE_UNREVERSE_COMMON_PATTERNS)
            or reverse_hits >= 2
        )
        restored.append(clean[::-1].strip() if should_reverse else clean)
    return "\n".join(restored)


def detect_academic_language(text: str) -> str:
    """Detecta el idioma académico predominante: 'es', 'ca', 'gl', 'eu', 'en'."""
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


def normalize_joint_title(title: str) -> str:
    """Normaliza el título de una titulación conjunta eliminando menciones interuniversitarias."""
    if not title:
        return ""
    t = normalize_ascii_text(title)
    t = re.sub(r"\s*\(interuniversitario[^)]*\)", "", t, flags=re.I)
    t = re.sub(r"\s*\(consorcio[^)]*\)", "", t, flags=re.I)
    return clean_spaces(t)
