"""Normalización, procedencia y validaciones de calidad para UniHub."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urldefrag, urlsplit, urlunsplit


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
    return issues

