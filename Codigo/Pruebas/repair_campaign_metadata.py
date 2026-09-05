"""Repara metadatos no curriculares perdidos durante una campaña auditable.

La herramienta es deliberadamente genérica: solo rellena campos de precio
ausentes en el piloto a partir de un árbol de referencia y de una auditoría
de archivos modificados. Nunca sustituye el plan curricular ni sus fuentes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


PRICING_FIELDS = (
    "precio_credito_ects",
    "precio_credito_2",
    "precio_credito_3",
    "precio_credito_4",
    "precio_estimado_anual",
    "fuente_precio",
)


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def repair(pilot_root: str, reference_root: str, audit_path: str) -> dict:
    pilot = Path(pilot_root).resolve()
    reference = Path(reference_root).resolve()
    audit = _load(Path(audit_path).resolve())
    repaired = []

    for item in audit.get("modified_plan_files", []):
        rel = item.get("path") if isinstance(item, dict) else None
        if not rel:
            continue
        target_path = pilot / rel
        reference_path = reference / rel
        if not target_path.is_file() or not reference_path.is_file():
            continue
        target = _load(target_path)
        source = _load(reference_path)
        changed_fields = []
        for field in PRICING_FIELDS:
            if target.get(field) in (None, "") and source.get(field) not in (None, ""):
                target[field] = source[field]
                changed_fields.append(field)
        if changed_fields:
            temporary_path = target_path.with_suffix(target_path.suffix + ".repair.tmp")
            temporary_path.write_text(
                json.dumps(target, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, target_path)
            repaired.append({"path": rel, "fields": changed_fields})

    return {
        "modified_candidates": len(audit.get("modified_plan_files", [])),
        "repaired_records": len(repaired),
        "repaired_fields": sum(len(item["fields"]) for item in repaired),
        "repaired": repaired,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--audit", required=True)
    args = parser.parse_args(argv)
    result = repair(args.pilot, args.reference, args.audit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
