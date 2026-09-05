import os
import sys
import re
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from core.downloader import RUCTDownloader
from utils.sanitizers import sanitize_string_value


RE_LINEAS_HEADER = re.compile(
    r"\b(?:l[íi]neas?\s+de\s+investigaci[óo]n|l[íi]nies?\s+de\s+recerca|ikerketa[- ]lerroak|li[ñn]as?\s+de\s+investigaci[óo]n|research\s+lines)\b",
    re.I,
)

RE_ACTIVIDADES_HEADER = re.compile(
    r"\b(?:actividades?\s+formativas?|activitats?\s+formatives?|prestakuntza[- ]jarduerak|training\s+activities)\b",
    re.I,
)

RE_ESCUELA_PATTERNS = re.compile(
    r"(?:escuela\s+(?:internacional\s+)?de\s+doctorado|escuela\s+internacional\s+de\s+posgrado|escola\s+de\s+doctorat|doktoretza\s+eskola|doctoral\s+school)[^<\n,.]*",
    re.I,
)

SUBPAGE_LINEAS_KW = re.compile(
    r"(?:l[íi]neas?\s+de\s+investigaci[óo]n|l[íi]nies?\s+de\s+recerca|equipos?\s+y\s+l[íi]neas|lineas-de-investigacion|equipos-y-lineas)",
    re.I,
)

DISQUALIFIERS = {
    "informe", "verificación", "modificación", "matrícula", "admisión", "documentación",
    "precios", "automatrícula", "contacto", "organización", "normativa", "inicio",
    "contingut", "calendario", "requisitos", "presentación", "tasas", "quejas",
    "sugerencias", "mapa del sitio", "accesibilidad", "responsables", "investigadores",
    "profesorado", "proyectos de investigación", "producción científica", "directors/es",
    "la direcció", "tutoria", "comissió", "comisiones", "equipos de investigación",
    "líneas de investigación", "personal de investigación", "criterios de selección",
    "deva", "memoria", "seguimiento", "calidad", "infraestructura", "dotación",
    "acreditación", "comisión", "alumnos", "tesis dirigidas", "indicadores", "dr."
}


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def is_valid_line_candidate(t: str) -> bool:
    if not (4 < len(t) < 110):
        return False
    t_low = t.lower()
    if any(k in t_low for k in DISQUALIFIERS):
        return False
    if "@" in t_low or "http://" in t_low or "https://" in t_low:
        return False
    if re.match(r"^(?:prof|dra?|don|dña)\.?\s+", t_low):
        return False
    return True


def extract_lines_from_soup(soup: BeautifulSoup, base_url: str) -> list:
    """Extrae líneas de investigación desde una sopa HTML de forma universal."""
    lines = []
    seen = set()

    headers = [
        el for el in soup.find_all(["h1", "h2", "h3", "h4", "h5"])
        if RE_LINEAS_HEADER.search(el.get_text(strip=True)) and len(el.get_text(strip=True)) < 90
    ]

    for h in headers:
        # Patrón 1: Lista HTML (ul, ol) adyacente o siguiente
        next_list = h.find_next(["ol", "ul"])
        if next_list:
            items = []
            for li in next_list.find_all("li", recursive=False):
                t = clean_text(li.get_text(separator=" ", strip=True))
                if is_valid_line_candidate(t) and t.lower() not in seen:
                    seen.add(t.lower())
                    items.append(t)
            if len(items) >= 2:
                return items

        # Patrón 2: Sub-encabezados de sección (h4/h5 en UAB bajo h2)
        section_parent = h.find_parent(["section", "article", "div"])
        if section_parent:
            sub_headers = section_parent.find_all(["h4", "h5"])
            if not sub_headers:
                sub_headers = section_parent.find_all("h3")
            sh_items = []
            for sh in sub_headers:
                t = clean_text(sh.get_text(strip=True))
                if is_valid_line_candidate(t) and t.lower() not in seen:
                    seen.add(t.lower())
                    sh_items.append(t)
            if len(sh_items) >= 2:
                return sh_items

        # Patrón 3: Tablas estructuradas (múltiples tablas o filas, UGR / UCA)
        tables = h.find_all_next("table")
        if tables:
            tb_items = []
            for table in tables:
                for tr in table.find_all("tr"):
                    for td in tr.find_all("td"):
                        styled_items = td.find_all(["span", "strong", "b", "h4", "h5"])
                        found_styled = False
                        for st in styled_items:
                            style = st.get("style", "")
                            t = clean_text(st.get_text(strip=True))
                            if ("16pt" in style or "14pt" in style or "font-size" in style or st.name in ["strong", "b"]):
                                if is_valid_line_candidate(t) and t.lower() not in seen:
                                    seen.add(t.lower())
                                    tb_items.append(t)
                                    found_styled = True
                        if not found_styled:
                            for a in td.find_all("a"):
                                t = clean_text(a.get_text(strip=True))
                                if is_valid_line_candidate(t) and t.lower() not in seen:
                                    seen.add(t.lower())
                                    tb_items.append(t)
            if len(tb_items) >= 2:
                return tb_items

    return lines


