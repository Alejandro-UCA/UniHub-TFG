"""Motor de extracción de asignaturas y mallas curriculares desde tablas y estructuras HTML."""

from __future__ import annotations

import logging
import re
import unicodedata
import urllib
import urllib.parse
from bs4 import BeautifulSoup

from core.config import (
    DEFAULT_SUBJECT_ECTS,
    HEADER_KEYWORDS,
    INVALID_METADATA_LABELS,
    INVALID_SUBJECT_KEYWORDS,
)
from utils.sanitizers import (
    classify_subject_caracter,
    curriculum_element_key,
    detect_academic_language,
    extract_subjects_from_card_blocks,
    is_spurious_or_administrative_subject,
    is_valid_curricular_table,
    normalize_cuatrimestre,
    normalize_curso,
    sanitize_string_value,
    sanitize_subject_name,
)

from utils.text_utils import normalize_unicode_text as normalize_text
from extractors.curriculum_recovery import (
    discover_linked_curriculum_documents,
    discover_linked_curriculum_pages,
    discover_related_academic_origins,
    extract_curriculum_from_json_tree,
    extract_hydration_payload,
    extract_prose_curriculum,
    extract_structured_curriculum,
    generic_curriculum_path_candidates,
    infer_declared_total_ects,
    is_summary_curriculum_name,
    matches_academic_level,
    merge_curriculum_elements,
)
from parsers.schema_org import extract_schema_org_curriculum
try:
    from quality.curriculum_validator import infer_missing_courses_in_curriculum
except ImportError:
    from quality.curriculum_validator import infer_missing_courses_in_curriculum

logger = logging.getLogger(__name__)

_RE_SUMMARY_ROW_MARKERS = re.compile(
    r"^(?:totals?|totales?|total\s+cr[eé]ditos?|[1-6][º°a-z]*\s+(?:curs|curso|ano|año)|[1-6]r?\s+i\s+[1-6]t?\s+cursos?|formaci[oó]\s+b[aà]sica|optatives?|optativas?|menci[oó]\s+en\s+.*|itinerario\s+.*|menci[oó]n\s+.*)$",
    re.IGNORECASE,
)

_OPTIONAL_SECTION_MARKERS = (
    "optativa",
    "optatividad",
    "optatives",
    "optional subject",
    "optional credit",
    "elective",
    "electives",
    "aukerako",
)


def _is_optional_curriculum_section(text: str) -> bool:
    """Detecta una sección de oferta optativa en cualquier idioma soportado."""
    normalized = normalize_text(text or "")
    return bool(normalized) and any(marker in normalized for marker in _OPTIONAL_SECTION_MARKERS)


def _table_has_optional_context(table) -> bool:
    """Indica si la tabla pertenece al encabezado curricular optativo más cercano."""
    caption = table.find("caption")
    if caption and _is_optional_curriculum_section(caption.get_text(" ", strip=True)):
        return True
    for heading in table.find_all_previous(
        ["h1", "h2", "h3", "h4", "h5", "h6", "legend", "button", "summary"]
    ):
        text = heading.get_text(" ", strip=True)
        if not text:
            continue
        return _is_optional_curriculum_section(text)
    return False


def _extract_subject_cell_text(cell) -> str:
    """Obtiene el nombre de la asignatura de una celda con docentes/contactos."""
    if cell is None:
        return ""
    raw_parts = [
        part.strip()
        for part in cell.get_text(separator=" | ", strip=True).split("|")
        if part.strip()
    ]
    result = []
    for part in raw_parts:
        part = re.sub(r"^\s*\d{4,8}\s*:\s*", "", part).strip()
        if not part:
            continue
        # Los correos y el paréntesis inmediatamente anterior marcan el
        # bloque de docente, que no forma parte del nombre curricular.
        if "@" in part or re.match(r"^[\[(]?https?://", part, re.IGNORECASE):
            break
        if result and re.search(r"\(\s*$", part):
            break
        result.append(part)
    return sanitize_subject_name(" ".join(result))


