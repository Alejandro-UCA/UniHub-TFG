"""Utilidades compartidas por las cuatro partes de la Fase 1.

Este módulo contiene únicamente infraestructura transversal: selección de
partes, descubrimiento canónico de planes, formateo de plantillas RUCT,
limpieza de temporales y notificación de la ETL. La lógica de negocio permanece
en cada ``fase1_parteX_*``.
"""

from __future__ import annotations

import os
import time
import json
import logging
from pathlib import Path
from typing import Iterable, Sequence

from core.config import (
    ADMIN_API_KEY,
    API_SYNC_TIMEOUT_SECONDS,
    API_SYNC_URL,
    PLANES_DIR,
)

logger = logging.getLogger(__name__)


PHASE_DESCRIPTIONS = {
    1: "Catálogos RUCT y resoluciones BOE",
    2: "Rastreo de webs universitarias",
    3: "Precios públicos y privados",
    4: "Guías docentes y asignaturas",
}


def normalize_phase_selection(parts: Iterable[int] | None) -> tuple[int, ...]:
    """Valida, deduplica y conserva el orden de una selección de partes."""
    requested = (1, 2, 3, 4) if parts is None else tuple(parts)
    normalized: list[int] = []
    for part in requested:
        if part not in PHASE_DESCRIPTIONS:
            raise ValueError(f"Parte de Fase 1 no válida: {part!r}")
        if part not in normalized:
            normalized.append(part)
    if not normalized:
        raise ValueError("Debe seleccionarse al menos una parte de la Fase 1.")
    return tuple(normalized)


def normalize_text(text: str) -> str:
    """Normaliza texto eliminando acentos y pasando a minúsculas para búsquedas semánticas robustas."""
    if not text:
        return ""
    import unicodedata
    return unicodedata.normalize("NFKD", str(text).lower()).encode("ASCII", "ignore").decode("utf-8").strip()


def matches_degree_title(title: str | None, query: str | None) -> bool:
    """Indica si el título de una titulación coincide con el filtro textual."""
    if not query or not str(query).strip():
        return True
    return normalize_text(query) in normalize_text(title or "")


def resolve_target_universities(
    raw_inputs: Sequence[str] | None = None,
    *,
    universities_data: Sequence[dict] | None = None,
    university_type: str | None = None,
) -> tuple[str, ...]:
    """Resuelve códigos, nombres y filtros de tipo hacia una tupla de códigos RUCT de 3 dígitos."""
    from core.checkpoint import load_json_safe
    from core.config import UNIVERSIDADES_JSON

    univ_list = universities_data
    if univ_list is None and os.path.exists(UNIVERSIDADES_JSON):
        univ_list = load_json_safe(UNIVERSIDADES_JSON, default=[])
    if not isinstance(univ_list, list):
        univ_list = []

    type_norm = (university_type or "").strip().lower()
    if type_norm in {"publica", "publicas", "public"}:
        target_type = "pública"
    elif type_norm in {"privada", "privadas", "private"}:
        target_type = "privada"
    else:
        target_type = None

    resolved_codes = set()

    if raw_inputs:
        flat_inputs = []
        for item in raw_inputs:
            if isinstance(item, str):
                flat_inputs.extend([part.strip() for part in item.replace(",", " ").split() if part.strip()])

        for raw in flat_inputs:
            if raw.isdigit():
                code = str(raw).zfill(3)
                resolved_codes.add(code)
            else:
                norm_q = normalize_text(raw)
                for u in univ_list:
                    if isinstance(u, dict):
                        u_name = normalize_text(u.get("nombre", ""))
                        u_code = str(u.get("codigo", "")).zfill(3)
                        if norm_q in u_name or norm_q == u_code:
                            resolved_codes.add(u_code)
    elif target_type and univ_list:
        for u in univ_list:
            if isinstance(u, dict) and normalize_text(u.get("tipo", "")) == normalize_text(target_type):
                resolved_codes.add(str(u.get("codigo", "")).zfill(3))

    if target_type and resolved_codes and univ_list:
        valid_type_codes = {
            str(u.get("codigo", "")).zfill(3)
            for u in univ_list
            if isinstance(u, dict) and normalize_text(u.get("tipo", "")) == normalize_text(target_type)
        }
        resolved_codes &= valid_type_codes

    return tuple(sorted(resolved_codes))


