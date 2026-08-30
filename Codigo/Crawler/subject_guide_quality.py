"""Evaluación determinista de cobertura de campos de una guía docente."""

from __future__ import annotations

from datetime import datetime, timezone
from config import SUBJECT_GUIDE_QUALITY_WEIGHTS


def _non_empty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _ects_present(guide: dict) -> bool:
    credits = guide.get("creditos") or {}
    if isinstance(credits, dict):
        return _non_empty(credits.get("total_ects")) or _non_empty(credits.get("ects"))
    return _non_empty(credits) or _non_empty(guide.get("creditos_ects"))


def assess_subject_guide_quality(guide: dict, expected_name: str = "", expected_code: str = "", source_url: str = "") -> dict:
    """Calcula una cobertura explicable; no es una probabilidad estadística."""
    guide = guide if isinstance(guide, dict) else {}
    fields = {
        "nombre_asignatura": _non_empty(guide.get("nombre_asignatura")),
        "codigo_asignatura": _non_empty(guide.get("codigo_asignatura")),
        "creditos_ects": _ects_present(guide),
        "temario": _non_empty(guide.get("temario")),
        "sistema_evaluacion": _non_empty(guide.get("sistema_evaluacion")),
        "competencias": _non_empty(guide.get("competencias")),
        "resultados_aprendizaje": _non_empty(guide.get("resultados_aprendizaje")),
        "profesorado": _non_empty(guide.get("profesorado")),
        "departamento": _non_empty(guide.get("departamento")),
    }
    weights = dict(SUBJECT_GUIDE_QUALITY_WEIGHTS)
    score = round(sum(weights[name] for name, present in fields.items() if present) * 100 / sum(weights.values()), 2)
    missing = [name for name, present in fields.items() if not present]
    if score >= 80:
        level = "alta"
    elif score >= 55:
        level = "media"
    else:
        level = "baja"
    return {
        "tipo": "cobertura_de_campos",
        "puntuacion": score,
        "nivel": level,
        "campos": {name: {"presente": present, "peso": weights[name]} for name, present in fields.items()},
        "campos_faltantes": missing,
        "identidad_esperada": {"nombre": str(expected_name or ""), "codigo": str(expected_code or "")},
        "fuente_url": str(source_url or guide.get("url_guia_docente") or ""),
        "evaluado_en": datetime.now(timezone.utc).isoformat(),
    }


def annotate_subject_guide_quality(guide: dict, expected_name: str = "", expected_code: str = "", source_url: str = "") -> dict:
    """Añade la evaluación sin sobrescribir ningún dato extraído."""
    if not isinstance(guide, dict):
        return guide
    guide["calidad_extraccion"] = assess_subject_guide_quality(
        guide, expected_name=expected_name, expected_code=expected_code, source_url=source_url
    )
    return guide

