import sys
import time
import os
import tempfile
import threading
from bs4 import BeautifulSoup
from config import USER_AGENT, HTTP_TIMEOUT, SPA_ACCORDION_CLICK_DELAY

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class RenderResult(str):
    """
    Subclase de string para total retrocompatibilidad con código existente que espera
    un HTML string, pero enriquecida con metadatos de descargas binarias (PDFs).
    """
    def __new__(cls, html_content="", is_download=False, content_bytes=b"", filename=""):
        obj = str.__new__(cls, html_content or "")
        obj.is_download = is_download
        obj.content_bytes = content_bytes or b""
        obj.filename = filename or ""
        return obj


class SPALayoutCrawler:
    """
    Renders dynamic SPA university websites (React/Vue/Angular/AJAX)
    using Playwright headless Chromium, automatically expanding accordions and tabs.
    Thread-local architecture ensures full thread-safety in multi-worker pools.
    """
    _local = threading.local()
    _lock = threading.Lock()

    @classmethod
    def get_shared_instance(cls, timeout=HTTP_TIMEOUT):
        if not hasattr(cls._local, "instance") or cls._local.instance is None:
            cls._local.instance = SPALayoutCrawler(timeout=timeout)
        return cls._local.instance

    def __init__(self, timeout=HTTP_TIMEOUT):
        self.timeout = timeout * 1000  # ms for Playwright
        self._pw = None
        self._browser = None

    def _ensure_browser(self):
        if not PLAYWRIGHT_AVAILABLE:
            return None
        if self._browser is None or not self._browser.is_connected():
            try:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(headless=True)
            except Exception as e:
                print(f"   [SPA Crawler] Error al arrancar Chromium: {e}")
                self._browser = None
        return self._browser

    def render_spa_page(self, target_url: str) -> RenderResult:
        """
        Renders target_url in headless Chromium, clicks accordion/tab elements,
        and returns the fully rendered HTML string or intercepted binary download.
        Safe fallback if Playwright is unavailable.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return RenderResult("")

        context = None
        try:
            browser = self._ensure_browser()
            if not browser:
                return RenderResult("")

            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 960},
                accept_downloads=True
            )
            page = context.new_page()

            # Interceptar descargas automáticas forzadas por cabeceras Content-Disposition (Patrón A)
            try:
                page.goto(target_url, timeout=self.timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
            except Exception as nav_err:
                if "Download is starting" in str(nav_err) or "net::ERR_ABORTED" in str(nav_err):
                    try:
                        with page.expect_download(timeout=self.timeout) as dl_info:
                            try:
                                page.goto(target_url, timeout=self.timeout)
                            except Exception:
                                pass
                        dl = dl_info.value
                        temp_f = tempfile.NamedTemporaryFile(delete=False, suffix="_" + dl.suggested_filename)
                        temp_f.close()
                        dl.save_as(temp_f.name)
                        with open(temp_f.name, "rb") as f_in:
                            dl_bytes = f_in.read()
                        try:
                            os.remove(temp_f.name)
                        except Exception:
                            pass
                        print(f"   [SPA Crawler] Descarga binaria interceptada con éxito ({len(dl_bytes)} bytes): '{dl.suggested_filename}'")
                        return RenderResult("", is_download=True, content_bytes=dl_bytes, filename=dl.suggested_filename)
                    except Exception as dl_err:
                        print(f"   [SPA Crawler] Fallo al capturar descarga de '{target_url}': {dl_err}")
                        return RenderResult("")
                else:
                    raise nav_err

            # Expand interactive accordions, course tabs (1º a 4º curso) and specialization panels (Multilingüe)
            accordion_selectors = [
                "button", "a.accordion", ".tab", ".nav-link", ".panel-title", "details summary", ".accordion-header", ".ui-accordion-header", "li[role='tab']", "a[role='tab']"
            ]
            clicked_elements = set()
            for sel in accordion_selectors:
                try:
                    elements = page.query_selector_all(sel)
                    for elem in elements[:12]:
                        txt = (elem.inner_text() or "").strip().lower()
                        if not txt or txt in clicked_elements:
                            continue
                        course_tab_match = any(
                            k in txt for k in [
                                # Cursos 1º a 4º (ES, CA, GL, EU, EN)
                                "1º", "2º", "3º", "4º", "1er", "2º", "3º", "4º", "primer curs", "segon curs", "tercer curs", "quart curs",
                                "1r curs", "2n curs", "3r curs", "4t curs", "1. maila", "2. maila", "3. maila", "4. maila",
                                "primeiro curso", "segundo curso", "terceiro curso", "cuarto curso", "year 1", "year 2", "year 3", "year 4",
                                # Materias, especialidades y TFG
                                "asignatura", "materia", "plan de estudios", "pla d'estudis", "ikasketa plana", "syllabus",
                                "mención", "mencion", "especialidad", "optativas", "itinerari", "itinerario", "trabajo fin", "tfg", "tfm"
                            ]
                        )
                        if course_tab_match:
                            clicked_elements.add(txt)
                            try:
                                elem.click(timeout=1000)
                                page.wait_for_timeout(int(SPA_ACCORDION_CLICK_DELAY * 1000))
                            except Exception:
                                pass
                except Exception:
                    pass

            rendered_html = page.content()
            return RenderResult(rendered_html)
        except Exception as err:
            print(f"   [SPA Crawler] Headless browser fallback notice for '{target_url}': {err}")
            return RenderResult("")
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass

    def close(self):
        """Cleanly terminates the browser instance."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