def _infer_uniform_curricular_ects(soup: BeautifulSoup) -> float | None:
    """Detecta una carga común explícita para asignaturas sin columna ECTS.

    Algunos planes HTML declaran en la prosa que todas las asignaturas tienen
    una carga fija y después omiten esa columna en las tablas. Sólo se acepta
    una declaración con cuantificador universal y una unidad curricular
    explícita; no se infieren créditos a partir de una suma, de una fila de
    resumen o de una convención editorial.
    """
    if not soup:
        return None
    page_text = soup.get_text(" ", strip=True)
    if not page_text:
        return None
    pattern = re.compile(
        r"\b(?:todas?|cada|all|each)\s+(?:las?\s+|los?\s+|as?\s+|the\s+)?"
        r"(?:asignaturas?|materias?|subjects?|courses?)\b"
        r".{0,140}?(?:tien(?:en|e)|son|have|are|worth|valen|de)"
        r".{0,40}?(?P<value>\d{1,2}(?:[.,]\d{1,2})?)\s*"
        r"(?:cr[eéè�]ditos?|credits?|ects)\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(page_text):
        try:
            value = float(match.group("value").replace(",", "."))
        except (TypeError, ValueError):
            continue
        if 1.0 <= value <= 30.0:
            return value
    return None


def _fill_explicit_uniform_curricular_ects(
    elementos: list[dict], uniform_ects: float | None
) -> list[dict]:
    """Completa sólo filas docentes sin crédito cuando la fuente lo declara."""
    if uniform_ects is None:
        return elementos
    for item in elementos:
        if not isinstance(item, dict) or item.get("creditos_ects") not in (None, ""):
            continue
        name = str(item.get("nombre_elemento") or "")
        name_low = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
        # Las propias excepciones de la declaración universal no deben heredar
        # el valor común cuando la fila no publica su carga específica.
        if any(marker in name_low for marker in (
            "practic", "internship", "placement", "trabajo fin", "treball de fi",
            "tfg", "tfm", "final project", "thesis",
        )):
            continue
        item["creditos_ects"] = (
            str(int(uniform_ects))
            if float(uniform_ects).is_integer()
            else str(uniform_ects)
        )
    return elementos


def _extract_parallel_html_row(
    tds: list,
    subject_cols: list[int],
    table_curso: str,
    table_cuatrimestre: str,
    base_url: str,
) -> list[dict]:
    """Extrae todos los bloques de una fila con asignaturas en paralelo."""
    extracted = []
    for index, subject_col in enumerate(subject_cols):
        if subject_col >= len(tds):
            continue
        next_subject_col = (
            subject_cols[index + 1]
            if index + 1 < len(subject_cols)
            else len(tds)
        )
        group = tds[subject_col:next_subject_col]
        if not group:
            continue
        cols = [cell.get_text(separator=" ", strip=True) for cell in group]
        raw_name = _extract_subject_cell_text(group[0])
        # Los catálogos suelen anteponer el código interno con un guion largo.
        # Se elimina únicamente esa forma estructural para dejar el nombre
        # docente como identidad visible del elemento.
        raw_name = re.sub(r"^\s*\(?\d{4,8}\)?\s*[–—-]\s*", "", raw_name).strip()
        inline_credit = re.search(
            r"\(\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:cr[eéè�]ditos?|credits?|ects)\s*\)",
            raw_name,
            re.IGNORECASE,
        )
        creditos = None
        ects_value = None
        if inline_credit:
            creditos = inline_credit.group(1).replace(",", ".")
            ects_value = float(creditos)
            raw_name = raw_name[: inline_credit.start()].strip()
        nombre = sanitize_subject_name(raw_name)
        nombre_lower = nombre.lower()
        if (
            len(nombre) < 4
            or len(nombre) > 150
            or _RE_SUMMARY_ROW_MARKERS.match(nombre_lower)
            or is_summary_curriculum_name(nombre)
            or any(nombre_lower == hk for hk in HEADER_KEYWORDS)
            or any(sk in nombre_lower for sk in INVALID_SUBJECT_KEYWORDS)
        ):
            continue

        # La carga puede estar en cualquiera de las celdas del bloque, no
        # necesariamente en una columna con el mismo índice en ambos lados.
        if ects_value is None:
            for value in cols[1:]:
                match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", value)
                if not match:
                    continue
                try:
                    candidate = float(match.group(1).replace(",", "."))
                except ValueError:
                    continue
                if 1.0 <= candidate <= 30.0:
                    ects_value = candidate
                    creditos = (
                        str(int(candidate)) if candidate.is_integer() else str(candidate)
                    )
                    break

        caracter = "OB"
        for value in cols[1:]:
            classified = classify_subject_caracter(value, default="")
            if classified:
                caracter = classified
                break
        if caracter == "OB":
            caracter = classify_subject_caracter(nombre, default="OB") or "OB"
        if _is_html_metadata_subject(nombre, ects_value, caracter) or is_spurious_or_administrative_subject(
            nombre,
            ects_val=ects_value,
            caracter=caracter,
        ):
            continue

        curso = table_curso
        cuatrimestre = table_cuatrimestre or "1C"
        for value in cols[1:]:
            if not curso and any(token in value.lower() for token in (
                "1º", "2º", "3º", "4º", "primer", "segundo", "tercer", "cuarto",
                "1er", "2do", "3er", "4to",
            )):
                curso = normalize_curso(value)[0] or value
            if not table_cuatrimestre and any(token in value.lower() for token in (
                "1c", "2c", "1s", "2s", "primer", "segundo", "anual", "q1", "q2", "s1", "s2",
            )):
                cuatrimestre = normalize_cuatrimestre(value) or cuatrimestre

        codigo = ""
        url_guia = ""
        for cell, value in zip(group, cols):
            if not codigo:
                code_match = re.search(r"\b(?:\d{4,8}|[A-Z]{2,4}\d{2,6})\b", value)
                if code_match:
                    codigo = code_match.group(0)
            anchor = cell.find("a", href=True)
            if anchor and not url_guia:
                href = str(anchor.get("href") or "").strip()
                if href.startswith("http"):
                    url_guia = href
                elif base_url and not href.startswith("javascript:"):
                    url_guia = urllib.parse.urljoin(base_url, href)
        item = {
            "modulo": "",
            "materia": "",
            "codigo_asignatura": codigo,
            "nombre_elemento": nombre,
            "creditos_ects": creditos,
            "caracter": caracter,
            "curso": curso,
            "cuatrimestre": cuatrimestre,
            "idioma": detect_academic_language(nombre),
        }
        if url_guia:
            item["url_guia_docente"] = url_guia
        extracted.append(item)
    return extracted


def _is_html_metadata_subject(name, credits=None, character=""):
    """Distingue etiquetas de portal de prácticas con carga curricular explícita."""
    low = name.casefold()
    matches = [label for label in INVALID_METADATA_LABELS
               if low == label or (len(label) > 6 and label in low)]
    if not matches:
        return False
    internship_labels = {
        "prácticas externas", "practicas externas", "pràctiques externes",
        "practiques externes", "kanpoko praktikak",
    }
    # No basta encontrar «prácticas» en un menú o una tabla de contactos.
    # La fila debe declarar tanto su carácter como sus créditos.
    return not (
        set(matches) <= internship_labels
        and character == "PE"
        and credits is not None and 0 < credits <= 30
    )


def normalize_table_rows_with_spans(rows: list) -> list[tuple[object, list, list[str]]]:
    """Expande celdas con rowspan y colspan para reconstruir una cuadrícula regular.
    
    Devuelve una lista de tuplas: (row_tag, lista_de_celdas_tag, lista_de_textos_raw).
    Las celdas propagadas por rowspan conservan la referencia al Tag original
    y su contenido de texto para preservar el alineamiento exacto de columnas.
    """
    grid = []
    active_spans = {}  # col_idx -> {"remaining": int, "tag": Tag, "text": str}

    for row in rows:
        cells_in_row = row.find_all(["td", "th"])
        if not cells_in_row and not active_spans:
            continue

        row_tags = []
        row_texts = []
        col_idx = 0
        cell_iter = iter(cells_in_row)

        while True:
            if col_idx in active_spans:
                span_info = active_spans[col_idx]
                row_tags.append(span_info["tag"])
                row_texts.append(span_info["text"])
                span_info["remaining"] -= 1
                if span_info["remaining"] <= 0:
                    del active_spans[col_idx]
                col_idx += 1
                continue

            try:
                cell = next(cell_iter)
            except StopIteration:
                break

            try:
                rowspan = int(cell.get("rowspan", 1) or 1)
            except (ValueError, TypeError):
                rowspan = 1
            try:
                colspan = int(cell.get("colspan", 1) or 1)
            except (ValueError, TypeError):
                colspan = 1

            text = cell.get_text(separator=" ", strip=True)

            for _ in range(max(1, colspan)):
                row_tags.append(cell)
                row_texts.append(text)
                if rowspan > 1:
                    active_spans[col_idx] = {
                        "remaining": rowspan - 1,
                        "tag": cell,
                        "text": text,
                    }
                col_idx += 1

        while col_idx in active_spans:
            span_info = active_spans[col_idx]
            row_tags.append(span_info["tag"])
            row_texts.append(span_info["text"])
            span_info["remaining"] -= 1
            if span_info["remaining"] <= 0:
                del active_spans[col_idx]
            col_idx += 1

        grid.append((row, row_tags, row_texts))

    return grid


def extract_html_subjects(soup: BeautifulSoup, base_url: str = "", raw_html: str = "") -> list:
    """
    Extrae elementos curriculares de tablas HTML evitando filas de cabecera (<th>),
    filas de resumen de créditos (Totals, 1r curs...), palabras clave no curriculares,
    soportando celdas multi-línea divididas por <br>, <p>, <div> o <li>, y capturando
    el enlace saliente a la guía docente oficial (url_guia_docente).
    """
    elementos = []
    seen_names = set()
    tables = soup.find_all("table")

    for t in tables:
        if not is_valid_curricular_table(t):
            continue

        table_optional = _table_has_optional_context(t)
        table_curso = ""
        table_cuatrimestre = ""
        parent_heading = t.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "caption", "legend", "button", "summary"])
        if parent_heading:
            h_text = parent_heading.get_text()
            if any(ext in h_text.lower() for ext in ["en extinción", "en extincion", "en procés d'extinció", "pla amortitzat", "plan extinguido", "plan histórico"]):
                continue
            c_norm, _ = normalize_curso(h_text)
            if c_norm:
                table_curso = c_norm
            table_cuatrimestre = normalize_cuatrimestre(h_text)

        if not table_curso:
            parent_tab = t.find_parent(["div", "section", "article"], class_=lambda c: c and any(k in str(c).lower() for k in ["tab-pane", "tabcontent", "accordion", "collapse", "panel"]))
            if parent_tab:
                tab_id = parent_tab.get("id") or ""
                tab_aria = parent_tab.get("aria-labelledby") or ""
                tab_trigger = soup.find(["a", "button", "li"], attrs={"href": f"#{tab_id}"}) if tab_id else None
                if not tab_trigger and tab_aria:
                    tab_trigger = soup.find(id=tab_aria)
                if tab_trigger:
                    t_text = tab_trigger.get_text()
                    c_norm, _ = normalize_curso(t_text)
                    if c_norm:
                        table_curso = c_norm
                    if not table_cuatrimestre:
                        table_cuatrimestre = normalize_cuatrimestre(t_text)

        rows = t.find_all("tr")
        subj_col = 0
        subject_cols = [0]
        ects_col = -1
        car_col = -1
        curso_col = -1
        has_split_credit_headers = False

        normalized_grid = normalize_table_rows_with_spans(rows)
        for r_idx, (row, tds, cols_raw) in enumerate(normalized_grid):
            if not tds:
                continue

            # Detectar si la fila define los índices de columnas (fila con <th> o fila 0 con palabras clave de cabecera)
            is_header_row = (
                all(cell.name == "th" for cell in tds)
                or (r_idx == 0 and any(
                    any(w in c_val.lower() for w in ["asignatura", "assignatura", "asineira", "irakasgaia", "materia", "denominaci", "crédito", "credito", "crèdits", "ects"])
                    for c_val in cols_raw
                ))
                # Las tablas con varios cursos repiten la cabecera después de
                # una fila de título y no siempre usan <th>. Dos o más celdas
                # con vocabulario de cabecera son evidencia suficiente para
                # reconocer ese esquema sin depender de su posición.
                or sum(
                    any(w in c_val.lower() for w in [
                        "asignatura", "assignatura", "asineira", "irakasgaia",
                        "materia", "denominaci", "nombre", "subject", "course",
                    ])
                    for c_val in cols_raw
                ) >= 2
            )
            if is_header_row:
                header_low = " ".join(cols_raw).lower()
                if "obligat" in header_low and "optat" in header_low:
                    has_split_credit_headers = True
                subject_cols = []
                for c_i, c_val in enumerate(cols_raw):
                    c_low = c_val.lower().strip()
                    if any(w == c_low or w in c_low for w in ["asignatura", "assignatura", "asineira", "irakasgaia", "materia", "denominació", "denominacion", "denominación", "nombre", "actividad", "subject", "course", "modul", "módulo", "modulo"]):
                        subj_col = c_i
                        if c_i not in subject_cols:
                            subject_cols.append(c_i)
                    elif any(w == c_low or w in c_low for w in ["crédito", "credito", "crèdits", "credits", "credit", "kredituak", "kreditu", "ects"]):
                        ects_col = c_i
                    elif any(w == c_low or w in c_low for w in ["carácter", "caracter", "caràcter", "tipo", "tipus", "mota", "type"]):
                        car_col = c_i
                    elif any(w == c_low or w in c_low for w in ["curso", "curs", "ano", "año", "ikasturtea", "maila", "year", "level"]):
                        curso_col = c_i
                continue

            # Algunos planes distribuyen dos o más asignaturas en paralelo
            # (Asignatura/Tipo/Departamento | Asignatura/Tipo/Departamento).
            # Procesar los grupos completos evita perder sistemáticamente la
            # mitad derecha de estas tablas.
            if len(subject_cols) > 1 and len(tds) >= subject_cols[-1] + 1:
                parallel_items = _extract_parallel_html_row(
                    tds,
                    subject_cols,
                    table_curso,
                    table_cuatrimestre,
                    base_url,
                )
                for item in parallel_items:
                    if table_optional and item.get("caracter") == "OB":
                        item["caracter"] = "OP"
                    norm_name = curriculum_element_key(item.get("nombre_elemento"))
                    if norm_name and norm_name not in seen_names:
                        seen_names.add(norm_name)
                        elementos.append(item)
                continue

            # Las celdas con saltos de línea aparecen también en tablas
            # estructuradas (p. ej. asignatura + docente + ECTS). En una fila
            # con varias columnas esas líneas no son asignaturas separadas y
            # expandirlas aquí descarta la columna de créditos. La expansión
            # solo es segura para una fila realmente monocolumna.
            extracted_any_multiline = False
            if len(tds) == 1:
                multiline_cells = tds
            else:
                multiline_cells = []
            for td in multiline_cells:
                lines = [l.strip() for l in td.get_text(separator="\n").splitlines() if l.strip()]

                if len(lines) >= 2:
                    for line in lines:
                        clean_line = re.sub(r"^[\s\-•*]+\s*", "", line).strip()
                        clean_line = sanitize_subject_name(clean_line)
                        if not clean_line or len(clean_line) < 4 or len(clean_line) > 120:
                            continue
                        clean_low = clean_line.lower()
                        if (
                            _RE_SUMMARY_ROW_MARKERS.match(clean_low)
                            or any(clean_low == hk for hk in HEADER_KEYWORDS)
                            or any(sk in clean_low for sk in INVALID_SUBJECT_KEYWORDS)
                            or clean_line.isdigit()
                        ):
                            continue

                        creditos = None
                        ects_val_num = None
                        m_cr = re.search(r"[/()]\s*(\d+(?:[.,]\d+)?)\s*(?:cr[eè]dits?|cr\.?|ects)", clean_line, re.IGNORECASE)
                        if m_cr:
                            creditos = m_cr.group(1).replace(",", ".")
                            try:
                                ects_val_num = float(creditos)
                            except ValueError:
                                pass

                        caracter = "OB"
                        if "optativ" in clean_low:
                            caracter = "OP"
                        elif any(k in clean_low for k in ["treball de final", "tfg", "tfm", "trabajo fin"]):
                            caracter = "TFG"
                        elif any(k in clean_low for k in ["pràctiques", "practicas", "prácticas"]):
                            caracter = "PE"
                        elif any(k in clean_low for k in ["bàsica", "basica"]):
                            caracter = "FB"
                        elif table_optional:
                            caracter = "OP"

                        if _is_html_metadata_subject(clean_line, ects_val_num, caracter) or is_spurious_or_administrative_subject(clean_line, ects_val=ects_val_num, caracter=caracter):
                            continue

                        norm_name = curriculum_element_key(clean_line)
                        if norm_name in seen_names or len(norm_name) < 4:
                            continue
                        seen_names.add(norm_name)

                        # Extraer enlace si existe
                        url_guia = ""
                        a_tag = td.find("a", href=True)
                        if a_tag:
                            href_val = a_tag["href"].strip()
                            if href_val.startswith("http"):
                                url_guia = href_val
                            elif base_url and not href_val.startswith("javascript:"):
                                url_guia = urllib.parse.urljoin(base_url, href_val)

                        # Extraer código si viene en la celda o URL
                        cod_asig = ""
                        if url_guia:
                            m_cod = re.search(r"[/?=](\d{4,8})(?:[/?&.#]|$)", url_guia)
                            if m_cod:
                                cod_asig = m_cod.group(1)

                        elem_item = {
                            "modulo": "",
                            "materia": "",
                            "codigo_asignatura": cod_asig,
                            "nombre_elemento": clean_line,
                            "creditos_ects": creditos,
                            "caracter": caracter,
                            "curso": table_curso,
                            "cuatrimestre": table_cuatrimestre or "1C",
                            "idioma": detect_academic_language(clean_line)
                        }
                        if url_guia:
                            elem_item["url_guia_docente"] = url_guia

                        elementos.append(elem_item)
                        extracted_any_multiline = True

            if extracted_any_multiline:
                continue

            # Fallback para maquetas paralelas sin cabecera: cada bloque suele
            # ser «asignatura | ECTS» y puede ir precedido por un código. Solo
            # se activa cuando hay al menos dos nombres y cada uno tiene
            # inmediatamente después una carga entre 1 y 30 ECTS.
            if ects_col == -1 and len(tds) >= 4:
                inferred_subject_cols = []
                for cell_index, cell_value in enumerate(cols_raw[:-1]):
                    if cell_value.strip().isdigit() or len(cell_value.strip()) < 4:
                        continue
                    next_value = cols_raw[cell_index + 1].strip().replace(",", ".")
                    if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", next_value):
                        continue
                    try:
                        if 1.0 <= float(next_value) <= 30.0:
                            inferred_subject_cols.append(cell_index)
                    except ValueError:
                        continue
                if len(inferred_subject_cols) >= 2:
                    parallel_items = _extract_parallel_html_row(
                        tds,
                        inferred_subject_cols,
                        table_curso,
                        table_cuatrimestre,
                        base_url,
                    )
                    for item in parallel_items:
                        if table_optional and item.get("caracter") == "OB":
                            item["caracter"] = "OP"
                        norm_name = curriculum_element_key(item.get("nombre_elemento"))
                        if norm_name and norm_name not in seen_names:
                            seen_names.add(norm_name)
                            elementos.append(item)
                    if parallel_items:
                        continue

            # Extracción tabular clásica (1 fila = 1 asignatura con columnas)
            if len(cols_raw) < 2:
                continue

            subject_cell = None
            if subj_col < len(tds) and len(cols_raw[subj_col]) >= 4 and not cols_raw[subj_col].isdigit():
                subject_cell = tds[subj_col]
            elif len(tds) > 1:
                # Algunas tablas declaran «Asignatura» como primera columna,
                # pero anteponen en las filas un identificador numérico o un
                # código. Buscar primero texto académico evita conservar el
                # código o el carácter de la materia como nombre. Se mantiene
                # el fallback geométrico para filas con rowspan.
                character_labels = {
                    "fb", "fba", "básica", "basica", "basic", "ob", "obl",
                    "obligatoria", "obligatorio", "obligatory", "op", "opt",
                    "optativa", "optativo", "elective", "pe", "pex", "tfg", "tfm",
                }
                for candidate_index, candidate_value in enumerate(cols_raw):
                    normalized_candidate = candidate_value.strip().casefold()
                    if candidate_index == ects_col or not normalized_candidate:
                        continue
                    if re.fullmatch(r"(?:\d{3,8}|[A-Z]{2,4}\d{2,6})", normalized_candidate, re.IGNORECASE):
                        continue
                    if normalized_candidate in character_labels:
                        continue
                    if len(normalized_candidate) >= 4 and not normalized_candidate.isdigit():
                        subject_cell = tds[candidate_index]
                        break
                if subject_cell is None:
                    subject_cell = tds[-2]
            elif tds:
                subject_cell = tds[0]
            nombre_candidato = _extract_subject_cell_text(subject_cell)
            if not nombre_candidato:
                if subj_col < len(cols_raw):
                    nombre_candidato = cols_raw[subj_col]
                elif len(cols_raw) > 1:
                    nombre_candidato = cols_raw[-2]
                elif cols_raw:
                    nombre_candidato = cols_raw[0]

            nombre_candidato = sanitize_subject_name(nombre_candidato)
            nombre_lower = nombre_candidato.lower()

            if (
                len(nombre_candidato) < 4
                or _RE_SUMMARY_ROW_MARKERS.match(nombre_lower)
                or any(nombre_lower == hk for hk in HEADER_KEYWORDS)
                or any(sk in nombre_lower for sk in INVALID_SUBJECT_KEYWORDS)
                or len(nombre_candidato) > 150
            ):
                continue

            norm_name = curriculum_element_key(nombre_candidato)
            if norm_name in seen_names:
                continue

            creditos = None
            ects_val_num = None
            split_credit_values = []
            if has_split_credit_headers:
                for col_i, col_value in enumerate(cols_raw):
                    if col_i == subj_col:
                        continue
                    m_split = re.search(r"\b(\d+(?:[.,]\d+)?)\b", col_value)
                    if not m_split:
                        continue
                    try:
                        split_value = float(m_split.group(1).replace(",", "."))
                    except ValueError:
                        continue
                    if 0 <= split_value <= 60:
                        split_credit_values.append(split_value)
                if split_credit_values and sum(split_credit_values) > 0:
                    ects_val_num = round(sum(split_credit_values), 2)
                    creditos = (
                        str(int(ects_val_num))
                        if ects_val_num.is_integer()
                        else str(ects_val_num)
                    )
            if creditos is None and ects_col != -1 and ects_col < len(cols_raw):
                m_c = re.search(r"\b(\d+(?:[.,]\d+)?)\b", cols_raw[ects_col])
                if m_c:
                    raw_c = m_c.group(1).replace(",", ".")
                    try:
                        c_f = float(raw_c)
                        if 1.0 <= c_f <= 30.0:
                            creditos = raw_c
                            ects_val_num = c_f
                    except ValueError:
                        pass
            elif creditos is None:
                for col in cols_raw[1:]:
                    m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", col)
                    if m:
                        val_str = m.group(1).replace(",", ".")
                        try:
                            val_num = float(val_str)
                            if 1.0 <= val_num <= 30.0:
                                creditos = str(int(val_num)) if val_num.is_integer() else str(val_num)
                                ects_val_num = val_num
                                break
                        except ValueError:
                            pass

            caracter = "OB"
            if car_col != -1 and car_col < len(cols_raw):
                caracter = classify_subject_caracter(cols_raw[car_col], default="OB")
            else:
                for col in cols_raw:
                    car = classify_subject_caracter(col, default="")
                    if car:
                        caracter = car
                        break
            if table_optional and caracter == "OB":
                caracter = "OP"

            validation_ects = (
                None
                if has_split_credit_headers and split_credit_values
                else ects_val_num
            )
            if _is_html_metadata_subject(nombre_candidato, ects_val_num, caracter) or is_spurious_or_administrative_subject(
                nombre_candidato,
                ects_val=validation_ects,
                caracter=caracter,
            ):
                continue

            curso = ""
            if curso_col != -1 and curso_col < len(cols_raw):
                c_norm, _ = normalize_curso(cols_raw[curso_col])
                curso = c_norm or cols_raw[curso_col]
            else:
                for col in cols_raw[1:]:
                    col_lower = col.lower()
                    if any(c_kw in col_lower for c_kw in ["1º", "2º", "3º", "4º", "primer", "segundo", "tercer", "cuarto", "1er", "2do", "3er", "4to"]):
                        c_norm, _ = normalize_curso(col)
                        curso = c_norm or col
                        break
            if not curso and table_curso:
                curso = table_curso

            cuatrimestre_val = ""
            for col in cols_raw:
                c_clean = col.lower().strip()
                if any(q in c_clean for q in ["1c", "2c", "1s", "2s", "primer", "segundo", "anual", "q1", "q2", "s1", "s2", "lauhileko"]):
                    cuatrimestre_val = normalize_cuatrimestre(col)
                    break
            if not cuatrimestre_val:
                cuatrimestre_val = table_cuatrimestre or "1C"

            # Extraer enlace saliente a la guía docente si existe en la fila o celda
            url_guia = ""
            a_tag = row.find("a", href=True)
            if a_tag:
                href_val = a_tag["href"].strip()
                if href_val.startswith("http"):
                    url_guia = href_val
                elif base_url and not href_val.startswith("javascript:"):
                    url_guia = urllib.parse.urljoin(base_url, href_val)

            # Extraer código si existe en alguna columna o en la URL
            codigo_asig = ""
            for c_val in cols_raw:
                c_val_strip = c_val.strip()
                if re.match(r"^\d{4,8}$", c_val_strip) or re.match(r"^[A-Z]{2,4}\d{2,6}$", c_val_strip):
                    codigo_asig = c_val_strip
                    break
            if not codigo_asig and url_guia:
                m_cod = re.search(r"[/?=](\d{4,8})(?:[/?&.#]|$)", url_guia)
                if m_cod:
                    codigo_asig = m_cod.group(1)

            seen_names.add(norm_name)
            elem_item = {
                "modulo": "",
                "materia": "",
                "codigo_asignatura": codigo_asig,
                "nombre_elemento": nombre_candidato,
                "creditos_ects": creditos,
                "caracter": caracter,
                "curso": curso,
                "cuatrimestre": cuatrimestre_val,
                "idioma": detect_academic_language(nombre_candidato)
            }
            if url_guia:
                elem_item["url_guia_docente"] = url_guia
            if has_split_credit_headers and split_credit_values:
                elem_item["_creditos_compuestos"] = True

            elementos.append(elem_item)

    def _keep_curriculum_item(item):
        if not isinstance(item, dict):
            return False
        raw_ects = item.get("creditos_ects")
        try:
            ects_value = float(str(raw_ects).replace(",", ".")) if raw_ects not in (None, "") else None
        except (TypeError, ValueError):
            ects_value = None
        return (
            not is_summary_curriculum_name(item.get("nombre_elemento", ""))
            and not is_spurious_or_administrative_subject(
                item.get("nombre_elemento", ""),
                ects_val=None if item.get("_creditos_compuestos") else ects_value,
                caracter=item.get("caracter", "OB"),
            )
        )

    elementos = [item for item in elementos if _keep_curriculum_item(item)]

    # Hay portales que publican la carga común en un párrafo y omiten la
    # columna de créditos en las tablas temporales. Aplicar la declaración
    # explícita antes de construir el payload evita perder esas asignaturas,
    # sin alterar filas que ya tienen ECTS ni excepciones docentes conocidas.
    uniform_ects = _infer_uniform_curricular_ects(soup)
    _fill_explicit_uniform_curricular_ects(elementos, uniform_ects)

    # Muchos catálogos oficiales publican las materias en párrafos, listas o
    # JSON-LD en lugar de una tabla. Sólo se incorpora esa evidencia cuando la
    # página ya ha pasado por la misma comprobación de identidad del llamador.
    structured_elems = extract_structured_curriculum(soup, base_url)
    prose_elems = extract_prose_curriculum(soup, base_url)
    recovered_elems = merge_curriculum_elements(structured_elems, prose_elems)
    hydration_payloads = extract_hydration_payload(soup, raw_html)
    hydration_elems = extract_curriculum_from_json_tree(hydration_payloads, source_url=base_url)
    if hydration_elems:
        recovered_elems = merge_curriculum_elements(recovered_elems, hydration_elems)
    schema_org_elems = extract_schema_org_curriculum(soup, base_url)
    if schema_org_elems:
        recovered_elems = merge_curriculum_elements(recovered_elems, schema_org_elems)
    recovered_elems = [item for item in recovered_elems if _keep_curriculum_item(item)]
    if recovered_elems:
        elementos = merge_curriculum_elements(elementos, recovered_elems)

    if len(elementos) < 3 or not tables:
        card_elems = extract_subjects_from_card_blocks(soup, base_url)
        card_elems = [item for item in card_elems if _keep_curriculum_item(item)]
        def _structure_score(items):
            return sum(
                sum(bool(item.get(field)) for field in (
                    "codigo_asignatura", "creditos_ects", "curso", "cuatrimestre", "caracter"
                ))
                for item in items
                if isinstance(item, dict)
            )

        # En páginas sin tabla, el extractor de prosa puede devolver el mismo
        # número de elementos pero perder la frontera de cada tarjeta y su
        # código. Preferir la representación de tarjetas si aporta una
        # estructura claramente más rica; la cantidad por sí sola no basta.
        if card_elems and (
            len(card_elems) > len(elementos)
            or (not tables and _structure_score(card_elems) > _structure_score(elementos))
        ):
            return infer_missing_courses_in_curriculum(card_elems)

    for item in elementos:
        if isinstance(item, dict):
            item.pop("_creditos_compuestos", None)
    elementos = infer_missing_courses_in_curriculum(elementos)
    return elementos


