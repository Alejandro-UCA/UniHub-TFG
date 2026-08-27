import re
import unicodedata
from datetime import datetime
from bs4 import BeautifulSoup
import xlrd

from sanitizers import sanitize_string_value
from downloader import normalize_url


def clean_excel_code(val, zfill_len: int = 0) -> str:
    """Limpia códigos numéricos o alfanuméricos de celdas XLS."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"[^\w]", "", s)
    if zfill_len > 0 and s.isdigit():
        return s.zfill(zfill_len)
    return s


def parse_universities_from_html(html_text: str) -> list[dict]:
    """Fallback para universidades cuando el RUCT responde con tabla HTML en lugar de XLS."""
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


def parse_universities_xls(filepath: str) -> list[dict]:
    """
    Parsea el archivo XLS de universidades descargado de RUCT.
    Devuelve la lista estructurada con orden prioritario (Públicas primero, Privadas después).
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

    # Ordenación prioritaria: Públicas primero, Privadas después
    def get_univ_priority(u):
        tipo_lower = u.get("tipo", "").lower()
        if "pública" in tipo_lower or "publica" in tipo_lower:
            return 0
        return 1

    universities.sort(key=get_univ_priority)
    return universities


def parse_degrees_from_html(html_text: str) -> list[dict]:
    """Fallback para catálogo de titulaciones cuando RUCT responde con HTML."""
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


def normalize_lifecycle_text(text: str) -> str:
    """Normaliza un estado RUCT para clasificar su vigencia sin perder el original."""
    if not text:
        return ""
    value = str(text).lower().strip()
    value = value.replace("Ã³", "o").replace("Ã¡", "a").replace("Ã©", "e")
    value = value.replace("Ã­", "i").replace("Ãº", "u").replace("Ã±", "n")
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def classify_degree_lifecycle(status_text: str) -> str:
    """Clasifica el ciclo de vida de una titulación sin confundir extinción y vigencia.

    ``vigente_no_matriculable`` identifica títulos aún existentes que no
    admiten nueva matrícula por estar en transición de extinción. Deben seguir
    obteniendo su plan: solo se excluyen las titulaciones definitivamente
    obsoletas o extinguidas.
    """
    state = normalize_lifecycle_text(status_text)
    definitively_obsolete = (
        "extinguida", "extinguido", "extinta", "extinto", "baja definitiva",
        "derogada", "derogado", "cancelada", "cancelado", "eliminada", "eliminado",
        "revocada", "revocado", "sin efecto", "caducada", "caducado",
        "desestimada", "desestimado", "archivo definitivo",
    )
    not_enrollable_but_current = (
        "en extincion", "proceso de extincion", "sin docencia", "no matriculable",
        "no se oferta", "no impartida", "no impartido", "no se imparte",
    )
    if any(marker in state for marker in definitively_obsolete):
        return "obsoleta"
    if any(marker in state for marker in not_enrollable_but_current):
        return "vigente_no_matriculable"
    return "vigente_matriculable"


