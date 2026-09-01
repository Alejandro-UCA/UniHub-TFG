"""Detección explícita de capacidades opcionales del crawler.

Los parsers pueden degradar elegantemente cuando falta una dependencia, pero
la operación debe saber si esa degradación está ocurriendo. Este módulo no
lanza navegadores ni ejecuta OCR: solo inspecciona el entorno.
"""

from __future__ import annotations

import importlib.util
import os
import shutil


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def find_browser_executable() -> str:
    """Localiza un ejecutable Chromium disponible (Chromium, Chrome o Edge)."""
    # 1. Priorizar binarios nativos de Playwright si existen en rutas compartidas
    playwright_candidates = [
        "/ms-playwright/chromium-1234/chrome-linux64/chrome",
        "/home/crawler/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
        "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
    ]
    for pw_path in playwright_candidates:
        if pw_path and os.path.isfile(pw_path):
            return pw_path

    # 2. Variable de entorno configurada
    configured_browser = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH", "").strip()
    if configured_browser and os.path.isfile(configured_browser):
        if configured_browser == "/usr/bin/chromium" and os.path.isfile("/usr/lib/chromium/chromium"):
            return "/usr/lib/chromium/chromium"
        return configured_browser

    candidates = [
        "/usr/lib/chromium/chromium",
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


def detect_runtime_capabilities() -> dict:
    """Devuelve capacidades y dependencias faltantes en formato serializable."""
    browser_path = find_browser_executable()
    playwright_package = _module_available("playwright")
    pypdfium = _module_available("pypdfium2")
    pytesseract_package = _module_available("pytesseract")
    tesseract_binary = shutil.which("tesseract")
    capabilities = {
        "playwright_package": playwright_package,
        "chromium_binary": bool(browser_path),
        "javascript_rendering": bool(playwright_package and browser_path),
        "pypdfium2": pypdfium,
        "pytesseract_package": pytesseract_package,
        "tesseract_binary": bool(tesseract_binary),
        "ocr": bool(pypdfium and pytesseract_package and tesseract_binary),
        "browser_path": browser_path or "",
        "tesseract_path": tesseract_binary or "",
    }
    capabilities["missing"] = [
        name for name, available in (
            ("playwright_package", playwright_package),
            ("chromium_binary", bool(browser_path)),
            ("pypdfium2", pypdfium),
            ("pytesseract_package", pytesseract_package),
            ("tesseract_binary", bool(tesseract_binary)),
        ) if not available
    ]
    return capabilities


if __name__ == "__main__":
    import json
    print(json.dumps(detect_runtime_capabilities(), ensure_ascii=False, indent=2))