def extract_activities_from_soup(soup: BeautifulSoup) -> list:
    """Extrae actividades formativas universales."""
    actividades = []
    header_act = soup.find(lambda e: e.name in ["h1", "h2", "h3", "h4", "h5", "strong"] and RE_ACTIVIDADES_HEADER.search(e.get_text(strip=True)))
    if header_act:
        act_list = header_act.find_next(["ul", "ol"])
        if act_list:
            for li in act_list.find_all("li"):
                t = clean_text(li.get_text(separator=" ", strip=True))
                if 5 < len(t) < 150 and not any(k in t.lower() for k in ["requisitos", "calendario"]):
                    actividades.append(t)
    return actividades


def extract_school_name(soup: BeautifulSoup) -> str:
    """Extrae y sanitiza el nombre oficial de la Escuela de Doctorado."""
    m_esc = RE_ESCUELA_PATTERNS.search(soup.get_text())
    if m_esc:
        cand = clean_text(m_esc.group(0))
        cand = re.sub(r"(?:PWNED|de la\s+de\s+|Mapa del sitio|Accesibilidad).*", "", cand, flags=re.I).strip()
        cand = cand.rstrip(" \t\n\r·-–—/")
        if len(cand) > 10:
            return cand
    return "Escuela Internacional de Posgrado / Doctorado"