def parse_degrees_xls(filepath: str) -> list[dict]:
    """
    Parsea el archivo XLS de titulaciones de una universidad específica.
    - Filtra titulaciones inactivas o extinguidas.
    - Deduplica renovaciones dentro de la misma institución.
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

    blacklist = [
        "extinguid", "extinta", "extinto", "no vigente", "baja definitiva",
        "derogad", "cancelad", "eliminad", "revocad",
        "suspendid", "caducad", "desestimad", "sustituid", "sin efecto",
        "archivo definitivo"
    ]

    whitelist = [
        "vigente", "impartiendose", "autorizad", "renovad",
        "acreditad", "alta", "publicad", "b.o.e", "boe", "inscrit"
    ]

    legacy_levels = ["solo segundo ciclo", "ciclo corto", "ciclo largo", "primer ciclo", "primer y segundo ciclo", "pre-bolonia", "rd 56/2005"]
    legacy_title_prefixes = ["licenciado", "licenciada", "diplomado", "diplomada", "ingeniero tecnico", "ingeniera tecnica", "arquitecto tecnico", "arquitecta tecnica"]

    for row_data in candidate_rows:
        code = row_data["code"]
        title = row_data["title"]
        nivel = row_data["nivel"]
        estado = row_data["estado"]

        estado_norm = normalize_lifecycle_text(estado)
        nivel_norm = normalize_lifecycle_text(nivel)
        title_norm = normalize_lifecycle_text(title)

        has_blacklist = any(term in estado_norm for term in blacklist)
        has_whitelist = any(term in estado_norm for term in whitelist)
        is_legacy_level = any(leg in nivel_norm for leg in legacy_levels)
        is_legacy_title = any(title_norm.startswith(prefix) for prefix in legacy_title_prefixes)

        lifecycle = classify_degree_lifecycle(estado)
        if (
            code and title and has_whitelist and not has_blacklist
            and lifecycle != "obsoleta" and not is_legacy_level and not is_legacy_title
        ):
            raw_active_degrees.append({
                "codigo_estudio": code.strip(),
                "titulo": sanitize_string_value(title),
                "nivel_academico": sanitize_string_value(nivel),
                "estado": sanitize_string_value(estado),
                "situacion_matriculacion": lifecycle,
            })

    # Deduplicación precisa:
    # 1. Deduplicar primero por codigo_estudio único oficial del RUCT (unifica múltiples sedes/facultades del mismo grado).
    by_code = {}
    for deg in raw_active_degrees:
        c_code = deg.get("codigo_estudio", "").strip()
        if not c_code:
            continue
        if c_code not in by_code:
            by_code[c_code] = deg
        else:
            if deg.get("situacion_matriculacion") == "activa" and by_code[c_code].get("situacion_matriculacion") != "activa":
                by_code[c_code] = deg

    # 2. Deduplicar únicamente si el título completo normalizado y el nivel son exactamente idénticos
    #    (renovaciones de plan con el mismo nombre). NO truncar por 'por la' para preservar títulos interuniversitarios.
    grouped_degrees = {}
    for deg in by_code.values():
        full_title_norm = normalize_lifecycle_text(deg.get("titulo", ""))
        level_norm = normalize_lifecycle_text(deg.get("nivel_academico", ""))
        dedup_key = f"{full_title_norm}|{level_norm}" if level_norm else full_title_norm

        if dedup_key not in grouped_degrees:
            grouped_degrees[dedup_key] = deg
        else:
            existing_deg = grouped_degrees[dedup_key]
            try:
                code_new = int(deg["codigo_estudio"])
                code_existing = int(existing_deg["codigo_estudio"])
                if code_new > code_existing:
                    grouped_degrees[dedup_key] = deg
            except ValueError:
                pass

    return list(grouped_degrees.values())


def extract_link_context_priority(a_tag) -> tuple[int, str]:
    """Determina la prioridad semántica de un enlace BOE en la ficha del RUCT."""
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

    if (
        "correcci" in legend_text or "modificaci" in legend_text or 
        "correcci" in th_text or "modificaci" in th_text or 
        "correcciones" in th_text or "corrección plan estudio" in combined_context or "correccion plan estudio" in combined_context
    ):
        return 100, "plan_correccion"

    if (
        "publicación plan estudios" in prev_text or "publicacion plan estudios" in prev_text or
        "plan de estudios" in prev_text or "plan estudios" in prev_text or
        "publicación plan estudios" in combined_context or "publicacion plan estudios" in combined_context
    ) and "consejo de ministros" not in prev_text:
        return 90, "plan_inicial"

    if "consejo de ministros" in prev_text or "acuerdo de consejo de ministros" in combined_context:
        return 10, "acuerdo_consejo_ministros"

    if any(k in combined_context for k in ["autorización ccaa", "autorizacion ccaa", "extinción", "extincion", "renovación acreditación", "renovacion acreditacion"]):
        return 0, "tramite_autonomico_extincion"

    return 30, "boe_general"


def parse_degree_detail_html(html_content: str) -> dict:
    """Extrae enlaces oficiales del BOE y estado en vivo desde la ficha web de la titulación en RUCT."""
    soup = BeautifulSoup(html_content, "html.parser")
    full_text_lower = soup.get_text().lower()

    status_text = ""
    for tr in soup.find_all("tr"):
        th = tr.find(["th", "td"])
        if th and any(k in th.get_text().lower() for k in ["estado", "situación", "situacion", "vigencia"]):
            tds = tr.find_all("td")
            if tds:
                status_text = tds[-1].get_text(strip=True)
                break

    lifecycle = classify_degree_lifecycle(status_text)
    # La ficha puede mencionar documentos históricos de extinción sin que la
    # titulación esté extinguida. Solo una marca inequívoca de estado en la
    # página completa permite descartarla si no pudimos extraer la celda.
    definitive_status_phrases = (
        "titulacion extinguida", "titulacion extinta", "estado: extinguida",
        "estado: extinta", "situacion: extinguida", "situacion: extinta",
    )
    normalized_full_text = normalize_lifecycle_text(full_text_lower)
    is_extinct = lifecycle == "obsoleta" or any(
        marker in normalized_full_text for marker in definitive_status_phrases
    )

    if is_extinct:
        return {
            "is_extinct": True,
            "status_text": status_text or "Extinguida",
            "lifecycle": "obsoleta",
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
            
            if date_obj and date_obj < datetime(2009, 1, 1):
                continue

            if href.startswith("/"):
                href = "https://www.boe.es" + href

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
        return {
            "is_extinct": False,
            "status_text": status_text,
            "lifecycle": lifecycle,
            "latest_boe_url": None,
            "boe_date": None,
            "all_boe_links": [],
            "all_boe_candidates": [],
        }
    
    sorted_candidates = sorted(
        boe_candidates,
        key=lambda c: (c.get("priority", 0), c["date"] if c["date"] is not None else datetime(1970, 1, 1)),
        reverse=True
    )
    
    latest = sorted_candidates[0]
        
    return {
        "is_extinct": False,
        "status_text": status_text,
        "lifecycle": lifecycle,
        "latest_boe_url": latest["url"],
        "boe_date": latest["boe_date"],
        "all_boe_links": [c["url"] for c in sorted_candidates],
        "all_boe_candidates": sorted_candidates
    }
