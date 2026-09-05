"""Utilidades centralizadas para extracción, validación y cómputo de créditos ECTS."""

from __future__ import annotations

import re
from typing import Any

RE_CREDIT_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
RE_CREDIT_UNIT = re.compile(r"(?:ECTS|cr[eéè]dit(?:os|s)?|credit(?:os|s)?)", re.I)


def parse_credit_number(
    raw_value: Any,
    min_val: float | None = 0.0,
    max_val: float | None = 360.0,
) -> float | None:
    """Extrae un valor numérico de créditos ECTS a partir de un entero, float o texto.

    Soporta separadores decimales ',' y '.' y valida opcionalmente límites admisibles.
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        val = float(raw_value)
    else:
        s = str(raw_value).strip()
        match = RE_CREDIT_NUMBER.search(s)
        if not match:
            return None
        try:
            val = float(match.group(0).replace(",", "."))
        except ValueError:
            return None

    if min_val is not None and val < min_val:
        return None
    if max_val is not None and val > max_val:
        return None
    return val


def compute_curriculum_total_ects(elements: list[dict[str, Any]]) -> float:
    """Calcula la suma total de créditos ECTS de una lista de asignaturas o módulos."""
    if not isinstance(elements, list):
        return 0.0
    total = 0.0
    for el in elements:
        if not isinstance(el, dict):
            continue
        c = parse_credit_number(el.get("creditos"), min_val=0.0, max_val=120.0)
        if c is not None:
            total += c
    return round(total, 2)
