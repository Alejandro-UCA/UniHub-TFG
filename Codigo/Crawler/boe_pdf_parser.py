import os
import re
import io
import hashlib
import unicodedata
import logging
import threading
import collections
import pdfplumber

from config import (
    BOE_SCHEMA_CONCEPT_VOCABULARY,
    BOE_SPURIOUS_MARKERS,
    GRADO_STANDARD_ECTS,
    MASTER_MIN_ECTS,
    PREAMBLE_REJECTION_PATTERNS,
    SPANISH_STOP_WORDS,
    UMBRELLA_BRANCH_WORDS
)

logger = logging.getLogger("boe_pdf_parser")

RE_CREDIT_SUMMARY = [
    ("Formación Básica", re.compile(r"(?:Formaci[oó]n\s+B[aá]sica|FB)\s*(?:\([^)]*\))?\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Obligatorias", re.compile(r"(?:Obligatorias?|OB)\s*(?:\([^)]*\))?\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Optativas", re.compile(r"(?:Optativas?|OP)\s*(?:\([^)]*\))?\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Prácticas Externas", re.compile(r"(?:Pr[aá]cticas\s+Externas?|PE)\s*(?:\([^)]*\))?\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Trabajo Fin de Grado / Máster", re.compile(r"(?:Trabajo\s+Fin\s+de\s+(?:Grado|M[aá]ster)|TFG|TFM)\s*(?:\([^)]*\))?\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Créditos Totales", re.compile(
        r"(?:cr[eé]ditos?\s+totales?|total(?:\s+(?:de\s+)?cr[eé]ditos?)?(?:\s+ects)?"
        r"(?:\s+(?:del|de\s+la)\s+t[ií]tulo)?)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    ))
]

RE_DEGREE_SECTION_MARKERS = [
    re.compile(r"(?:ANEXO|Anexo)\s+[I|V|X\d]+[.:\s–-]+([^\n\r]+(?:\n[^\n\r]+)?(?:Grado|Máster|Master|Doctorado|Graduado|Graduada)[^\n\r]+(?:\n[^\n\r]+)?)", re.IGNORECASE),
    re.compile(r"(?:PLAN DE ESTUDIOS|Plan de Estudios)\s+(?:CONDUCENTES?\s+AL\s+T[IÍ]TULO\s+DE:?\s*)?(?:DEL|DE LA|DE)?\s*([^\n\r]+(?:\n[^\n\r]+)?(?:Grado|Máster|Master|Doctorado|Graduado|Graduada)[^\n\r]+(?:\n[^\n\r]+)?)", re.IGNORECASE),
    re.compile(r"((?:Grado|Máster|Master|Graduado|Graduada)\s+en\s+[^\n\r]+(?:\n[^\n\r]+)?)", re.IGNORECASE)
]

RE_PREAMBLE_REJECTION = re.compile(
    r"(?:resoluci[oó]n|acuerdo|orden|decreto|de\s+conformidad|visto\s+el|"
    + "|".join(PREAMBLE_REJECTION_PATTERNS)
    + r")\b",
    re.IGNORECASE
)

RE_SUMMARY_LABEL = re.compile(
    r"^(?:formaci[oó]n\s+b[aá]sica\s*(?:\([^\)]+\))?|obligatorias?\s*(?:\([^\)]+\))?|optativas?\s*(?:\([^\)]+\))?|total\s+cr[eé]ditos?|cr[eé]ditos\s+totales?|total|totales|suma)$",
    re.IGNORECASE
)

RE_HEADER_GARBAGE = re.compile(r"^(?:(?:FB|OB|OP|PE|TFG|TFM|BAS|OBL|OPT|PRA)\s*){3,}$", re.IGNORECASE)
RE_TABLE_HEADER_NOISE = re.compile(r"^(?:n[º°.]*\s*c(?:tos|r[eé]ditos?)|c[oó]d(?:igo)?|curso|semestre|car[aá]cter)$", re.IGNORECASE)
RE_ECTS_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")
RE_CURRICULAR_PAGE_HINTS = re.compile(
    r"(?:\b(?:FB|OB|OP|PE|TFG|TFM|BAS|OBL|OPT|PEX|ECTS|cr[eé]ditos?|asignatura|materia|denominaci[oó]n|cuatrimestre|semestre|car[aá]cter|m[oó]dulo)\b|\b(?:3|4[.,]5|6|9|12|18|24|30|60)\s*(?:cr[eé]ditos?|ects)?\b)",
    re.IGNORECASE
)
_RE_DYNAMIC_TIPO_FIRST = re.compile(
    r"^(?:(?P<mod>[A-ZÁÉÍÓÚÑ][^.\n\t]+?)\.\s+)?(?P<name>[A-ZÁÉÍÓÚÑ][^.\n\t]+?(?:\.|\b))\s*"
    r"(?P<car>FBA|FB|OBL|OB|OPT|OP|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU)\s+"
    r"(?P<ects>\d+(?:[.,]\d+)?)(?:\s+(?P<extra>.*))?$",
    re.IGNORECASE,
)
_RE_DYNAMIC_CRED_FIRST = re.compile(
    r"^(?:(?P<mod>[A-ZÁÉÍÓÚÑ][^.\n\t]+?)\.\s+)?(?P<name>[A-ZÁÉÍÓÚÑ][^.\n\t]+?(?:\.|\b))\s*"
    r"(?P<ects>\d+(?:[.,]\d+)?)\s+"
    r"(?P<car>FBA|FB|OBL|OB|OPT|OP|PE|PEX|TFG|TFM|EXT|OIN|DER|HAU)(?:\s+(?P<extra>.*))?$",
    re.IGNORECASE,
)
from sanitizers import (
    unreverse_text,
    sanitize_subject_name,
    curriculum_element_key,
    is_spurious_or_administrative_subject,
    classify_subject_caracter,
    normalize_curso,
    normalize_cuatrimestre,
    detect_academic_language
)

RE_MULTIPLE_SPACES = re.compile(r"[ \t]+")
STOP_WORDS_WITH_UMBRELLA = SPANISH_STOP_WORDS.union(UMBRELLA_BRANCH_WORDS)


def clean_curricular_elements(elements: list) -> list:
    """Descarta ruido de tabla y duplicados tipográficos de un plan BOE.

    Se aplica después de combinar las rutas tabular y textual: así no depende
    de cómo haya segmentado el PDF sus columnas y siempre conserva la primera
    ocurrencia (la tabla curricular principal precede normalmente a la de
    temporalidad).
    """
    if not isinstance(elements, list):
        return []

    cleaned = []
    seen = set()
    for element in elements:
        if not isinstance(element, dict):
            continue
        name = sanitize_subject_name(element.get("nombre_elemento", ""))
        if is_spurious_or_administrative_subject(name):
            continue
        code = str(element.get("codigo_asignatura") or element.get("codigo") or "").strip().lower()
        code = re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", code))
        key = f"code:{code}" if code and re.fullmatch(r"[a-z0-9]{4,12}", code) else f"name:{curriculum_element_key(name)}"
        if not key or key in seen:
            continue
        seen.add(key)
        normalized = dict(element)
        normalized["nombre_elemento"] = name
        cleaned.append(normalized)
    return cleaned


def extract_credit_summary(full_text: str) -> dict:
    """Extrae la tabla/resumen de ECTS sin asumir una única etiqueta BOE."""
    summary = {}
    for label, pattern in RE_CREDIT_SUMMARY:
        match = pattern.search(full_text or "")
        if match:
            summary[label] = match.group(1).replace(",", ".")
    return summary


def detect_curricular_table_header(clean_row: list[str]) -> dict:
    """Devuelve columnas curriculares sólo si la fila es una cabecera real.

    La detección anterior buscaba subcadenas en toda la fila. Eso convertía
    ``Ciclos de los materiales`` en una cabecera por contener ``materia`` y
    hacía desaparecer una asignatura válida. Exigimos dos o más etiquetas de
    columna completas, con límites de palabra.
    """
    columns = {}
    for idx, cell in enumerate(clean_row):
        text = str(cell or "").lower()
        if re.search(r"\b(?:asignaturas?|denominaci[oó]n|nombre|actividad\s+formativa|unidad\s+curricular)\b", text):
            columns.setdefault("subject", idx)
        if re.search(r"\b(?:materias?|m[oó]dulos?)\b", text):
            columns.setdefault("materia", idx)
        if re.search(r"\b(?:cr[eé]ditos?|ects)\b", text):
            columns.setdefault("ects", idx)
        if re.search(r"\b(?:car[aá]cter|tipo|tipus)\b", text):
            columns.setdefault("caracter", idx)
        if re.search(r"\b(?:curso|curs|a[nñ]o)\b", text):
            columns.setdefault("curso", idx)
        if re.search(r"\b(?:cuatrimestre|semestre|periodo|per[ií]odo|quadrimestre)\b", text):
            columns.setdefault("cuatrimestre", idx)
    return columns if len(columns) >= 2 else {}


def first_page_curricular_search_text(page_text: str) -> str:
    """Elimina el preámbulo administrativo sin perder el título del anexo.

    Algunos BOE sitúan el encabezado del plan inmediatamente antes de ``ANEXO
    I``. Recortar desde esa palabra eliminaba precisamente la única referencia
    a la titulación y hacía fallar la desambiguación multi-plan. La firma del
    rector delimita el preámbulo de forma más fiable; si no existe, se conserva
    el texto para que las reglas de rechazo evalúen cada coincidencia.
    """
    text = page_text or ""
    signature_pattern = re.compile(
        r"(?:El Rector|La Rectora|El Secretario General|La Secretaria General|El Director|La Directora)\b",
        re.IGNORECASE,
    )
    signatures = list(signature_pattern.finditer(text))
    if signatures:
        return text[signatures[-1].end():]
    return text


def extract_degree_core_keywords(title: str, univ_name: str = "") -> set:
    """Extrae lemas y palabras clave discriminativas de una titulación."""
    if not title:
        return set()
    norm = title.lower()
    norm = unicodedata.normalize('NFKD', norm).encode('ASCII', 'ignore').decode('utf-8')
    words = re.findall(r'\b[a-z0-9]{3,}\b', norm)
    
    univ_words = set()
    if univ_name:
        u_norm = unicodedata.normalize('NFKD', univ_name.lower()).encode('ASCII', 'ignore').decode('utf-8')
        univ_words = set(re.findall(r'\b[a-z0-9]{3,}\b', u_norm))
        u_acr = ''.join(w[0] for w in univ_name.split() if len(w) > 2).lower()
        if len(u_acr) >= 2:
            univ_words.add(u_acr)
    
    filtered = set(w for w in words if w not in STOP_WORDS_WITH_UMBRELLA and w not in univ_words)
    if filtered:
        return filtered
    
    return set(w for w in words if w not in SPANISH_STOP_WORDS and w not in univ_words)


def is_section_matching(sec_kw: set, target_kw: set) -> bool:
    """Evalúa si un conjunto de palabras clave de sección corresponde a la titulación objetivo."""
    if not sec_kw or not target_kw:
        return False
    
    target_stems = {w[:5] if len(w) >= 5 else w for w in target_kw}
    sec_stems = {w[:5] if len(w) >= 5 else w for w in sec_kw}
    stem_intersection = target_stems.intersection(sec_stems)

    if len(target_kw) == 1:
        # Un título con una única palabra distintiva (p. ej. «Biomédica»)
        # puede aparecer acompañado en el anexo por rama, ámbito o texto de
        # contexto. La coincidencia de esa palabra es suficiente; exigir que
        # la sección no tenga más términos descartaba planes válidos.
        return bool(stem_intersection)
            
    if len(target_kw) == 2:
        return len(stem_intersection) >= 2

    overlap_ratio = len(stem_intersection) / len(target_kw)
    return len(stem_intersection) >= 2 and overlap_ratio >= 0.60


def parse_header_schema(header_line: str) -> list:
    """Deduce el orden de columnas de una cabecera curricular del BOE."""
    clean = header_line.lower().strip()
    clean = re.sub(r"^\d+(?:\.\d+)*\s*[-–—:]?\s*", "", clean)
    clean = clean.replace("estructura del plan de estudios", "").replace(":", "")
    tokens = re.findall(r"[a-záéíóúñç]+", clean)

    schema = []
    seen = set()
    for token in tokens:
        for concept, synonyms in BOE_SCHEMA_CONCEPT_VOCABULARY.items():
            if token in synonyms and concept not in seen:
                schema.append(concept)
                seen.add(concept)
                break
    return schema


def parse_boe_text_curriculum_dynamic(full_text: str, degree_title: str = "", level: str = "") -> dict:
    """Extrae filas tabuladas cuando el PDF no ofrece tablas estructurales."""
    lines = [line.strip() for line in (full_text or "").splitlines() if line.strip()]
    schema = []
    start_idx = -1
    for idx, line in enumerate(lines):
        candidate = parse_header_schema(line)
        if (
            len(candidate) >= 2
            and ("asignatura" in candidate or "materia" in candidate)
            and ("creditos" in candidate or "tipo" in candidate)
        ):
            schema = candidate
            start_idx = idx
            break
    if not schema:
        return {}

    tipo_idx = schema.index("tipo") if "tipo" in schema else -1
    credit_idx = schema.index("creditos") if "creditos" in schema else -1
    if tipo_idx == -1 and credit_idx == -1:
        logger.debug("Ambos índices (tipo y créditos) son -1; aplicando fallback por defecto (_RE_DYNAMIC_CRED_FIRST) al no poder inferir el esquema.")
    pattern = _RE_DYNAMIC_TIPO_FIRST if 0 <= tipo_idx < credit_idx else _RE_DYNAMIC_CRED_FIRST
    extracted = []
    current_module = ""
    seen_names = set()

    for line in lines[start_idx + 1:]:
        line_lower = line.lower()
        if any(marker in line_lower for marker in BOE_SPURIOUS_MARKERS):
            continue
        if re.match(r"^\d+\.\d+\s+condiciones de terminación", line_lower):
            break
        if (
            line.endswith(".")
            and not re.search(r"\b(FBA|FB|OBL|OB|OPT|OP|PE|TFG|TFM)\b", line)
            and not re.search(r"\b\d+\s*$", line)
        ):
            current_module = line.rstrip(".")
            continue

        match = pattern.match(line)
        if not match:
            continue
        module = (match.group("mod") or current_module or "").strip()
        name = sanitize_subject_name(match.group("name").strip().rstrip("."))
        if not name or name.lower() in seen_names:
            continue
        if any(marker in name.lower() for marker in BOE_SPURIOUS_MARKERS):
            continue
        seen_names.add(name.lower())
        ects = match.group("ects").replace(",", ".")
        character = classify_subject_caracter(match.group("car"), name)
        extracted.append({
            "modulo": module,
            "materia": module,
            "nombre_elemento": name,
            "creditos": ects,
            "creditos_ects": ects,
            "tipo": character,
            "caracter": character,
            "curso": "",
            "cuatrimestre": "",
            "idioma": detect_academic_language(name),
        })

    is_degree = "grado" in (degree_title or level or "").lower()
    summary = extract_credit_summary(full_text)
    if "Créditos Totales" not in summary:
        # El valor reglamentario es sólo un fallback; una declaración explícita
        # del BOE (por ejemplo, 90 ECTS) siempre debe prevalecer.
        summary["Créditos Totales"] = str(GRADO_STANDARD_ECTS if is_degree else MASTER_MIN_ECTS)
    extracted = clean_curricular_elements(extracted)
    return {
        "resumen_creditos": summary,
        "total_elementos": len(extracted),
        "elementos_curriculares": extracted,
    }


def _read_pdf_bytes(pdf_input) -> tuple[bytes | None, str | None]:
    """Normaliza la entrada sin abrir el PDF más de una vez para su análisis."""
    try:
        if isinstance(pdf_input, (bytes, bytearray)):
            raw = bytes(pdf_input)
        elif isinstance(pdf_input, io.BytesIO):
            raw = pdf_input.getvalue()
        elif isinstance(pdf_input, str) and os.path.isfile(pdf_input):
            with open(pdf_input, "rb") as stream:
                raw = stream.read()
        else:
            return None, None
    except OSError as error:
        logger.warning("No se pudo leer el PDF %s: %s", pdf_input, error)
        return None, None
    return raw, hashlib.sha256(raw).hexdigest()


def _section_mask(page_texts: list[str], target_title: str, univ_name: str) -> tuple[list[bool], bool, bool]:
    """Delimita la sección de la titulación dentro de resoluciones multi-plan."""
    target_keywords = extract_degree_core_keywords(target_title, univ_name)
    sections = []
    for page_idx, page_text in enumerate(page_texts):
        searchable = first_page_curricular_search_text(page_text) if page_idx == 0 else page_text
        # Primero inspeccionamos línea a línea: aplicar la expresión sobre toda
        # la página puede hacer que un título codicioso absorba el anexo
        # siguiente y oculte una resolución multi-titulación.
        fragments = [line.strip() for line in searchable.splitlines() if line.strip()]
        if not fragments:
            fragments = [searchable]
        page_sections = []
        for fragment in fragments:
            for pattern in RE_DEGREE_SECTION_MARKERS:
                for match in pattern.finditer(fragment):
                    raw = match.group(0).strip()
                    if RE_PREAMBLE_REJECTION.search(raw):
                        continue
                    keywords = extract_degree_core_keywords(raw, univ_name)
                    if keywords:
                        page_sections.append((page_idx, keywords))
        # Los títulos partidos en dos líneas no se detectan individualmente.
        # En ese caso conservamos el análisis completo de la página.
        if not page_sections:
            for pattern in RE_DEGREE_SECTION_MARKERS:
                for match in pattern.finditer(searchable):
                    raw = match.group(0).strip()
                    if RE_PREAMBLE_REJECTION.search(raw):
                        continue
                    keywords = extract_degree_core_keywords(raw, univ_name)
                    if keywords:
                        page_sections.append((page_idx, keywords))
        sections.extend(page_sections)

    is_multi = any(
        left_keywords.difference(right_keywords) and right_keywords.difference(left_keywords)
        for _, left_keywords in sections for _, right_keywords in sections
    )
    if not is_multi or not target_keywords:
        return [True] * len(page_texts), False, False

    mask, active, found = [], False, False
    for page_idx in range(len(page_texts)):
        for section_page, keywords in sections:
            if section_page == page_idx:
                active = is_section_matching(keywords, target_keywords)
                found = found or active
        mask.append(active)
    return mask, found, True


def _section_headers_on_page(positioned_lines: list[tuple[float, str]], target_title: str, univ_name: str) -> list[tuple[float, bool]]:
    """Detecta los cambios de titulación y su posición vertical en una página."""
    target_keywords = extract_degree_core_keywords(target_title, univ_name)
    headers = []
    for index, (top, line) in enumerate(positioned_lines):
        combined = " ".join(text for _, text in positioned_lines[index:min(index + 3, len(positioned_lines))])
        for pattern in RE_DEGREE_SECTION_MARKERS:
            match = pattern.search(combined)
            if not match:
                continue
            raw = match.group(0).strip()
            if RE_PREAMBLE_REJECTION.search(raw):
                continue
            keywords = extract_degree_core_keywords(raw, univ_name)
            if keywords:
                headers.append((top, is_section_matching(keywords, target_keywords)))
            break
    return headers


def _numeric_ects(value: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _curricular_element(name: str, ects: str = "", caracter: str = "", curso: str = "", cuatrimestre: str = "", materia: str = "", modulo: str = "") -> dict | None:
    name = sanitize_subject_name(name)
    if not name or is_spurious_or_administrative_subject(name):
        return None
    ects_number = _numeric_ects(ects)
    normalized_course, rescued_materia = normalize_curso(curso, materia, ects_number)
    return {
        "nombre_elemento": name,
        "tipo_elemento": "Asignatura",
        "materia": materia or rescued_materia,
        "modulo": modulo,
        "creditos": ects_number,
        "creditos_ects": ects_number,
        "caracter": classify_subject_caracter(caracter, name),
        "curso": normalized_course,
        "cuatrimestre": normalize_cuatrimestre(cuatrimestre),
        "idioma": detect_academic_language(name),
    }


def _extract_rows_from_table(rows: list[list[str]]) -> list[dict]:
    """Extrae filas sólo cuando la propia tabla declara una columna de asignatura.

    Rechazar tablas sin cabecera curricular evita convertir resúmenes por
    materias en asignaturas ficticias. Las filas multilínea se unen a la fila
    curricular anterior dentro de la misma tabla.
    """
    columns = {}
    extracted = []
    for row in rows or []:
        clean = [unreverse_text(RE_MULTIPLE_SPACES.sub(" ", str(cell).strip())) if cell else "" for cell in row]
        if not any(clean):
            continue
        header = detect_curricular_table_header(clean)
        if header:
            columns = header if "subject" in header and ("ects" in header or "caracter" in header) else {}
            continue
        if not columns:
            continue
        subject_index = columns["subject"]
        subject = clean[subject_index] if subject_index < len(clean) else ""
        ects_index = columns.get("ects", -1)
        caracter_index = columns.get("caracter", -1)
        ects = clean[ects_index] if 0 <= ects_index < len(clean) else ""
        caracter = clean[caracter_index] if 0 <= caracter_index < len(clean) else ""
        materia_index = columns.get("materia", -1)
        curso_index = columns.get("curso", -1)
        cuatrimestre_index = columns.get("cuatrimestre", -1)
        materia = clean[materia_index] if 0 <= materia_index < len(clean) else ""
        curso = clean[curso_index] if 0 <= curso_index < len(clean) else ""
        cuatrimestre = clean[cuatrimestre_index] if 0 <= cuatrimestre_index < len(clean) else ""

        # Una celda sin ECTS/tipo que empieza en minúscula es casi siempre la
        # continuación visual de la asignatura anterior.
        if subject and extracted and not ects and not caracter and subject[:1].islower():
            extracted[-1]["nombre_elemento"] = sanitize_subject_name(
                f"{extracted[-1]['nombre_elemento'].rstrip(' :-,')} {subject}"
            )
            continue
        element = _curricular_element(subject, ects, caracter, curso, cuatrimestre, materia)
        if element:
            extracted.append(element)
    return extracted


def _line_has_curricular_schema(line: str) -> bool:
    schema = parse_header_schema(line)
    return "asignatura" in schema and ("creditos" in schema or "tipo" in schema)


def _extract_rows_from_positioned_lines(lines: list[str]) -> list[dict]:
    """Extrae el mismo tipo de fila desde la geometría cuando no hay bordes.

    No es un segundo intento del documento: las líneas forman parte del modelo
    de cada página, junto a las tablas detectadas por el motor geométrico.
    """
    extracted, current_module, schema_seen = [], "", False
    for position, line in enumerate(lines):
        combined = " ".join(lines[position:min(position + 2, len(lines))])
        if _line_has_curricular_schema(line) or _line_has_curricular_schema(combined):
            schema_seen = True
            continue
        if not schema_seen:
            continue
        lower = line.lower()
        if re.match(r"^\d+(?:\.\d+)?\s+condiciones de terminaci[oó]n", lower):
            schema_seen = False
            continue
        if any(marker in lower for marker in BOE_SPURIOUS_MARKERS):
            continue
        match = _RE_DYNAMIC_TIPO_FIRST.match(line) or _RE_DYNAMIC_CRED_FIRST.match(line)
        if match:
            name = match.group("name").strip().rstrip(".")
            element = _curricular_element(
                name,
                match.group("ects"),
                match.group("car"),
                materia=(match.group("mod") or current_module or "").strip(),
                modulo=(match.group("mod") or current_module or "").strip(),
            )
            if element:
                extracted.append(element)
            continue
        if line.endswith(".") and len(line) > 4 and not re.search(r"\b(?:FB|FBA|OBL|OB|OPT|OP|PE|TFG|TFM)\b", line, re.IGNORECASE):
            current_module = line.rstrip(".")
    return extracted


def _merge_curricular_candidates(candidates: list[dict]) -> list[dict]:
    """Combina representaciones del mismo documento, priorizando filas completas."""
    merged = []
    by_key = {}
    for element in candidates:
        code = str(element.get("codigo_asignatura") or element.get("codigo") or "").strip().lower()
        code = re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", code))
        key = f"code:{code}" if code and re.fullmatch(r"[a-z0-9]{4,12}", code) else f"name:{curriculum_element_key(element.get('nombre_elemento', ''))}"
        if not key:
            continue
        previous = by_key.get(key)
        if previous is None:
            by_key[key] = element
            merged.append(element)
            continue
        # La representación tabular suele aportar mejor temporalidad y ECTS.
        if previous.get("creditos_ects") is None and element.get("creditos_ects") is not None:
            index = merged.index(previous)
            merged[index] = element
            by_key[key] = element
    return clean_curricular_elements(merged)


_DOCUMENT_MODEL_CACHE_LOCK = threading.Lock()
_DOCUMENT_MODEL_CACHE: collections.OrderedDict[str, tuple[list[dict], str]] = collections.OrderedDict()
_DOCUMENT_MODEL_CACHE_MAX_SIZE = 128


def _get_cached_document_model(pdf_sha256: str) -> tuple[list[dict], str] | None:
    if not pdf_sha256:
        return None
    with _DOCUMENT_MODEL_CACHE_LOCK:
        if pdf_sha256 in _DOCUMENT_MODEL_CACHE:
            _DOCUMENT_MODEL_CACHE.move_to_end(pdf_sha256)
            return _DOCUMENT_MODEL_CACHE[pdf_sha256]
    return None


def _store_cached_document_model(pdf_sha256: str, model: tuple[list[dict], str]) -> None:
    if not pdf_sha256 or not model:
        return
    with _DOCUMENT_MODEL_CACHE_LOCK:
        _DOCUMENT_MODEL_CACHE[pdf_sha256] = model
        if len(_DOCUMENT_MODEL_CACHE) > _DOCUMENT_MODEL_CACHE_MAX_SIZE:
            _DOCUMENT_MODEL_CACHE.popitem(last=False)


def clear_document_model_cache() -> None:
    """Vacía la caché en memoria de modelos de PDFs del BOE."""
    with _DOCUMENT_MODEL_CACHE_LOCK:
        _DOCUMENT_MODEL_CACHE.clear()


def _build_document_model(raw_pdf: bytes, original_input, pdf_sha256: str = "") -> tuple[list[dict], str]:
    """Lee el documento completo una vez y devuelve páginas con texto, líneas y tablas."""
    if pdf_sha256:
        cached = _get_cached_document_model(pdf_sha256)
        if cached is not None:
            return cached

    pages = []
    try:
        with pdfplumber.open(io.BytesIO(raw_pdf)) as pdf:
            for page in pdf.pages:
                text = unreverse_text(page.extract_text() or "")
                
                # Búsqueda de tablas geométricas
                tables_raw = page.find_tables()
                tables = [{"rows": table.extract(), "top": table.bbox[1]} for table in tables_raw]
                
                # Optimización B: Análisis posicional detallado de palabras
                # Solo se calcula la geometría de palabras si la página contiene tablas o indicios curriculares/anexos.
                # En páginas netamente administrativas sin tablas, splitlines() es idéntico y 10x más rápido.
                has_curricular_hints = bool(
                    tables
                    or RE_CURRICULAR_PAGE_HINTS.search(text)
                    or any(marker.search(text) for marker in RE_DEGREE_SECTION_MARKERS)
                )

                positioned_lines = []
                if has_curricular_hints:
                    words = page.extract_words(use_text_flow=True) or []
                    buckets = []
                    for word in sorted(words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0)))):
                        if not str(word.get("text") or "").strip():
                            continue
                        top = float(word.get("top", 0))
                        if not buckets or abs(top - buckets[-1][0]) > 3.5:
                            buckets.append([top, [word]])
                        else:
                            buckets[-1][1].append(word)
                    for top, group in buckets:
                        line = unreverse_text(" ".join(str(word.get("text") or "") for word in sorted(group, key=lambda item: float(item.get("x0", 0))))).strip()
                        if line:
                            positioned_lines.append((top, line))

                pages.append({
                    "text": text,
                    "lines": [line for _, line in positioned_lines] or [line.strip() for line in text.splitlines() if line.strip()],
                    "positioned_lines": positioned_lines,
                    "tables": tables,
                })
    except Exception as error:
        logger.warning("No se pudo construir el modelo geométrico del PDF: %s", error)

    full_text = "\n".join(page["text"] for page in pages)
    if len(full_text.strip()) >= 50:
        result = (pages, full_text)
        if pdf_sha256:
            _store_cached_document_model(pdf_sha256, result)
        return result

    # OCR es una modalidad de lectura para documentos imagen, no una segunda
    # estrategia de extracción de asignaturas.
    try:
        from ocr_parser import OCRPDFParser
        ocr_text = OCRPDFParser().extract_text_via_ocr(original_input)
        if len((ocr_text or "").strip()) >= 50:
            result = ([{"text": ocr_text, "lines": [line.strip() for line in ocr_text.splitlines() if line.strip()], "positioned_lines": [], "tables": []}], ocr_text)
            if pdf_sha256:
                _store_cached_document_model(pdf_sha256, result)
            return result
    except Exception as error:
        logger.info("No se pudo leer mediante OCR el PDF sin capa de texto: %s", error)
    return pages, full_text


def parse_boe_pdf(pdf_filepath, target_title: str = "", univ_name: str = "") -> dict:
    """Analiza un PDF BOE mediante un único modelo profundo del documento.

    Cada página se inspecciona una sola vez para obtener texto, posiciones y
    tablas. Desde ese modelo se delimita la titulación y se reconstruyen sus
    filas curriculares; no se encadenan lectores alternativos según el número
    de resultados obtenido.
    """
    raw_pdf, pdf_sha256 = _read_pdf_bytes(pdf_filepath)
    empty = {
        "resumen_creditos": {}, "total_elementos": 0, "elementos_curriculares": [],
        "pdf_sha256": pdf_sha256, "idioma_predominante": "es",
        "metodo_extraccion": "analisis_profundo_pdf",
    }
    if not raw_pdf or not raw_pdf.startswith(b"%PDF"):
        return empty

    pages, full_text = _build_document_model(raw_pdf, pdf_filepath, pdf_sha256=pdf_sha256)
    page_texts = [page["text"] for page in pages]
    mask, target_found, is_multi_document = _section_mask(page_texts, target_title, univ_name)
    if target_title and is_multi_document and not target_found:
        return empty

    relevant_pages = [page for index, page in enumerate(pages) if index < len(mask) and mask[index]]
    relevant_text = "\n".join(page["text"] for page in relevant_pages) or full_text
    candidates = []
    current_section_matches = not is_multi_document
    for page_index, page in enumerate(pages):
        page_table_candidates = []
        headers = _section_headers_on_page(page.get("positioned_lines", []), target_title, univ_name) if is_multi_document else []
        for table in page["tables"]:
            if is_multi_document:
                for header_top, header_matches in headers:
                    if header_top <= table["top"] + 10:
                        current_section_matches = header_matches
                if not current_section_matches:
                    continue
            elif page_index >= len(mask) or not mask[page_index]:
                continue
            page_table_candidates.extend(_extract_rows_from_table(table["rows"]))
        candidates.extend(page_table_candidates)

        # Las tablas con cabecera tienen mayor evidencia que la lectura lineal.
        # Las líneas se usan sólo en páginas sin una tabla curricular válida.
        if not page_table_candidates and page_index < len(mask) and mask[page_index]:
            candidates.extend(_extract_rows_from_positioned_lines(page["lines"]))
    elements = _merge_curricular_candidates(candidates)
    return {
        "resumen_creditos": extract_credit_summary(relevant_text),
        "total_elementos": len(elements),
        "elementos_curriculares": elements,
        "pdf_sha256": pdf_sha256,
        "idioma_predominante": detect_academic_language(relevant_text[:20000]),
        "metodo_extraccion": "analisis_profundo_pdf",
        "paginas_analizadas": len(relevant_pages),
    }