def format_ruct_url(template: str, code: str, *, degree: bool = False) -> str:
    """Formatea plantillas históricas y nuevas sin depender del alias usado."""
    values = {
        "codigo": code,
        "codigo_univ": code,
        "codigo_universidad": code,
        "codigo_estudio": code,
    }
    return template.format(**values)


def iter_plan_files(
    root: str = PLANES_DIR,
    *,
    deduplicate: bool = True,
) -> list[str]:
    """Devuelve planes JSON de forma recursiva y determinista.

    Durante la migración pueden coexistir ``planes_estudio/<codigo>.json`` y
    ``planes_estudio/<universidad>/<codigo>.json``. Al deduplicar se prioriza la
    ruta particionada, que es la representación canónica nueva.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    paths = sorted(
        (
            path for path in root_path.rglob("*.json")
            if path.stem.isdigit() or _is_plan_payload(path)
        ),
        key=lambda path: (path.stem, len(path.parts), str(path).lower()),
    )
    if not deduplicate:
        return [str(path) for path in paths]

    by_degree: dict[tuple[str, str], Path] = {}
    for path in paths:
        university_code = ""
        try:
            import json
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            university_code = str(payload.get("universidad_codigo") or "").zfill(3)
        except Exception:
            university_code = path.parent.name if path.parent != root_path else ""
        key = (university_code, path.stem)
        current = by_degree.get(key)
        if current is None or len(path.parts) > len(current.parts):
            by_degree[key] = path
    return [str(by_degree[key]) for key in sorted(by_degree)]


def _is_plan_payload(path: Path) -> bool:
    """Acepta códigos alfanuméricos solo si el JSON demuestra ser un plan."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return isinstance(payload, dict) and bool(str(payload.get("codigo_estudio") or "").strip())
    except (OSError, ValueError, TypeError):
        return False


def cleanup_temporary_files(
    directory: str,
    suffixes: Sequence[str] = (".tmp", ".pdf", ".xls", ".download"),
    max_age_seconds: float = 3600,
) -> int:
    """Elimina únicamente temporales conocidos del directorio indicado."""
    if not os.path.isdir(directory):
        return 0
    removed = 0
    for entry in os.scandir(directory):
        if entry.is_file() and entry.name.lower().endswith(tuple(suffixes)):
            try:
                if max_age_seconds is not None and time.time() - entry.stat().st_mtime < max_age_seconds:
                    continue
                os.remove(entry.path)
                removed += 1
            except OSError:
                pass
    return removed


def trigger_api_etl_sync(
    urls: Iterable[str] | None = None,
    *,
    api_key: str | None = None,
    timeout: float = API_SYNC_TIMEOUT_SECONDS,
) -> bool:
    """Solicita una ETL sincrónica y confirma que la transacción finalizó."""
    import requests

    candidates = list(urls) if urls is not None else [
        API_SYNC_URL,
        "http://unihub_api:8000/api/v1/admin/sync-etl",
        "http://localhost/api/v1/admin/sync-etl",
        "http://localhost:8000/api/v1/admin/sync-etl",
    ]
    headers = {}
    resolved_key = ADMIN_API_KEY if api_key is None else api_key
    if resolved_key:
        headers["X-API-Key"] = resolved_key

    seen: set[str] = set()
    deadline = time.monotonic() + max(0.1, float(timeout))
    for url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            response = requests.post(url, headers=headers, timeout=min(float(timeout), remaining))
            if response.ok:
                return True
            logger.warning("La ETL remota respondió %s en %s", response.status_code, url)
        except requests.RequestException:
            logger.info("No se pudo contactar con la ETL remota en %s (API offline o en entorno standalone)", url)
            continue
    return False
