"""Reconciliación segura de metadatos derivados de planes ya persistidos."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from checkpoint import atomic_json_dump, load_json_safe
from data_quality import assess_plan_quality, synchronize_plan_quality_metadata


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def reconcile(root: str, output: str) -> dict:
    base = Path(root).resolve()
    plan_dir = base / "Codigo" / "Crawler" / "Datos" / "planes_estudio"
    result = {
        "root": str(base),
        "files": 0,
        "plan_records": 0,
        "changed": 0,
        "quality_metadata_changed": 0,
        "content_loss": 0,
        "publication_decision_changed": 0,
        "publication_decisions_reconciled": 0,
        "errors": [],
    }

    for path in sorted(plan_dir.rglob("*.json")):
        result["files"] += 1
        record = load_json_safe(path, default=None)
        if not isinstance(record, dict) or not isinstance(record.get("plan_estudios"), dict):
            continue
        result["plan_records"] += 1
        plan = record["plan_estudios"]
        before_elements = _digest(plan.get("elementos_curriculares"))
        before_publicable = bool((record.get("calidad_datos") or {}).get("publicable"))
        assessment = assess_plan_quality(record, record.get("origen_fuente"))
        after_publicable = bool(assessment.get("publicable"))
        if before_publicable != after_publicable:
            result["publication_decision_changed"] += 1

        before_record = _digest(record)
        synchronize_plan_quality_metadata(plan, assessment)
        # Una discrepancia entre la decisión almacenada y la evaluación actual
        # es precisamente un metadato obsoleto que esta herramienta debe
        # reparar. La decisión sólo se aplica después de comprobar que la lista
        # curricular no cambia; así se puede corregir una marca stale sin
        # fabricar, eliminar ni sustituir asignaturas.
        record["calidad_datos"] = assessment
        record["estado_ultima_extraccion"] = assessment["estado"]
        record["estado_calidad"] = assessment["estado"]
        after_elements = _digest(plan.get("elementos_curriculares"))
        if before_elements != after_elements:
            result["content_loss"] += 1
            result["errors"].append(f"contenido_curricular_alterado:{path}")
            continue
        if _digest(record) != before_record:
            atomic_json_dump(record, path)
            result["changed"] += 1
            if before_publicable != after_publicable:
                result["publication_decisions_reconciled"] += 1
            if before_record != _digest(record):
                result["quality_metadata_changed"] += 1

    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    reconcile(args.root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
