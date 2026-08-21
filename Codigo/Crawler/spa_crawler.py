import sys
import time
import threading
from bs4 import BeautifulSoup
from config import USER_AGENT, HTTP_TIMEOUT

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class SPALayoutCrawler:
    """
    Renders dynamic SPA university websites (React/Vue/Angular/AJAX)
    using Playwright headless Chromium, automatically expanding accordions and tabs.
    Supports single-use or persistent browser instance reuse for maximum performance.
    """
    _shared_instance = None
    _lock = threading.Lock()

    @classmethod
    def get_shared_instance(cls, timeout=HTTP_TIMEOUT):
        with cls._lock:
            if cls._shared_instance is None:
                cls._shared_instance = SPALayoutCrawler(timeout=timeout)
            return cls._shared_instance

    def __init__(self, timeout=HTTP_TIMEOUT):
        self.timeout = timeout * 1000  # ms for Playwright
        self._pw = None
        self._browser = None
        self._inst_lock = threading.Lock()

    def _ensure_browser(self):
        if not PLAYWRIGHT_AVAILABLE:
            return None
        with self._inst_lock:
            if self._browser is None or not self._browser.is_connected():
                try:
                    self._pw = sync_playwright().start()
                    self._browser = self._pw.chromium.launch(headless=True)
                except Exception as e:
                    print(f"   [SPA Crawler] Error al arrancar Chromium: {e}")
                    self._browser = None
            return self._browser

    def render_spa_page(self, target_url: str) -> str:
        """
        Renders target_url in headless Chromium, clicks accordion/tab elements,
        and returns the fully rendered HTML string. Safe fallback if Playwright is unavailable.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return ""

        try:
            browser = self._ensure_browser()
            if not browser:
                return ""

            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 960}
            )
            page = context.new_page()
            page.goto(target_url, timeout=self.timeout, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            # Expand interactive accordions or tabs if present
            accordion_selectors = [
                "button", "a.accordion", ".tab", ".nav-link", ".panel-title", "details", "summary"
            ]
            for sel in accordion_selectors:
                try:
                    elements = page.query_selector_all(sel)
                    for elem in elements[:5]:
                        txt = (elem.inner_text() or "").lower()
                        if any(k in txt for k in ["asignatura", "estudio", "curso", "plan", "materia"]):
                            elem.click(timeout=1000)
                            page.wait_for_timeout(400)
                except Exception:
                    pass

            rendered_html = page.content()
            context.close()
            return rendered_html
        except Exception as err:
            print(f"   [SPA Crawler] Headless browser fallback notice for '{target_url}': {err}")
            return ""

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
