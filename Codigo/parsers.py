import os
import re
from datetime import datetime
import xlrd
from bs4 import BeautifulSoup
import pdfplumber
import pypdf

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
                "nombre": name,
                "tipo": tipo,
                "comunidad_autonoma": ccaa,
                "municipio": row_dict.get("Municipio", ""),
                "provincia": row_dict.get("Provincia", ""),
                "web": url,
                "email": row_dict.get("EMail", ""),
                "telefono": row_dict.get("Teléfono 1", row_dict.get("TelÃ©fono 1", ""))
            })
            
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
        
        code = row_dict.get("Código", row_dict.get("CÃ³digo", ""))
        title = row_dict.get("Título", row_dict.get("TÃ­tulo", ""))
        nivel = row_dict.get("Nivel académico", row_dict.get("Nivel acadÃ©mico", ""))
        estado = row_dict.get("Estado", "")
        
        # Filter inactive statuses
        estado_lower = estado.lower()
        is_inactive = any(term in estado_lower for term in ["extinguido", "no vigente", "en extinción", "extincion", "derogado"])
        
        if code and title and not is_inactive:
            raw_active_degrees.append({
                "codigo_estudio": code,
                "titulo": title,
                "nivel_academico": nivel,
                "estado": estado
            })

    # Deduplicate renovated degrees within the same university
    def normalize_title(full_title: str) -> str:
        # Standardize title base without trailing university name
        base = full_title.split(" por la ")[0].split(" por ")[0].strip().lower()
        return re.sub(r"\s+", " ", base)

    def get_rd_rank(nivel_str: str) -> int:
        nivel_lower = nivel_str.lower()
        if "822/2021" in nivel_lower:
            return 4
        elif "1393/2007" in nivel_lower:
            return 3
        elif "56/2005" in nivel_lower:
            return 2
        elif "bolet" in nivel_lower or "b.o.e" in nivel_lower:
            return 1
        return 0

    grouped_degrees = {}
    for deg in raw_active_degrees:
        norm_title = normalize_title(deg["titulo"])
        if norm_title not in grouped_degrees:
            grouped_degrees[norm_title] = deg
        else:
            existing = grouped_degrees[norm_title]
            rank_existing = get_rd_rank(existing["nivel_academico"])
            rank_new = get_rd_rank(deg["nivel_academico"])
            
            # Prefer higher Real Decreto rank (newer decree)
            if rank_new > rank_existing:
                grouped_degrees[norm_title] = deg
            elif rank_new == rank_existing:
                # Prefer higher numeric code (newer registration/renovation ID)
                try:
                    code_existing = int(existing["codigo_estudio"])
                    code_new = int(deg["codigo_estudio"])
                    if code_new > code_existing:
                        grouped_degrees[norm_title] = deg
                except ValueError:
                    pass

    return list(grouped_degrees.values())


