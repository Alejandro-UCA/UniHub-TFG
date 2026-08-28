import os
import re
import io
import hashlib
import unicodedata
import logging
from functools import lru_cache
import pypdf
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
    ("Formación Básica", re.compile(r"(?:Formaci[oó]n\s+B[aá]sica|FB)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Obligatorias", re.compile(r"(?:Obligatorias?|OB)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Optativas", re.compile(r"(?:Optativas?|OP)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Prácticas Externas", re.compile(r"(?:Pr[aá]cticas\s+Externas?|PE)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Trabajo Fin de Grado / Máster", re.compile(r"(?:Trabajo\s+Fin\s+de\s+(?:Grado|M[aá]ster)|TFG|TFM)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)),
    ("Créditos Totales", re.compile(r"(?:Cr[eé]ditos\s+Totales?|Total)\s*[:.\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE))
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
    is_spurious_or_administrative_subject,
    classify_subject_caracter,
    normalize_curso,
    normalize_cuatrimestre,
    detect_academic_language
)

RE_MULTIPLE_SPACES = re.compile(r"[ \t]+")
STOP_WORDS_WITH_UMBRELLA = SPANISH_STOP_WORDS.union(UMBRELLA_BRANCH_WORDS)


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
        if len(sec_kw) == 1:
            return len(stem_intersection) == 1
        return False
            
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
    return {
        "resumen_creditos": {
            "Créditos Totales": str(GRADO_STANDARD_ECTS if is_degree else MASTER_MIN_ECTS)
        },
        "total_elementos": len(extracted),
        "elementos_curriculares": extracted,
    }


def parse_boe_pdf(pdf_filepath, target_title: str = "", univ_name: str = "") -> dict:
    """
    Motor híbrido de extracción de planes de estudio del BOE:
    - Soporta rutas en disco (str), flujos binarios en memoria (bytes) y objetos io.BytesIO (Green IT).
    - Desambiguación multi-grado para resoluciones con múltiples titulaciones (Anexo I, II, III...).
    - Extracción estructural de tablas con pdfplumber y fallback textual regex.
    - Detección automática de lengua cooficial (ES, CA, GL, EU, EN) a nivel de plan y asignaturas.
    - Fallback de OCR asistido para resoluciones históricas escaneadas.
    """
    resumen_creditos = {}
    elementos_curriculares = []
    seen_elements = set()
    raw_text_parts = []

    is_valid_pdf = False
    if isinstance(pdf_filepath, (bytes, bytearray)):
        pdf_stream = io.BytesIO(pdf_filepath)
        pdf_sha256 = hashlib.sha256(pdf_filepath).hexdigest()
        is_valid_pdf = pdf_filepath.startswith(b"%PDF")
    elif isinstance(pdf_filepath, io.BytesIO):
        pdf_stream = pdf_filepath
        pdf_bytes = pdf_filepath.getvalue()
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        is_valid_pdf = pdf_bytes.startswith(b"%PDF")
    else:
        pdf_stream = pdf_filepath
        pdf_sha256 = None
        if isinstance(pdf_filepath, str) and os.path.exists(pdf_filepath):
            try:
                h = hashlib.sha256()
                with open(pdf_filepath, "rb") as f:
                    head = f.read(5)
                    is_valid_pdf = head.startswith(b"%PDF")
                    f.seek(0)
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                pdf_sha256 = h.hexdigest()
            except OSError as error:
                logger.warning("No se pudo calcular el SHA-256 de %s: %s", pdf_filepath, error)

    if not is_valid_pdf:
        logger.info(
            "El recurso '%s' no contiene la cabecera mágica %%PDF (es probablemente HTML/portal web). Se omite el análisis.",
            pdf_filepath if isinstance(pdf_filepath, str) else "stream",
        )
        return {
            "resumen_creditos": {},
            "total_elementos": 0,
            "elementos_curriculares": [],
            "pdf_sha256": pdf_sha256,
            "idioma_predominante": "es",
        }

    try:
        reader = pypdf.PdfReader(pdf_stream)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                raw_text_parts.append(unreverse_text(text))
    except Exception as error:
        logger.warning("No se pudo extraer texto del PDF: %s", error)

    full_text = "\n".join(raw_text_parts)

    # Fallback OCR para PDFs escaneados
    if len(full_text.strip()) < 50:
        try:
            from ocr_parser import OCRPDFParser
            ocr_parser = OCRPDFParser()
            ocr_input = pdf_filepath if (isinstance(pdf_filepath, str) and os.path.exists(pdf_filepath)) else pdf_stream
            ocr_text = ocr_parser.extract_text_via_ocr(ocr_input)
            if len(ocr_text.strip()) >= 50:
                full_text = ocr_text
                raw_text_parts = [full_text]
        except Exception as error:
            logger.info("No se pudo aplicar el fallback OCR al PDF: %s", error)

    # -------------------------------------------------------------------------
    # MOTOR DE DESAMBIGUACIÓN MULTI-GRADO:
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

        if not has_any_match:
            return {
                "resumen_creditos": {},
                "total_elementos": 0,
                "elementos_curriculares": []
            }

    # 1. Resumen de Créditos
    relevant_text = "\n".join([raw_text_parts[i] for i in range(len(raw_text_parts)) if i < len(page_inclusion_mask) and page_inclusion_mask[i]]) or full_text
    for label, pattern in RE_CREDIT_SUMMARY:
        match = pattern.search(relevant_text)
        if match:
            resumen_creditos[label] = match.group(1)

    # 1.1 Pre-filtrado Inteligente de Páginas con Continuidad y Red de Seguridad
    total_pages = len(raw_text_parts)
    candidate_page_mask = [True] * total_pages

    if total_pages > 2:
        for idx in range(total_pages):
            p_text = raw_text_parts[idx]
            # Si el documento es multi-grado, respetar estrictamente la inclusión de la sección objetivo
            if is_multi_degree_doc and idx < len(page_inclusion_mask) and not page_inclusion_mask[idx]:
                candidate_page_mask[idx] = False
                continue

            # Comprobar si la página contiene indicadores curriculares
            has_hints = bool(RE_CURRICULAR_PAGE_HINTS.search(p_text))
            candidate_page_mask[idx] = has_hints

        # Regla de Continuidad de Tablas: si la página anterior tenía contenido curricular, incluir la siguiente
        for idx in range(1, total_pages):
            if candidate_page_mask[idx - 1] and not candidate_page_mask[idx]:
                candidate_page_mask[idx] = True

        # Red de seguridad: si todas las páginas fueron descartadas, habilitar todas
        if not any(candidate_page_mask):
            candidate_page_mask = [True] * total_pages

    # 2. Extracción Estructural de Tablas con pdfplumber
    try:
        if isinstance(pdf_stream, io.BytesIO):
            pdf_stream.seek(0)

        with pdfplumber.open(pdf_stream) as pdf:
            current_modulo = ""
            current_materia = ""
            current_state = False if is_multi_degree_doc else True

            for page_idx, page in enumerate(pdf.pages):
                if page_idx < len(candidate_page_mask) and not candidate_page_mask[page_idx]:
                    continue

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

                found_tables = page.find_tables()
                if not found_tables:
                    continue

                for t_obj in found_tables:
                    t_top = t_obj.bbox[1]

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

                    for row in table_data:
                        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                            continue

                        clean_row = [unreverse_text(RE_MULTIPLE_SPACES.sub(" ", str(cell).strip())) if cell else "" for cell in row]
                        row_str = " ".join(clean_row).lower()

                        if any(hk in row_str for hk in ["asignatura", "denominaci", "materia", "crédito", "credito", "ects", "carácter", "caracter", "curso", "módulo", "modulo"]):
                            for idx, cell_str in enumerate(clean_row):
                                c_lower = cell_str.lower()
                                if any(kw in c_lower for kw in ["asignatura", "denominaci", "nombre", "actividad formativa", "unidad curricular"]):
                                    subject_col_idx = idx
                                elif any(kw in c_lower for kw in ["materia", "modulo", "módulo"]):
                                    materia_col_idx = idx
                                elif any(kw in c_lower for kw in ["crédito", "credito", "ects"]):
                                    ects_col_idx = idx
                                elif any(kw in c_lower for kw in ["carácter", "caracter", "tipo", "tipus"]):
                                    caracter_col_idx = idx
                                elif any(kw in c_lower for kw in ["curso", "curs", "ano", "año"]):
                                    curso_col_idx = idx
                                elif any(kw in c_lower for kw in ["cuatrimestre", "semestre", "periodo", "quadrimestre"]):
                                    cuatrimestre_col_idx = idx
                            continue

                        if subject_col_idx == -1 and len(clean_row) >= 3:
                            subject_col_idx = 0
                            ects_col_idx = 1 if len(clean_row) > 1 else -1

                        if subject_col_idx != -1 and subject_col_idx < len(clean_row):
                            subj_raw = clean_row[subject_col_idx]
                            materia_raw = clean_row[materia_col_idx] if (materia_col_idx != -1 and materia_col_idx < len(clean_row)) else ""
                            ects_raw = clean_row[ects_col_idx] if (ects_col_idx != -1 and ects_col_idx < len(clean_row)) else ""
                            caracter_raw = clean_row[caracter_col_idx] if (caracter_col_idx != -1 and caracter_col_idx < len(clean_row)) else ""
                            curso_raw = clean_row[curso_col_idx] if (curso_col_idx != -1 and curso_col_idx < len(clean_row)) else ""
                            cuat_raw = clean_row[cuatrimestre_col_idx] if (cuatrimestre_col_idx != -1 and cuatrimestre_col_idx < len(clean_row)) else ""

                            if not subj_raw and materia_raw:
                                subj_raw = materia_raw

                            subj_clean = sanitize_subject_name(subj_raw)
                            if not subj_clean or is_spurious_or_administrative_subject(subj_clean):
                                continue

                            # Validación numérica de créditos ECTS
                            ects_num = None
                            m_cr = re.search(r"(\d+(?:[.,]\d+)?)", ects_raw)
                            if m_cr:
                                try:
                                    ects_num = float(m_cr.group(1).replace(",", "."))
                                except ValueError:
                                    ects_num = None

                            norm_key = re.sub(r"[^\w\s]", "", subj_clean.lower()).strip()
                            if norm_key in seen_elements:
                                continue
                            seen_elements.add(norm_key)

                            caracter_norm = classify_subject_caracter(caracter_raw, subj_clean)
                            curso_norm, materia_rescatada = normalize_curso(curso_raw, materia_raw or current_materia, ects_num)
                            cuat_norm = normalize_cuatrimestre(cuat_raw)
                            lang_code = detect_academic_language(subj_clean)

                            elementos_curriculares.append({
                                "nombre_elemento": subj_clean,
                                "tipo_elemento": "Asignatura",
                                "materia": materia_raw or materia_rescatada or current_materia,
                                "modulo": current_modulo,
                                "creditos": ects_num,
                                "creditos_ects": ects_num,
                                "caracter": caracter_norm,
                                "curso": curso_norm,
                                "cuatrimestre": cuat_norm,
                                "idioma": lang_code
                            })
    except Exception as error:
        logger.warning("Falló el análisis tabular del PDF BOE: %s", error, exc_info=True)

    # 3. Fallback dinámico para texto tabulado sin estructura PDF detectable.
    if len(elementos_curriculares) < 3:
        dynamic = parse_boe_text_curriculum_dynamic(relevant_text, target_title)
        for element in dynamic.get("elementos_curriculares", []):
            norm_key = re.sub(r"[^\w\s]", "", element.get("nombre_elemento", "").lower()).strip()
            if norm_key and norm_key not in seen_elements:
                seen_elements.add(norm_key)
                elementos_curriculares.append(element)
        if not resumen_creditos and dynamic.get("resumen_creditos"):
            resumen_creditos.update(dynamic["resumen_creditos"])

    # 4. Último fallback por líneas con un patrón explícito de ECTS.
    if len(elementos_curriculares) < 3:
        lines = relevant_text.splitlines()
        for line in lines:
            line_clean = sanitize_subject_name(line)
            if len(line_clean) < 4 or is_spurious_or_administrative_subject(line_clean):
                continue
            
            m_ects = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:cr[eé]ditos?|ects|cr\.?)\b", line, re.IGNORECASE)
            if m_ects:
                try:
                    cr_val = float(m_ects.group(1).replace(",", "."))
                except ValueError:
                    cr_val = None
                
                nom_asig = sanitize_subject_name(line[:m_ects.start()].strip())
                if nom_asig and len(nom_asig) >= 4 and not is_spurious_or_administrative_subject(nom_asig):
                    norm_k = re.sub(r"[^\w\s]", "", nom_asig.lower()).strip()
                    if norm_k not in seen_elements:
                        seen_elements.add(norm_k)
                        course, rescued_subject = normalize_curso(line, "", cr_val)
                        elementos_curriculares.append({
                            "nombre_elemento": nom_asig,
                            "tipo_elemento": "Asignatura",
                            "materia": rescued_subject,
                            "modulo": "",
                            "creditos": cr_val,
                            "creditos_ects": cr_val,
                            "caracter": classify_subject_caracter("", nom_asig),
                            "curso": course,
                            "cuatrimestre": normalize_cuatrimestre(line),
                            "idioma": detect_academic_language(nom_asig)
                        })

    return {
        "resumen_creditos": resumen_creditos,
        "total_elementos": len(elementos_curriculares),
        "elementos_curriculares": elementos_curriculares,
        "pdf_sha256": pdf_sha256,
        "idioma_predominante": detect_academic_language(relevant_text[:20000]),
    }
