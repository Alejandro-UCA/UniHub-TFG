import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
import urllib.parse
from bs4 import BeautifulSoup
import requests

from config import (
    USER_AGENT,
    HTTP_TIMEOUT,
    SPA_ACCORDION_CLICK_DELAY,
    RESPECT_ROBOTS,
    ROBOTS_CHECK_TIMEOUT,
    MAX_RESPONSE_SIZE_BYTES,
    MAX_TEXT_RESPONSE_SIZE_BYTES,
    DOWNLOAD_CHUNK_SIZE,
)
from robots_policy import RobotsPolicy

logger = logging.getLogger("spa_crawler")

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
    Provides intelligent static fallback if Playwright or Chromium is unavailable.
    """
    _local = threading.local()
    _lock = threading.Lock()

    @classmethod
    def get_shared_instance(cls, timeout=HTTP_TIMEOUT):
        if not hasattr(cls._local, "instance") or cls._local.instance is None:
            cls._local.instance = SPALayoutCrawler(timeout=timeout)
        return cls._local.instance

    @classmethod
    def close_thread_instance(cls):
        """Cleanly terminates the thread-local browser instance."""
        if hasattr(cls._local, "instance") and cls._local.instance is not None:
            cls._local.instance.close()
            cls._local.instance = None

    def __init__(self, timeout=HTTP_TIMEOUT):
        self.timeout = timeout * 1000  # ms for Playwright
        self._pw = None
        self._browser = None
        self._robots_policy = RobotsPolicy(timeout=ROBOTS_CHECK_TIMEOUT)

    def _ensure_browser(self):
        if not PLAYWRIGHT_AVAILABLE:
            return None
        if self._browser is not None and not self._browser.is_connected():
            self.close()
        if self._browser is None:
            try:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
            except Exception as e:
                print(f"   [SPA Crawler] Error al arrancar Chromium: {e}")
                self.close()
        return self._browser

    def _extract_subjects_from_json_tree(self, node, accumulator: list[dict], depth: int = 0):
        """Recorre recursivamente un árbol JSON de hidratación buscando arrays y objetos de asignaturas."""
        if depth > 10 or len(accumulator) >= 120:
            return
        if isinstance(node, dict):
            name_val = node.get("nombre") or node.get("name") or node.get("nom") or node.get("asignatura") or node.get("assignatura") or node.get("title")
            ects_val = node.get("creditos") or node.get("credits") or node.get("ects") or node.get("creditos_ects")
            if isinstance(name_val, str) and len(name_val.strip()) >= 4:
                ects_num = 6.0
                has_valid_ects = False
                if ects_val is not None:
                    try:
                        ects_num = float(str(ects_val).replace(",", "."))
                        if 1.0 <= ects_num <= 30.0:
                            has_valid_ects = True
                    except ValueError:
                        pass

                car_val = node.get("caracter") or node.get("tipo") or node.get("type") or "OB"
                cur_val = str(node.get("curso") or node.get("course") or node.get("year") or "")
                cod_val = str(node.get("codigo") or node.get("code") or node.get("id") or "")

                if has_valid_ects or any(k in node for k in ["asignatura", "assignatura", "materia", "subject"]):
                    accumulator.append({
                        "codigo": cod_val,
                        "nombre": name_val.strip(),
                        "creditos": str(int(ects_num)) if ects_num.is_integer() else str(ects_num),
                        "caracter": str(car_val),
                        "curso": cur_val
                    })

            for v in node.values():
                self._extract_subjects_from_json_tree(v, accumulator, depth + 1)
        elif isinstance(node, list):
            for item in node:
                self._extract_subjects_from_json_tree(item, accumulator, depth + 1)

    def _static_fallback_render(self, target_url: str) -> RenderResult:
        """
        Fallback estático avanzado cuando Playwright o Chromium no están disponibles:
        1. Descarga el HTML estático de la página.
        2. Desempaqueta y normaliza componentes ocultos (<details>, aria-hidden="true", class="collapse").
        3. Analiza scripts de hidratación (__NEXT_DATA__, __NUXT_DATA__, JSON-LD, window.__INITIAL_STATE__)
           para sintetizar tablas de asignaturas legibles por el parser HTML.
        """
        if RESPECT_ROBOTS:
            allowed, _ = self._robots_policy.check(target_url)
            if not allowed:
                return RenderResult("")

        resp = None
        try:
            timeout_sec = int(self.timeout / 1000) if self.timeout else HTTP_TIMEOUT
            resp, final_url = self._safe_static_get(target_url, timeout_sec)
            if resp is None or resp.status_code != 200:
                return RenderResult("")

            content_type = resp.headers.get("Content-Type", "").lower()
            max_size = MAX_RESPONSE_SIZE_BYTES if "application/pdf" in content_type else MAX_TEXT_RESPONSE_SIZE_BYTES
            declared_size = resp.headers.get("Content-Length")
            if declared_size and int(declared_size) > max_size:
                logger.warning("Respuesta SPA descartada por Content-Length excesivo: %s", final_url)
                return RenderResult("")

            content = bytearray()
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > max_size:
                    logger.warning("Respuesta SPA descartada por exceder el límite de tamaño: %s", final_url)
                    return RenderResult("")
            if not content:
                return RenderResult("")
            content = bytes(content)

            if "application/pdf" in content_type or content.startswith(b"%PDF-"):
                filename = os.path.basename(urllib.parse.urlparse(final_url).path) or "plan_estudios.pdf"
                return RenderResult("", is_download=True, content_bytes=content, filename=filename)

            encoding = resp.encoding or "utf-8"
            html_text = content.decode(encoding, errors="replace")
            soup = BeautifulSoup(html_text, "html.parser")

            # 1. Expandir <details> y elementos ocultos en el DOM
            for dt in soup.find_all(["details"]):
                dt["open"] = "open"
            for hidden_el in soup.find_all(attrs={"aria-hidden": "true"}):
                hidden_el["aria-hidden"] = "false"
            for collapsed in soup.find_all(class_=re.compile(r"\b(collapse|collapsed|hide|hidden|tab-pane)\b")):
                cls_list = collapsed.get("class", [])
                collapsed["class"] = [c for c in cls_list if c not in ["collapse", "collapsed", "hide", "hidden"]]
                collapsed["style"] = "display: block !important;"

            # 2. Extraer datos estructurados de asignaturas en scripts de hidratación
            synthetic_subjects = []
            for script in soup.find_all("script"):
                stype = script.get("type", "").lower()
                sid = script.get("id", "").lower()
                stext = script.string or script.get_text() or ""
                if not stext or len(stext) < 20:
                    continue

                if sid in ["__next_data__", "__nuxt_data__"] or "json" in stype or "window.__initial_state__" in stext.lower() or "window.__preloaded_state__" in stext.lower():
                    json_str = ""
                    if sid in ["__next_data__", "__nuxt_data__"] or "json" in stype:
                        json_str = stext.strip()
                    else:
                        m_json = re.search(r"=\s*(\{.*\}|\[.*\])\s*;?", stext, re.DOTALL)
                        if m_json:
                            json_str = m_json.group(1)

                    if json_str:
                        try:
                            data = json.loads(json_str)
                            self._extract_subjects_from_json_tree(data, synthetic_subjects)
                        except Exception as json_error:
                            logger.debug("Bloque JSON SPA no válido: %s", json_error)

            if synthetic_subjects:
                table_tag = soup.new_tag("table", attrs={"class": "tabla-plan-estudios synthetic-spa"})
                tr_header = soup.new_tag("tr")
                for h_name in ["Código", "Asignatura", "Créditos ECTS", "Carácter", "Curso"]:
                    th = soup.new_tag("th")
                    th.string = h_name
                    tr_header.append(th)
                table_tag.append(tr_header)

                for subj in synthetic_subjects:
                    tr = soup.new_tag("tr")
                    td_cod = soup.new_tag("td")
                    td_cod.string = str(subj.get("codigo") or "")
                    td_nom = soup.new_tag("td")
                    td_nom.string = str(subj.get("nombre") or "")
                    td_ects = soup.new_tag("td")
                    td_ects.string = str(subj.get("creditos") or "")
                    td_car = soup.new_tag("td")
                    td_car.string = str(subj.get("caracter") or "OB")
                    td_cur = soup.new_tag("td")
                    td_cur.string = str(subj.get("curso") or "1")

                    tr.append(td_cod)
                    tr.append(td_nom)
                    tr.append(td_ects)
                    tr.append(td_car)
                    tr.append(td_cur)
                    table_tag.append(tr)

                if soup.body:
                    soup.body.append(table_tag)
                else:
                    soup.append(table_tag)

            return RenderResult(str(soup))
        except Exception as exc:
            logger.debug(f"Fallo en fallback estático SPA: {exc}")
            return RenderResult("")
        finally:
            if resp is not None:
                resp.close()

    @staticmethod
    def _is_allowed_redirect(target_url: str, original_url: str) -> bool:
        """Acepta sólo el dominio institucional inicial y sus subdominios."""
        target = urllib.parse.urlsplit(target_url)
        original = urllib.parse.urlsplit(original_url)
        if target.scheme not in {"http", "https"} or not target.hostname or not original.hostname:
            return False
        original_host = re.sub(r"^(?:www\d*\.)+", "", original.hostname.lower())
        target_host = re.sub(r"^(?:www\d*\.)+", "", target.hostname.lower())
        return target_host == original_host or target_host.endswith("." + original_host)

    def _safe_static_get(self, target_url: str, timeout_sec: int):
        """Sigue pocos redireccionamientos validados y deja el cuerpo en streaming."""
        current_url = target_url
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf"}
        for _ in range(6):
            if not self._is_allowed_redirect(current_url, target_url):
                logger.warning("Redirección SPA fuera del dominio institucional descartada: %s", current_url)
                return None, current_url
            response = requests.get(current_url, headers=headers, timeout=timeout_sec, stream=True, allow_redirects=False)
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    return None, current_url
                current_url = urllib.parse.urljoin(current_url, location)
                continue
            return response, current_url
        logger.warning("Demasiadas redirecciones en fallback SPA: %s", target_url)
        return None, current_url

    def render_spa_page(self, target_url: str) -> RenderResult:
        """
        Renders target_url in headless Chromium, clicks accordion/tab elements,
        and returns the fully rendered HTML string or intercepted binary download.
        Safe fallback if Playwright is unavailable.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return self._static_fallback_render(target_url)

        if RESPECT_ROBOTS:
            allowed, _ = self._robots_policy.check(target_url)
            if not allowed:
                return RenderResult("")

        context = None
        try:
            browser = self._ensure_browser()
            if not browser:
                return self._static_fallback_render(target_url)

            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 960},
                accept_downloads=True
            )
            page = context.new_page()

            # Bloqueo de recursos pesados (imágenes, medios, fuentes) para máxima velocidad
            def _block_unneeded_resources(route):
                if route.request.resource_type in ["image", "media", "font", "imageset"]:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", _block_unneeded_resources)

            # Interceptar descargas automáticas forzadas por cabeceras Content-Disposition (Patrón A)
            try:
                page.goto(target_url, timeout=self.timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(800)
            except Exception as nav_err:
                if "Download is starting" in str(nav_err) or "net::ERR_ABORTED" in str(nav_err):
                    try:
                        with page.expect_download(timeout=self.timeout) as dl_info:
                            try:
                                page.goto(target_url, timeout=self.timeout)
                            except Exception as navigation_retry_error:
                                logger.debug("Reintento de navegación para descarga fallido: %s", navigation_retry_error)
                        dl = dl_info.value
                        safe_filename = re.sub(r'[^\w.-]', '_', dl.suggested_filename or "document.pdf")
                        temp_f = tempfile.NamedTemporaryFile(delete=False, suffix="_" + safe_filename)
                        temp_f.close()
                        dl.save_as(temp_f.name)
                        with open(temp_f.name, "rb") as f_in:
                            dl_bytes = f_in.read()
                        try:
                            os.remove(temp_f.name)
                        except OSError as cleanup_error:
                            logger.warning("No se pudo eliminar el temporal descargado %s: %s", temp_f.name, cleanup_error)
                        print(f"   [SPA Crawler] Descarga binaria interceptada con éxito ({len(dl_bytes)} bytes): '{safe_filename}'")
                        return RenderResult("", is_download=True, content_bytes=dl_bytes, filename=safe_filename)
                    except Exception as dl_err:
                        print(f"   [SPA Crawler] Fallo al capturar descarga de '{target_url}': {dl_err}")
                        return RenderResult("")
                else:
                    raise nav_err

            # Expand interactive accordions and tabs in a single fast in-page JS evaluation
            try:
                page.evaluate("""() => {
                    const keywords = [
                        "1º", "2º", "3º", "4º", "1er", "primer curs", "segon curs", "tercer curs", "quart curs",
                        "1r curs", "2n curs", "3r curs", "4t curs", "1. maila", "2. maila", "3. maila", "4. maila",
                        "primeiro curso", "segundo curso", "terceiro curso", "cuarto curso", "year 1", "year 2", "year 3", "year 4",
                        "asignatura", "materia", "plan de estudios", "pla d'estudis", "ikasketa plana", "syllabus",
                        "mención", "mencion", "especialidad", "optativas", "itinerari", "itinerario", "trabajo fin", "tfg", "tfm"
                    ];
                    const elements = Array.from(document.querySelectorAll("button, a.accordion, .tab, .nav-link, .panel-title, details summary, .accordion-header, .ui-accordion-header, li[role='tab'], a[role='tab']"));
                    const matching = elements.filter(elem => {
                        const txt = (elem.innerText || "").trim().toLowerCase();
                        return txt && keywords.some(k => txt.includes(k));
                    });
                    for (const elem of matching.slice(0, 25)) {
                        try { elem.click(); } catch(e) {}
                    }
                }""")
                page.wait_for_timeout(350)
            except Exception as expansion_error:
                logger.debug("No se pudieron expandir todos los controles de la SPA: %s", expansion_error)

            rendered_html = page.content()
            return RenderResult(rendered_html)
        except Exception as err:
            print(f"   [SPA Crawler] Headless browser fallback notice for '{target_url}': {err}")
            return self._static_fallback_render(target_url)
        finally:
            if context:
                try:
                    context.close()
                except Exception as close_error:
                    logger.debug("No se pudo cerrar el contexto Playwright: %s", close_error, exc_info=True)

    def close(self):
        """Cleanly terminates the browser instance."""
        if self._browser:
            try:
                self._browser.close()
            except Exception as close_error:
                logger.debug("No se pudo cerrar el navegador Playwright: %s", close_error, exc_info=True)
            self._browser = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception as stop_error:
                logger.debug("No se pudo detener Playwright: %s", stop_error, exc_info=True)
            self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
