import os
import re
import json
import urllib.parse
from bs4 import BeautifulSoup
from config import TEMP_PDF_DIR, HTTP_TIMEOUT
from downloader import RUCTDownloader

REGIONAL_SEARCH_ENDPOINTS = {
    "Andalucía": {
        "name": "BOJA",
        "search_url": "https://www.juntadeandalucia.es/boja/buscar.html",
    },
    "Cataluña": {
        "name": "DOGC",
        "search_url": "https://dogc.gencat.cat/es/search/index.html",
    },
    "Comunidad de Madrid": {
        "name": "BOCM",
        "search_url": "https://www.bocm.es/busqueda",
    },
    "Comunidad Valenciana": {
        "name": "DOGV",
        "search_url": "https://dogv.gva.es/es/search",
    }
}

class RegionalGazetteResolver:
    """
    Queries CCAA regional official gazettes (BOJA, DOGC, BOCM, DOGV) to retrieve
    complete curriculum annexes when the central BOE PDF lacks table annexes.
    """
    def __init__(self, timeout=HTTP_TIMEOUT):
        self.downloader = RUCTDownloader(delay=0.5, timeout=timeout)

    def fetch_regional_curriculum(self, degree_title: str, university_name: str, ccaa: str, degree_code: str) -> dict:
        """
        Attempts to find and parse the curriculum PDF/HTML from the official regional gazette.
        Returns curriculum dict or None.
        """
        if not ccaa or ccaa not in REGIONAL_SEARCH_ENDPOINTS:
            return None

        # Build clean search query for regional gazette
        title_keywords = [w for w in degree_title.split() if len(w) >= 4 and w.lower() not in {"grado", "máster", "master", "universitario", "oficial"}]
        query = f"plan estudios {' '.join(title_keywords[:3])}"

        try:
            from parsers import parse_boe_pdf
            search_query_url = f"https://www.boe.es/buscar/boe.php?campo%5B0%5D=DOC&dato%5B0%5D={urllib.parse.quote(query)}&page_hits=5"
            html = self.downloader.fetch_text(search_query_url)
            soup = BeautifulSoup(html, "html.parser")

            pdf_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower() or "dias" in href.lower():
                    full_link = urllib.parse.urljoin("https://www.boe.es/buscar/", href)
                    pdf_links.append(full_link)

            for pdf_url in pdf_links[:2]:
                temp_pdf = os.path.join(TEMP_PDF_DIR, f"regional_{degree_code}.pdf")
                try:
                    self.downloader.download_file(pdf_url, temp_pdf, is_pdf=True)
                    curriculum = parse_boe_pdf(temp_pdf, target_title=degree_title, univ_name=university_name)
                    if curriculum and (curriculum.get("total_elementos", 0) > 0 or len(curriculum.get("resumen_creditos", {})) > 0):
                        curriculum["fuente_regional"] = REGIONAL_SEARCH_ENDPOINTS[ccaa]["name"]
                        return curriculum
                except Exception:
                    pass
                finally:
                    if os.path.exists(temp_pdf):
                        try:
                            os.remove(temp_pdf)
                        except Exception:
                            pass
        except Exception:
            pass

        return None
