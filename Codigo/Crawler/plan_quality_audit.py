"""Auditoría ligera de cobertura e integridad de planes persistidos."""

from __future__ import annotations

import json
import os
from collections import Counter

from phase_common import iter_plan_files


REQUIRED_IDENTITY_FIELDS = (
    "codigo_estudio",
    "titulo",
    "nivel_academico",
    "universidad_codigo",
    "universidad_nombre",
)


def _load_catalog_degrees(catalog_path: str, target_codes=None) -> list[dict]:
    if not catalog_path or not os.path.exists(catalog_path):
        return []
    try:
        with open(catalog_path, "r", encoding="utf-8") as handle:
            catalog = json.load(handle)
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(catalog, dict):
        return []
    selected = {
        str(code).strip().zfill(3)
        for code in (target_codes or ())
        if str(code).strip()
    }
    result = []
    for u_code, value in catalog.items():
        normalized_code = str(u_code).strip().zfill(3)
        if selected and normalized_code not in selected:
            continue
        degrees = value.get("titulaciones_vigentes", []) if isinstance(value, dict) else []
        for degree in degrees if isinstance(degrees, list) else []:
            if isinstance(degree, dict) and degree.get("codigo_estudio"):
                result.append({
                    "universidad_codigo": normalized_code,
                    **degree,
                })
    return result


def audit_plan_records(plan_dir: str, catalog_path: str = "", target_codes=None) -> dict:
    """Devuelve métricas comparables de presencia, identidad y contenido.

    Los candidatos parciales se cuentan como extracción bruta, pero no como
    planes publicables. Los doctorados no se penalizan por carecer de
    asignaturas, aunque sí se audita la presencia de su registro.
    """
    files = iter_plan_files(plan_dir)
    records = []
    invalid_json = 0
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            invalid_json += 1
            continue
        if isinstance(payload, dict):
            records.append((path, payload))

    expected = _load_catalog_degrees(catalog_path, target_codes)
    expected_keys = {
        (str(item.get("universidad_codigo") or "").zfill(3), str(item.get("codigo_estudio")))
        for item in expected
    }
    seen_keys = set()
    identity_valid = 0
    sparse_paths = []
    states = Counter()
    accepted_elements = 0
    candidate_elements = 0
    accepted_plans = 0
    candidate_plans = 0
    for path, payload in records:
        path_obj = os.path.abspath(path)
        parent_code = os.path.basename(os.path.dirname(path_obj))
        u_code = str(payload.get("universidad_codigo") or parent_code or "").zfill(3)
        d_code = str(payload.get("codigo_estudio") or os.path.splitext(os.path.basename(path_obj))[0]).strip()
        if d_code:
            seen_keys.add((u_code, d_code))
        if all(str(payload.get(field) or "").strip() for field in REQUIRED_IDENTITY_FIELDS):
            identity_valid += 1
        else:
            sparse_paths.append(path)
        states[str(payload.get("estado_fuente") or "sin_estado")] += 1
        plan = payload.get("plan_estudios")
        candidate = payload.get("candidato_plan_estudios")
        if isinstance(plan, dict) and plan.get("elementos_curriculares"):
            accepted_plans += 1
            accepted_elements += len(plan.get("elementos_curriculares") or [])
        if isinstance(candidate, dict) and candidate.get("elementos_curriculares"):
            candidate_plans += 1
            candidate_elements += len(candidate.get("elementos_curriculares") or [])

    expected_missing = sorted(expected_keys - seen_keys)
    return {
        "files_seen": len(files),
        "json_records": len(records),
        "invalid_json": invalid_json,
        "identity_valid": identity_valid,
        "sparse_records": len(sparse_paths),
        "expected_catalog_records": len(expected),
        "expected_missing_records": len(expected_missing),
        "expected_missing_codes": [code for _, code in expected_missing[:25]],
        "accepted_plan_records": accepted_plans,
        "candidate_plan_records": candidate_plans,
        "accepted_elements": accepted_elements,
        "candidate_elements": candidate_elements,
        "source_states": dict(sorted(states.items())),
    }
