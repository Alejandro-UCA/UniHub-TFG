"""Extractor especializado para honorarios y precios de universidades privadas."""

from __future__ import annotations

import re
from bs4 import BeautifulSoup


def parse_price_value(val_str: str, min_val: float, max_val: float) -> float | None:
    """Convierte cadenas numéricas europeas o estándar a float y valida que se encuentren en el rango esperado."""
    if not val_str:
        return None
    s = str(val_str).strip()
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.match(r"^\d{1,3}\.\d{3}$", s):
        s = s.replace(".", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        val_num = float(s)
        if min_val <= val_num <= max_val:
            return round(val_num, 2)
    except ValueError:
        pass
    return None


def extract_private_university_pricing(soup: BeautifulSoup, page_text: str) -> dict:
    """Rastrea e identifica la información de precios de matrícula en webs de universidades privadas."""
    pricing_data = {}
    text_lower = page_text.lower()

    # 1. Patrones para precio por crédito ECTS
    ects_patterns = [
        r"(?:precio|coste|importe|valor)\s*(?:del)?\s*(?:crédito|ects)\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?",
        r"(\d{2,4}(?:[.,]\d{1,2})?)\s*€?\s*/\s*(?:crédito|ects|cr)",
        r"(\d{2,4}(?:[.,]\d{1,2})?)\s*€?\s*por\s*crédito",
        r"(\d{2,4}(?:[.,]\d{1,2})?)\s*€\s*ects"
    ]
    for pat in ects_patterns:
        m = re.search(pat, text_lower)
        if m:
            price = parse_price_value(m.group(1), 15.0, 500.0)
            if price is not None:
                pricing_data["precio_credito_ects"] = price
                break

    # 1.5 Patrones para segunda/tercera/cuarta matrícula
    tier_patterns = {
        "precio_credito_2": [r"(?:segunda|2ª|2a)\s*matrícula\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?", r"crédito\s*repetidor\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?"],
        "precio_credito_3": [r"(?:tercera|3ª|3a)\s*matrícula\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?"],
        "precio_credito_4": [r"(?:cuarta|4ª|4a)\s*matrícula\D*?(\d{2,4}(?:[.,]\d{1,2})?)\s*€?"]
    }
    for key, patterns in tier_patterns.items():
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                price = parse_price_value(m.group(1), 15.0, 500.0)
                if price is not None:
                    pricing_data[key] = price
                    break

    # Clonar precios base si faltan recargos de matrícula en privadas
    if "precio_credito_ects" in pricing_data:
        pricing_data["precio_credito_2"] = pricing_data.get("precio_credito_2", pricing_data["precio_credito_ects"])
        pricing_data["precio_credito_3"] = pricing_data.get("precio_credito_3", pricing_data["precio_credito_ects"])
        pricing_data["precio_credito_4"] = pricing_data.get("precio_credito_4", pricing_data["precio_credito_ects"])

    # 2. Patrones para precio/importe anual total
    annual_patterns = [
        r"(?:precio|importe|coste|tuition|cuota|honorarios)\s*(?:total|anual|por\s*curso)?\D*?(\d{1,2}[.,]\d{3}|\d{4,5})\s*€?",
        r"(\d{1,2}[.,]\d{3}|\d{4,5})\s*€?\s*/\s*(?:año|curso|anual)",
        r"(\d{1,2}[.,]\d{3}|\d{4,5})\s*€\s*(?:al\s*año|por\s*curso)"
    ]
    for pat in annual_patterns:
        m = re.search(pat, text_lower)
        if m:
            price = parse_price_value(m.group(1), 1000.0, 45000.0)
            if price is not None:
                pricing_data["precio_estimado_anual"] = price
                break

    if "precio_credito_ects" in pricing_data and "precio_estimado_anual" not in pricing_data:
        pricing_data["precio_estimado_anual"] = round(pricing_data["precio_credito_ects"] * 60, 2)
    elif "precio_estimado_anual" in pricing_data and "precio_credito_ects" not in pricing_data:
        pricing_data["precio_credito_ects"] = round(pricing_data["precio_estimado_anual"] / 60, 2)

    return pricing_data


__all__ = [
    "extract_private_university_pricing",
    "parse_price_value",
]
