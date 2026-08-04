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
        
        code = row_dict.get("Código") or row_dict.get("CÃ³digo") or ""
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
        
        # Helper para normalización estricta de acentos y distorsiones de codificación UTF-8
        def normalize_text(text: str) -> str:
            if not text:
                return ""
            t = text.lower().strip()
            # Eliminar distorsiones de doble codificación UTF-8 / ISO-8859-1
            t = t.replace("Ã³", "o").replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i").replace("Ãº", "u").replace("Ã±", "n")
            # Normalizar tildes y diéresis estándar
            t = t.replace("ó", "o").replace("á", "a").replace("é", "e").replace("í", "i").replace("ú", "u").replace("ñ", "n")
            t = t.replace("ö", "o").replace("ä", "a").replace("ë", "e").replace("ï", "i").replace("ü", "u")
            return t

        estado_norm = normalize_text(estado)

        # 1. LISTA NEGRA AMPLIADA (Términos que denotan inactividad, extinción o desestimación)
        blacklist = [
            "extinguid", "extincion", "extinta", "extinto",
            "no vigente", "sin docencia", "baja",
            "derogad", "cancelad", "eliminad", "revocad",
            "suspendid", "caducad", "desestimad", "sustituid",
            "no impartid", "sin efecto", "cierre", "cerrad", "archivo"
        ]
        has_blacklist = any(term in estado_norm for term in blacklist)

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
        has_whitelist = any(term in estado_norm for term in whitelist)

        # La titulación debe pertenecer a la Lista Blanca Y NO contener ningún término de la Lista Negra
        if code and title and has_whitelist and not has_blacklist:
            raw_active_degrees.append({
                "codigo_estudio": code,
                "titulo": title,
                "nivel_academico": nivel,
                "estado": estado
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


def parse_degree_detail_html(html_content: str) -> dict:
    """
    Parses the HTML of the degree detail page to find all BOE PDF links,
    and returns all candidate links sorted by date (newest first).
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
            
            if href.startswith("/"):
                href = "https://www.boe.es" + href
                
            boe_candidates.append({
                "url": href,
                "text": text,
                "date": date_obj,
                "boe_date": date_obj.strftime("%Y-%m-%d") if date_obj else None
            })
            
    if not boe_candidates:
        return {"latest_boe_url": None, "boe_date": None, "all_boe_links": [], "all_boe_candidates": []}
    
    sorted_candidates = sorted(
        boe_candidates,
        key=lambda c: c["date"] if c["date"] is not None else datetime(1970, 1, 1),
        reverse=True
    )
    
    latest = sorted_candidates[0]
        
    return {
        "latest_boe_url": latest["url"],
        "boe_date": latest["boe_date"],
        "all_boe_links": [c["url"] for c in sorted_candidates],
        "all_boe_candidates": sorted_candidates
    }


def parse_boe_pdf(pdf_filepath: str) -> dict:
    """
    Extracts METICULOUS curriculum data (resumen creditos, asignaturas, modulos, materias, 
    unidades formativas, bloques, ECTS, carácter, curso, cuatrimestre) from a BOE PDF file.
    """
    resumen_creditos = {}
    elementos_curriculares = []
    raw_text_parts = []

    try:
        reader = pypdf.PdfReader(pdf_filepath)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                raw_text_parts.append(text)
    except Exception as e:
        print(f"   [AVISO] error pypdf: {e}")

    full_text = "\n".join(raw_text_parts)

    # 1. Parse Credit Summary Table
    credit_keywords = [
        ("Formación Básica", r"(?:formaci[oó]n b[aá]sica|fb)\s*[:\.\-]?\s*(\d+)"),
        ("Obligatorias", r"(?:obligatoria[s]?|ob)\s*[:\.\-]?\s*(\d+)"),
        ("Optativas", r"(?:optativa[s]?|op)\s*[:\.\-]?\s*(\d+)"),
        ("Prácticas Externas", r"(?:pr[aá]ctica[s]?|pe)\s*[:\.\-]?\s*(\d+)"),
        ("Trabajo Fin de Grado / Máster", r"(?:trabajo fin de|tfg|tfm)\s*[:\.\-]?\s*(\d+)"),
        ("Créditos Totales", r"(?:total|cr[eé]ditos totales)\s*[:\.\-]?\s*(\d+)")
    ]

    for label, regex in credit_keywords:
        match = re.search(regex, full_text, re.IGNORECASE)
        if match:
            resumen_creditos[label] = match.group(1)

    # 2. Extract Structured Curriculum Tables with pdfplumber
    try:
        with pdfplumber.open(pdf_filepath) as pdf:
            current_modulo = ""
            current_materia = ""

            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                            continue
                        
                        clean_row = [re.sub(r"\s+", " ", str(cell).strip()) if cell else "" for cell in row]
                        row_str = " ".join(clean_row).lower()

                        if "módulo" in row_str or "modulo" in row_str:
                            current_modulo = clean_row[0] if clean_row else ""
                            continue
                        if "materia" in row_str:
                            current_materia = clean_row[0] if clean_row else ""
                            continue

                        # Check for subject row containing ECTS credit numbers
                        ects_match = None
                        caracter = "OB"
                        curso = ""
                        cuatrimestre = ""

                        for cell in clean_row:
                            if not ects_match:
                                m = re.search(r"\b(\d+(?:[\.,]\d+)?)\b", cell)
                                if m and float(m.group(1).replace(",", ".")) in [3, 4.5, 6, 9, 12, 15, 18, 24, 30]:
                                    ects_match = m.group(1)

                            cell_lower = cell.lower()
                            if "básica" in cell_lower or "basica" in cell_lower or "fb" in cell_lower:
                                caracter = "FB"
                            elif "optativa" in cell_lower or "op" in cell_lower:
                                caracter = "OP"
                            elif "práctica" in cell_lower or "pe" in cell_lower:
                                caracter = "PE"
                            elif "tfg" in cell_lower or "tfm" in cell_lower or "trabajo fin" in cell_lower:
                                caracter = "TFG/TFM"

                            if re.search(r"\b[1-6][ºº°]?\b", cell):
                                curso = cell
                            if "cuatrimestre" in cell_lower or "semestre" in cell_lower:
                                cuatrimestre = cell

                        if clean_row and len(clean_row[0]) > 3 and not any(k in clean_row[0].lower() for k in ["asignatura", "carácter", "créditos", "curso"]):
                            elementos_curriculares.append({
                                "modulo": current_modulo,
                                "materia": current_materia,
                                "nombre_elemento": clean_row[0],
                                "creditos_ects": ects_match or "6",
                                "caracter": caracter,
                                "curso": curso,
                                "cuatrimestre": cuatrimestre
                            })
    except Exception as e:
        print(f"   [AVISO] pdfplumber table extraction fallback: {e}")

    return {
        "resumen_creditos": resumen_creditos,
        "total_elementos": len(elementos_curriculares),
        "elementos_curriculares": elementos_curriculares
    }
