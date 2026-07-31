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
    
    # Read headers from row 0
    headers = [str(cell).strip() for cell in sheet.row_values(0)]
    universities = []
    
    for r in range(1, sheet.nrows):
        row = sheet.row_values(r)
        row_dict = {}
        for idx, header in enumerate(headers):
            val = str(row[idx]).strip() if idx < len(row) else ""
            # Fix floating point code formatting if xlrd parsed code as float (e.g., 89.0 -> 089)
            if header in ["Código", "CÃ³digo"] and val.endswith(".0"):
                val = val[:-2].zfill(3)
            row_dict[header] = val
        
        # Standardized dictionary keys
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
    FILTERS OUT INACTIVE / EXTINGUISHED DEGREES.
    Only returns degrees that are active/vigente (e.g. 'Publicado en B.O.E.').
    """
    wb = xlrd.open_workbook(filepath)
    sheet = wb.sheet_by_index(0)
    
    if sheet.nrows == 0:
        return []
    
    headers = [str(cell).strip() for cell in sheet.row_values(0)]
    active_degrees = []
    
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
        
        # Check active status requirement:
        # Non-active states include 'Extinguido', 'No vigente', 'En extinción', 'Derogado'.
        # Active state in RUCT is primarily 'Publicado en B.O.E.'.
        estado_lower = estado.lower()
        is_inactive = any(term in estado_lower for term in ["extinguido", "no vigente", "en extinción", "extincion", "derogado"])
        
        if code and title and not is_inactive:
            active_degrees.append({
                "codigo_estudio": code,
                "titulo": title,
                "nivel_academico": nivel,
                "estado": estado
            })
            
    return active_degrees


def parse_degree_detail_html(html_content: str) -> dict:
    """
    Parses the HTML of the degree detail page to find all BOE PDF links,
    and identifies the MOST RECENT BOE link.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    boe_candidates = []
    
    # Search all anchors
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        
        # Check if link points to BOE
        if "boe.es" in href.lower() or "boe" in text.lower() or ".pdf" in href.lower():
            # Try to extract date from link text (e.g. BOE 16/01/2025)
            date_obj = None
            text_date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
            if text_date_match:
                d, m, y = text_date_match.groups()
                try:
                    date_obj = datetime(int(y), int(m), int(d))
                except ValueError:
                    pass
            
            # Try to extract date from URL path (e.g. /boe/dias/2025/01/16/...)
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
    
    # Sort candidates by extracted date (descending)
    dated_candidates = [c for c in boe_candidates if c["date"] is not None]
    if dated_candidates:
        latest = max(dated_candidates, key=lambda c: c["date"])
    else:
        # Fallback to the last candidate link if no dates could be parsed
        latest = boe_candidates[-1]
        
    return {
        "latest_boe_url": latest["url"],
        "boe_date": latest["date"].strftime("%Y-%m-%d") if latest["date"] else None,
        "all_boe_links": [c["url"] for c in boe_candidates]
    }


def parse_boe_pdf(pdf_filepath: str) -> dict:
    """
    Extracts structured curriculum data (credit summaries, courses, subjects, ECTS, types)
    from a BOE PDF file using pdfplumber and pypdf.
    """
    resumen_creditos = {}
    asignaturas = []
    raw_text_parts = []
    
    # Extract plain text using pypdf
    try:
        reader = pypdf.PdfReader(pdf_filepath)
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            raw_text_parts.append(text)
    except Exception as e:
        raw_text_parts.append(f"Error extracting raw text with pypdf: {e}")

    full_text = "\n".join(raw_text_parts)

    # Extract tables using pdfplumber
    try:
        with pdfplumber.open(pdf_filepath) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    
                    # Inspect header row to categorize table type
                    header_row = [str(cell).strip().replace("\n", " ") for cell in table[0] if cell]
                    header_text = " ".join(header_row).lower()
                    
                    # Case 1: Credit Distribution Summary Table
                    if "carácter" in header_text or "tipo" in header_text or "créditos" in header_text and len(table[0]) <= 3:
                        for row in table[1:]:
                            if len(row) >= 2 and row[0] and row[1]:
                                key = str(row[0]).strip().replace("\n", " ")
                                val = str(row[1]).strip().replace("\n", " ")
                                resumen_creditos[key] = val
                    
                    # Case 2: Subjects Breakdown Table
                    # Common headers: ['Materia', 'Asignatura', 'Créditos ECTS', 'Carácter', 'Curso', 'Cuatrimestre']
                    if "asignatura" in header_text or "materia" in header_text:
                        # Find column indices dynamically
                        col_map = {}
                        for col_idx, col_name in enumerate(header_row):
                            col_name_lower = col_name.lower()
                            if "materia" in col_name_lower:
                                col_map["materia"] = col_idx
                            elif "asignatura" in col_name_lower:
                                col_map["asignatura"] = col_idx
                            elif "crédito" in col_name_lower or "ects" in col_name_lower:
                                col_map["creditos"] = col_idx
                            elif "carácter" in col_name_lower or "tipo" in col_name_lower:
                                col_map["caracter"] = col_idx
                            elif "curso" in col_name_lower:
                                col_map["curso"] = col_idx
                            elif "cuatrimestre" in col_name_lower or "periodo" in col_name_lower:
                                col_map["cuatrimestre"] = col_idx
                                
                        last_materia = ""
                        for row in table[1:]:
                            if not row or all(c is None for c in row):
                                continue
                            
                            # Safely extract cells
                            def get_cell(idx_key):
                                col_idx = col_map.get(idx_key)
                                if col_idx is not None and col_idx < len(row) and row[col_idx]:
                                    return str(row[col_idx]).strip().replace("\n", " ")
                                return ""
                            
                            materia_val = get_cell("materia")
                            if materia_val:
                                last_materia = materia_val
                            else:
                                materia_val = last_materia
                                
                            asignatura_val = get_cell("asignatura")
                            creditos_val = get_cell("creditos")
                            caracter_val = get_cell("caracter")
                            curso_val = get_cell("curso")
                            cuatrimestre_val = get_cell("cuatrimestre")
                            
                            if asignatura_val:
                                asignaturas.append({
                                    "materia": materia_val,
                                    "nombre_asignatura": asignatura_val,
                                    "creditos_ects": creditos_val,
                                    "caracter": caracter_val,
                                    "curso": curso_val,
                                    "cuatrimestre": cuatrimestre_val
                                })
    except Exception as e:
        pass
        
    return {
        "resumen_creditos": resumen_creditos,
        "asignaturas": asignaturas,
        "total_asignaturas": len(asignaturas),
        "texto_extraido_muestra": full_text[:1000]
    }