def parse_degree_detail_html(html_content: str) -> dict:
    """
    Parses the HTML of the degree detail page to find all BOE PDF links,
    and identifies the MOST RECENT BOE link.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    boe_candidates = []
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        
        if "boe.es" in href.lower() or "boe" in text.lower() or ".pdf" in href.lower():
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
            
            boe_candidates.append({
                "url": href,
                "text": text,
                "date": date_obj
            })
            
    if not boe_candidates:
        return {"latest_boe_url": None, "boe_date": None, "all_boe_links": []}
    
    dated_candidates = [c for c in boe_candidates if c["date"] is not None]
    if dated_candidates:
        latest = max(dated_candidates, key=lambda c: c["date"])
    else:
        latest = boe_candidates[-1]
        
    return {
        "latest_boe_url": latest["url"],
        "boe_date": latest["date"].strftime("%Y-%m-%d") if latest["date"] else None,
        "all_boe_links": [c["url"] for c in boe_candidates]
    }


def parse_boe_pdf(pdf_filepath: str) -> dict:
    """
    Extracts METICULOUS curriculum data (resumen creditos, asignaturas, modulos, materias, 
    unidades formativas, bloques, ECTS, carácter, curso, cuatrimestre) from a BOE PDF file.
    """
    resumen_creditos = {}
    elementos_curriculares = []
    raw_text_parts = []
    
    # Extract plain text with pypdf
    try:
        reader = pypdf.PdfReader(pdf_filepath)
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            raw_text_parts.append(text)
    except Exception as e:
        raw_text_parts.append(f"Error extracting raw text with pypdf: {e}")

    full_text = "\n".join(raw_text_parts)

    # Extract tables with pdfplumber
    try:
        with pdfplumber.open(pdf_filepath) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    
                    header_row = [str(cell).strip().replace("\n", " ") for cell in table[0] if cell]
                    header_text = " ".join(header_row).lower()
                    
                    # Case 1: Credit Distribution Summary Table
                    if any(term in header_text for term in ["carácter", "caracter", "tipo", "créditos", "creditos"]) and len(table[0]) <= 3:
                        for row in table[1:]:
                            if len(row) >= 2 and row[0] and row[1]:
                                key = str(row[0]).strip().replace("\n", " ")
                                val = str(row[1]).strip().replace("\n", " ")
                                if key:
                                    resumen_creditos[key] = val
                    
                    # Case 2: Detailed Curricular Elements (Asignaturas / Módulos / Materias / Bloques)
                    col_map = {}
                    for col_idx, col_name in enumerate(header_row):
                        col_lower = col_name.lower()
                        if "módulo" in col_lower or "modulo" in col_lower:
                            col_map["modulo"] = col_idx
                        elif "materia" in col_lower:
                            col_map["materia"] = col_idx
                        elif any(k in col_lower for k in ["asignatura", "enseñanza", "unidad", "bloque", "denominación", "denominacion"]):
                            col_map["asignatura"] = col_idx
                        elif "crédito" in col_lower or "ects" in col_lower:
                            col_map["creditos"] = col_idx
                        elif "carácter" in col_lower or "caracter" in col_lower or "tipo" in col_lower:
                            col_map["caracter"] = col_idx
                        elif "curso" in col_lower or "año" in col_lower:
                            col_map["curso"] = col_idx
                        elif any(k in col_lower for k in ["cuatrimestre", "semestre", "periodo"]):
                            col_map["cuatrimestre"] = col_idx

                    # If table contains subject or module or credit information
                    if "asignatura" in col_map or "modulo" in col_map or "materia" in col_map or ("creditos" in col_map and "caracter" in col_map):
                        last_modulo = ""
                        last_materia = ""
                        for row in table[1:]:
                            if not row or all(c is None for c in row):
                                continue
                            
                            def get_cell(idx_key):
                                c_idx = col_map.get(idx_key)
                                if c_idx is not None and c_idx < len(row) and row[c_idx]:
                                    return str(row[c_idx]).strip().replace("\n", " ")
                                return ""
                            
                            mod_val = get_cell("modulo")
                            if mod_val:
                                last_modulo = mod_val
                            else:
                                mod_val = last_modulo

                            mat_val = get_cell("materia")
                            if mat_val:
                                last_materia = mat_val
                            else:
                                mat_val = last_materia
                                
                            asig_val = get_cell("asignatura")
                            cred_val = get_cell("creditos")
                            carac_val = get_cell("caracter")
                            curso_val = get_cell("curso")
                            cuatri_val = get_cell("cuatrimestre")
                            
                            # Standardize element name (Asignatura or Module or Row text if nameless)
                            elem_name = asig_val or mat_val or mod_val
                            if elem_name and elem_name.lower() not in ["total", "subtotal", "suma"]:
                                elementos_curriculares.append({
                                    "modulo": mod_val,
                                    "materia": mat_val,
                                    "nombre_elemento": elem_name,
                                    "creditos_ects": cred_val,
                                    "caracter": carac_val,
                                    "curso": curso_val,
                                    "cuatrimestre": cuatri_val
                                })
    except Exception as e:
        pass
        
    return {
        "resumen_creditos": resumen_creditos,
        "elementos_curriculares": elementos_curriculares,
        "total_elementos": len(elementos_curriculares),
        "texto_extraido_muestra": full_text[:1000]
    }
