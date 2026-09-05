"""Módulo de persistencia unificada para planes de estudio y metadatos de titulaciones.

Centraliza la serialización atómica en formato JSON, particionado por universidad,
historial de versiones (snapshots) y actualización de checkpoints.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from checkpoint import atomic_json_dump
from config import (
    DEGREE_HISTORY_DIR,
    DEGREE_HISTORY_ENABLED,
    get_plan_filepath,
)
from data_quality import apply_plan_quality, source_record
from payload_contract import validate_degree_payload
from utils.text_utils import detect_academic_language

logger = logging.getLogger(__name__)

_VOLATILE_SNAPSHOT_FIELDS = {
    "fecha_procesado",
    "fecha_ultima_comprobacion_fuente",
    "fecha_ultima_comprobacion_guia",
    "fecha_obtencion",
    "evaluado_en",
    "estado_ultima_extraccion",
    "snapshot_hash",
    "previous_snapshot",
}


def _without_volatile_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_volatile_fields(item)
            for key, item in value.items()
            if key not in _VOLATILE_SNAPSHOT_FIELDS
        }
    if isinstance(value, list):
        return [_without_volatile_fields(item) for item in value]
    return value


def _stable_degree_snapshot_hash(payload: dict[str, Any]) -> str:
    """Calcula un hash sin marcas temporales para detectar cambios de datos."""
    stable = _without_volatile_fields(payload or {})
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_existing_payload(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _archive_previous_degree(
    path: str,
    previous: dict[str, Any],
    current_hash: str,
    u_code: str,
    d_code: str,
) -> str | None:
    """Archiva la versión anterior solo si el contenido estable ha cambiado."""
    if not DEGREE_HISTORY_ENABLED or not previous:
        return None
    previous_hash = str(
        previous.get("snapshot_hash") or _stable_degree_snapshot_hash(previous)
    )
    if previous_hash == current_hash:
        return None
    captured_at = datetime.now(timezone.utc)
    captured = captured_at.strftime("%Y%m%dT%H%M%SZ")
    history_dir = os.path.join(
        DEGREE_HISTORY_DIR,
        str(u_code or "unknown"),
        str(d_code or "unknown"),
    )
    os.makedirs(history_dir, exist_ok=True)
    archive_path = os.path.join(history_dir, f"{captured}_{previous_hash[:16]}.json")
    snapshot = dict(previous)
    snapshot["snapshot_hash"] = previous_hash
    snapshot["snapshot_archived_at"] = captured_at.isoformat()
    atomic_json_dump(snapshot, archive_path)
    return archive_path


def save_degree_payload(
    plan_file: str,
    d_code: str,
    d_title: str,
    u_code: str,
    u_name: str,
    nivel_academico: str,
    boe_url: str | None = None,
    boe_fecha: str | None = None,
    plan_estudios: dict | None = None,
    all_boe_urls: list | None = None,
    origen_fuente: str | None = None,
    checkpoint_mgr: Any = None,
    existing_data: dict | None = None,
    idioma: str | None = None,
    source_status: str | None = None,
    source_checked_at: str | None = None,
) -> dict[str, Any]:
    """Guarda atómicamente el payload JSON del plan de estudios y actualiza el checkpoint del sistema.

    Soporta particionado automático en subcarpeta de universidad y persistencia dual.
    """
    payload = existing_data if existing_data is not None else {}
    now_iso = datetime.now().isoformat()
    previous_on_disk = (
        _read_existing_payload(plan_file) if os.path.isfile(plan_file) else {}
    )

    # Determinar idioma predominante si no viene especificado
    if not idioma:
        if isinstance(plan_estudios, dict) and plan_estudios.get("idioma_predominante"):
            idioma = plan_estudios["idioma_predominante"]
        else:
            idioma = detect_academic_language(d_title)

    payload.update(
        {
            "codigo_estudio": d_code,
            "titulo": d_title,
            "nivel_academico": nivel_academico,
            "universidad_codigo": u_code,
            "universidad_nombre": u_name,
            "idioma_plan": idioma,
            "fecha_procesado": now_iso,
            "boe_url": boe_url if boe_url else payload.get("boe_url"),
            "boe_fecha": boe_fecha if boe_fecha else payload.get("boe_fecha"),
        }
    )
    if all_boe_urls:
        payload["all_boe_urls"] = all_boe_urls
    if source_status:
        payload["estado_fuente"] = str(source_status)
    if source_checked_at:
        payload["fecha_ultima_comprobacion_fuente"] = str(source_checked_at)
    if origen_fuente:
        payload["origen_fuente"] = origen_fuente
        source_url = boe_url or payload.get("web_fuente_directa_url")
        if source_url:
            fuentes = payload.setdefault("fuentes", [])
            if not isinstance(fuentes, list):
                fuentes = []
                payload["fuentes"] = fuentes
            record = source_record(
                source_url,
                "BOE" if "boe" in origen_fuente.lower() else origen_fuente.upper(),
                confidence=0.95 if "boe" in origen_fuente.lower() else 0.85,
            )
            fuentes[:] = [item for item in fuentes if item.get("url") != record["url"]]
            fuentes.append(record)

    # Evaluación de calidad y validación de contrato
    apply_plan_quality(payload, plan_estudios, origen_fuente)
    contract_payload = dict(payload)
    contract_payload["plan_estudios"] = plan_estudios
    payload["contrato_datos"] = validate_degree_payload(contract_payload)

    # Guardar en la ruta destino indicada
    current_hash = _stable_degree_snapshot_hash(payload)
    archived_path = _archive_previous_degree(
        plan_file, previous_on_disk, current_hash, u_code, d_code
    )
    payload["snapshot_hash"] = current_hash
    if archived_path:
        payload["previous_snapshot"] = archived_path
    parent_dir = os.path.dirname(os.path.abspath(plan_file))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    atomic_json_dump(payload, plan_file)

    # Guardar también en la ruta particionada para organización limpia del catálogo
    if u_code and d_code:
        part_path = get_plan_filepath(
            u_code, d_code, partitioned=True, ensure_dirs=True
        )
        if os.path.abspath(plan_file) != os.path.abspath(part_path):
            try:
                atomic_json_dump(payload, part_path)
            except Exception as exc:
                logger.warning(
                    "No se pudo escribir la copia particionada %s: %s", part_path, exc
                )

    if checkpoint_mgr:
        checkpoint_mgr.update_degree_record(d_code, boe_url, boe_fecha, now_iso)

    return payload
