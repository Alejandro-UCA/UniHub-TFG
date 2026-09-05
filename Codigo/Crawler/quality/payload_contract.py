"""Contrato mínimo y auditable del payload de una titulación."""

from __future__ import annotations

import math
import re
from urllib.parse import urlparse


CONTRACT_VERSION = "1.0"


def _valid_http_url(value) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_degree_payload(payload: dict) -> dict:
    """Valida estructura, identidad y rangos sin exigir que el plan sea completo."""
    issues = []
    if not isinstance(payload, dict):
        return {"version": CONTRACT_VERSION, "valid": False, "issues": ["payload_no_objeto"]}
    degree_code = str(payload.get("codigo_estudio") or "").strip()
    university_code = str(payload.get("universidad_codigo") or "").strip()
    if not re.fullmatch(r"[A-Z0-9_-]{4,32}", degree_code, re.IGNORECASE):
        issues.append("codigo_estudio_invalido")
    if not re.fullmatch(r"[A-Z0-9_-]{3,8}", university_code, re.IGNORECASE):
        issues.append("universidad_codigo_invalido")
    if not str(payload.get("titulo") or "").strip():
        issues.append("titulo_vacio")
    plan = payload.get("plan_estudios")
    if plan is not None and not isinstance(plan, dict):
        issues.append("plan_no_objeto")
    if isinstance(plan, dict):
        elements = plan.get("elementos_curriculares") or []
        if not isinstance(elements, list):
            issues.append("elementos_no_lista")
        else:
            for index, element in enumerate(elements):
                if not isinstance(element, dict):
                    issues.append(f"elemento_{index}_no_objeto")
                    continue
                if not str(element.get("nombre_elemento") or element.get("materia") or "").strip():
                    issues.append(f"elemento_{index}_sin_nombre")
                ects = element.get("creditos_ects", element.get("creditos"))
                if ects is not None and ects != "":
                    try:
                        numeric_ects = float(str(ects).replace(",", "."))
                        if not math.isfinite(numeric_ects) or numeric_ects < 0 or numeric_ects > 60:
                            issues.append(f"elemento_{index}_ects_fuera_de_rango")
                    except (TypeError, ValueError):
                        issues.append(f"elemento_{index}_ects_no_numerico")
                guide = element.get("guia_docente")
                if guide is not None and not isinstance(guide, dict):
                    issues.append(f"elemento_{index}_guia_no_objeto")
                guide_url = element.get("url_guia_docente") or (guide or {}).get("url_guia_docente")
                if guide_url and not _valid_http_url(guide_url):
                    issues.append(f"elemento_{index}_url_guia_invalida")
    source_url = payload.get("boe_url") or payload.get("web_fuente_directa_url")
    if source_url and not _valid_http_url(source_url):
        issues.append("fuente_url_invalida")
    return {
        "version": CONTRACT_VERSION,
        "valid": not issues,
        "issues": sorted(set(issues)),
    }

