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


def detect_runtime_capabilities() -> dict:
    """Devuelve capacidades y dependencias faltantes en formato serializable."""
    configured_browser = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH", "").strip()
    browser_path = configured_browser or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
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