def extract_generic_doctoral_program(start_url: str, downloader: RUCTDownloader) -> dict:
    """Orquestador genérico con navegación inteligente a subpáginas canónicas oficiales."""
    html = downloader.fetch_text(start_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    escuela = extract_school_name(soup)
    actividades = extract_activities_from_soup(soup)

    parsed_start = urllib.parse.urlparse(start_url)
    subpage_candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        # Ignorar archivos binarios o descargas directas de PDFs
        if href.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")) or "/wp-content/uploads/" in href.lower():
            continue
        if SUBPAGE_LINEAS_KW.search(text) or SUBPAGE_LINEAS_KW.search(href):
            full_sub = urllib.parse.urljoin(start_url, href)
            p_sub = urllib.parse.urlparse(full_sub)
            if p_sub.netloc == parsed_start.netloc and full_sub.split("#")[0] != start_url.split("#")[0]:
                if full_sub not in subpage_candidates:
                    if any(k in full_sub.lower() for k in ["lineas-de-investigacion", "equipos-y-lineas"]):
                        subpage_candidates.insert(0, full_sub)
                    else:
                        subpage_candidates.append(full_sub)

    lines = []
    final_url = start_url

    # Si hay una subpágina canónica especializada, probarla primero
    if subpage_candidates and any(k in subpage_candidates[0].lower() for k in ["lineas-de-investigacion", "equipos-y-lineas"]):
        target_sub = subpage_candidates[0]
        try:
            sub_html = downloader.fetch_text(target_sub)
            if sub_html:
                soup_sub = BeautifulSoup(sub_html, "html.parser")
                sub_lines = extract_lines_from_soup(soup_sub, target_sub)
                if len(sub_lines) >= 2:
                    lines = sub_lines
                    final_url = target_sub
                    if not actividades:
                        actividades = extract_activities_from_soup(soup_sub)
        except Exception:
            pass

    # Si no se resolvió con la subpágina canónica, intentar página inicial
    if len(lines) < 2:
        lines = extract_lines_from_soup(soup, start_url)
        final_url = start_url

    # Si aún no, intentar el resto de subpáginas candidatas
    if len(lines) < 2:
        for sub_url in subpage_candidates[1:4]:
            try:
                sub_html = downloader.fetch_text(sub_url)
                if not sub_html:
                    continue
                soup_sub = BeautifulSoup(sub_html, "html.parser")
                sub_lines = extract_lines_from_soup(soup_sub, sub_url)
                if len(sub_lines) >= 2:
                    lines = sub_lines
                    final_url = sub_url
                    if not actividades:
                        actividades = extract_activities_from_soup(soup_sub)
                    break
            except Exception:
                pass

    return {
        "regulacion": "RD 99/2011",
        "tipo_programa": "investigacion_doctoral",
        "escuela_doctorado": escuela,
        "url_fuente": final_url,
        "lineas_investigacion": lines,
        "actividades_formativas": actividades,
        "total_lineas": len(lines),
        "total_actividades": len(actividades),
    }


def main():
    print("=== BANCO DE PRUEBAS EXPERIMENTAL AVANZADO: EXTRACCIÓN DE DOCTORADOS ===")
    dl = RUCTDownloader()

    test_targets = [
        {
            "univ": "Universidad de Granada",
            "programa": "Doctorado en Farmacia",
            "url": "https://doctorados.ugr.es/farmacia/pages/ficha",
        },
        {
            "univ": "Universidad de Granada",
            "programa": "Doctorado en Psicología",
            "url": "https://doctorados.ugr.es/psicologia/pages/ficha",
        },
        {
            "univ": "Universidad de Cádiz",
            "programa": "Doctorado en Ciencias de la Salud",
            "url": "https://escueladoctoral.uca.es/doctorado/oferta-doctorado/programa-de-doctorado-en-ciencias-de-la-salud-8203/",
        },
        {
            "univ": "Universidad de Cádiz",
            "programa": "Doctorado en Comunicación",
            "url": "https://escueladoctoral.uca.es/doctorado/oferta-doctorado/programa-de-doctorado-en-comunicacion-8213/",
        },
        {
            "univ": "Universidad de Alicante",
            "programa": "Doctorado en Biodiversidad y Conservación",
            "url": "https://web.ua.es/es/doctorados/biodiversidad-y-conservacion/",
        },
        {
            "univ": "Universidad de Alicante",
            "programa": "Doctorado en Filosofía",
            "url": "https://web.ua.es/es/doctorados/filosofia/",
        },
        {
            "univ": "Universidad Autónoma de Barcelona",
            "programa": "Doctorat en Física",
            "url": "https://www.uab.cat/ca/doctorats/fisica",
        },
    ]

    total = len(test_targets)
    success = 0

    for idx, t in enumerate(test_targets, 1):
        print(f"\n[{idx}/{total}] Evaluando {t['programa']} ({t['univ']})...")
        print(f"      URL inicial: {t['url']}")
        data = extract_generic_doctoral_program(t["url"], dl)

        n_lines = data.get("total_lineas", 0)
        escuela = data.get("escuela_doctorado", "")
        final_url = data.get("url_fuente", "")

        print(f"      -> URL resuelta: {final_url}")
        print(f"      -> Escuela: {escuela}")
        print(f"      -> Líneas de investigación extraídas ({n_lines}):")
        for l in data.get("lineas_investigacion", [])[:5]:
            print(f"         * {l}")
        if n_lines > 5:
            print(f"         * ... y {n_lines - 5} líneas más")

        if n_lines >= 2:
            success += 1
            print(f"      [RESULTADO] ¡ÉXITO ROTUNDO! Programa recuperado con {n_lines} líneas oficiales.")
        else:
            print(f"      [RESULTADO] Insuficiente.")

    print("\n" + "=" * 50)
    print(f"BALANCE FINAL DEL BANCO DE PRUEBAS:")
    print(f"Programas probados: {total}")
    print(f"Programas con líneas de investigación verificadas: {success}/{total} ({success/total*100:.1f}%)")
    print("=" * 50)


if __name__ == "__main__":
    main()
