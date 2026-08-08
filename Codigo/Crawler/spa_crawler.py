import sys
import time
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
    """
    def __init__(self, timeout=HTTP_TIMEOUT):
        self.timeout = timeout * 1000  # ms for Playwright

    def render_spa_page(self, target_url: str) -> str:
        """
        Renders target_url in headless Chromium, clicks accordion/tab elements,
        and returns the fully rendered HTML string. Safe fallback if Playwright is unavailable.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 960}
                )
                page = context.new_page()
                page.goto(target_url, timeout=self.timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

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
                                page.wait_for_timeout(500)
                    except Exception:
                        pass

                rendered_html = page.content()
                browser.close()
                return rendered_html
        except Exception as err:
            print(f"   [SPA Crawler] Headless browser fallback notice for '{target_url}': {err}")
            return ""
