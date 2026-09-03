"""Normalización, procedencia y validaciones de calidad para UniHub."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urldefrag, urlsplit, urlunsplit

from curriculum_validator import get_curriculum_completeness_status, is_doctorate_program


QUALITY_VERIFIED_BOE = "verificado_boe"
QUALITY_VERIFIED_UNIVERSITY = "verificado_universidad"
QUALITY_VERIFIED_DOCTORATE = "verificado_programa_doctoral"
QUALITY_PARTIAL = "parcial"
QUALITY_PENDING_REVIEW = "pendiente_revision"
QUALITY_NO_VERIFIED_DATA = "sin_datos_verificados"

PUBLISHABLE_QUALITY_STATUSES = frozenset({
    QUALITY_VERIFIED_BOE,
    QUALITY_VERIFIED_UNIVERSITY,
    QUALITY_VERIFIED_DOCTORATE,
})


def _normalise_title_tokens(value: object) -> set[str]:
    """Obtiene los términos significativos de un título para detectar cruces obvios."""
    return {
        token
        for token in re.findall(r"[a-záéíóúüñ]{4,}", str(value or "").lower())
        if token not in {"grado", "master", "máster", "universidad", "programa", "estudios"}
    }


def is_publishable_quality_status(status: object) -> bool:
    """Indica si el estado autoriza publicar un currículo como verificado."""
    return str(status or "").strip().lower() in PUBLISHABLE_QUALITY_STATUSES


def canonical_url(url: str) -> str:
    if not url:
        return ""
    clean, _ = urldefrag(str(url).strip())
    parts = urlsplit(clean)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def content_sha256(content: bytes | None) -> str | None:
    return hashlib.sha256(content).hexdigest() if content else None


def source_record(url: str, source_type: str, *, confidence: float = 0.0, content: bytes | None = None) -> dict:
    return {
        "url": canonical_url(url),
        "tipo": source_type,
        "confianza": max(0.0, min(1.0, float(confidence))),
        "sha256": content_sha256(content),
        "fecha_obtencion": datetime.now(timezone.utc).isoformat(),
    }


def validate_plan_identity(payload: dict) -> list[str]:
    """Devuelve anomalías que deben impedir la promoción a plan verificado."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["payload_no_objeto"]
    if not re.fullmatch(r"[A-Z0-9_-]{4,32}", str(payload.get("codigo_estudio") or "")):
        issues.append("codigo_estudio_invalido")
    if not str(payload.get("titulo", "")).strip():
        issues.append("titulo_vacio")
    plan = payload.get("plan_estudios")
    if plan is not None and not isinstance(plan, dict):
        issues.append("plan_no_objeto")
    if isinstance(plan, dict) and plan.get("nombre_plan"):
        title_tokens = _normalise_title_tokens(payload.get("titulo"))
        plan_tokens = _normalise_title_tokens(plan.get("nombre_plan"))
        if title_tokens and plan_tokens and not title_tokens.intersection(plan_tokens):
            issues.append("titulo_plan_no_coincide")
    return issues


def assess_plan_quality(payload: dict, source_type: str | None = None) -> dict:
    """Clasifica un plan sin promocionarlo ni modificar el payload de entrada.

    La clasificación es deliberadamente conservadora: una fuente no trazable,
    una identidad inconsistente o una estructura incompleta nunca obtienen un
    estado publicable. El estado se usa igual en crawler, ETL y API.
    """
    payload = payload if isinstance(payload, dict) else {}
    plan = payload.get("plan_estudios")
    source_type = str(source_type or payload.get("origen_fuente") or "").strip().lower()
    issues = validate_plan_identity(payload)
    # La fuente que se está evaluando tiene prioridad. Un plan web puede
    # conservar un BOE histórico como respaldo, pero no debe etiquetarse como
    # verificado por BOE si la evidencia actual procede de la universidad.
    if any(marker in source_type for marker in ("web_oficial", "centro_adscrito", "interuniversitario")):
        source_url = payload.get("web_fuente_directa_url") or payload.get("boe_url")
    else:
        source_url = payload.get("boe_url") or payload.get("web_fuente_directa_url")
    if not source_url:
        source_url = next(
            (
                item.get("url")
                for item in payload.get("fuentes", [])
                if isinstance(item, dict) and item.get("url")
            ),
            None,
        )
    if source_url:
        parsed_source = urlsplit(str(source_url))
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            issues.append("fuente_url_invalida")
    else:
        issues.append("fuente_no_trazable")

    completeness = get_curriculum_completeness_status(payload)
    result = {
        "estado": QUALITY_NO_VERIFIED_DATA,
        "publicable": False,
        "errores": sorted(set(issues)),
        "completitud": completeness["status"],
        "plan_completo": completeness["is_complete"],
        "ects_totales_detectados": completeness["total_ects_obtained"],
        "ects_exigidos": completeness["required_ects"],
        "fuente_url": canonical_url(source_url) if source_url else None,
        "tipo_fuente": source_type or None,
    }
    if not isinstance(plan, dict) or not plan:
        return result
    if issues:
        result["estado"] = QUALITY_PENDING_REVIEW
        return result
    if not completeness["is_complete"]:
        result["estado"] = QUALITY_PARTIAL
        return result

    is_boe = "boe" in source_type or "boe.es" in str(source_url or "").lower()
    is_official_web = any(marker in source_type for marker in (
        "web_oficial", "centro_adscrito", "resolucion_boe", "interuniversitario",
    ))
    if is_doctorate_program(payload.get("nivel_academico", ""), payload.get("titulo", "")) and completeness["is_complete"]:
        result.update({"estado": QUALITY_VERIFIED_DOCTORATE, "publicable": True})
    elif is_boe:
        result.update({"estado": QUALITY_VERIFIED_BOE, "publicable": True})
    elif is_official_web:
        result.update({"estado": QUALITY_VERIFIED_UNIVERSITY, "publicable": True})
    else:
        result["estado"] = QUALITY_PENDING_REVIEW
        result["errores"].append("tipo_fuente_no_verificable")
    return result


def apply_plan_quality(payload: dict, candidate_plan: dict | None, source_type: str | None = None) -> dict:
    """Conserva sólo planes verificados en ``plan_estudios`` y audita candidatos.

    Un candidato fallido no puede sobrescribir un plan ya publicado. Si no existe
    un plan válido anterior, se almacena exclusivamente como candidato para
    revisión y el catálogo queda sin currículo publicable.
    """
    if not isinstance(payload, dict):
        raise TypeError("El payload de calidad debe ser un diccionario.")
    previous_plan = payload.get("plan_estudios")
    payload["plan_estudios"] = candidate_plan
    assessment = assess_plan_quality(payload, source_type)
    payload["calidad_datos"] = assessment
    payload["estado_ultima_extraccion"] = assessment["estado"]

    if assessment["publicable"]:
        payload["estado_calidad"] = assessment["estado"]
        payload.pop("candidato_plan_estudios", None)
        return assessment

    if isinstance(candidate_plan, dict) and candidate_plan:
        payload["candidato_plan_estudios"] = candidate_plan
    payload["plan_estudios"] = previous_plan if isinstance(previous_plan, dict) else None
    if not is_publishable_quality_status(payload.get("estado_calidad")):
        payload["estado_calidad"] = QUALITY_NO_VERIFIED_DATA
    return assessment
