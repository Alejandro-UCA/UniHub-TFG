"""Genera una cola de recuperación priorizada a partir del corpus del piloto."""

from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path


def _priority(record: dict) -> tuple[int, str, str]:
    plan = record.get("plan_estudios")
    candidate = record.get("candidato_plan_estudios")
    state = str(record.get("estado_fuente") or "").lower()
    level = str(record.get("nivel_academico") or "").lower()
    if candidate:
        return (100, "promover_o_completar_candidato", "Ya existe una extracción parcial; falta validarla o completarla.")
    if plan:
        return (0, "sin_accion_inmediata", "Existe una instantánea curricular; sólo requiere revalidación según antigüedad.")
    if "doctor" in level and "99/2011" in level:
        return (95, "adaptador_doctorado", "Buscar página canónica del programa, líneas de investigación y actividades formativas.")
    if "robots_denegado" in state:
        return (80, "respetar_robots_y_buscar_fuente_alternativa", "Robots bloquea el origen; usar RUCT/BOE o una fuente institucional autorizada.")
    if "web_no_disponible" in state or "fuente_no_disponible" in state:
        return (85, "reintento_con_rescate_de_dominio", "Revalidar dominio, TLS, redirecciones y sitemap; registrar la causa exacta.")
    if record.get("web_fuente_directa_url") or record.get("boe_url"):
        return (90, "reprocesar_fuentes_conocidas", "Hay una URL conocida que todavía no produjo un plan publicable.")
    if "master" in level or "máster" in level or "grado" in level:
        return (70, "adaptador_universidad", "Crear o ampliar el adaptador del portal académico de la universidad.")
    return (40, "revisar_manualmente", "No hay fuente trazable ni clasificador específico suficiente.")


def build_queue(root: str) -> dict:
    data_dir = Path(root) / "Codigo" / "Crawler" / "Datos" / "planes_estudio"
    rows = []
    action_counts = collections.Counter()
    university_counts = collections.Counter()
    for path in sorted(data_dir.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        priority, action, reason = _priority(record)
        if priority <= 0:
            continue
        row = {
            "priority": priority,
            "action": action,
            "reason": reason,
            "file": str(path),
            "university_code": record.get("universidad_codigo") or path.parent.name,
            "study_code": record.get("codigo_estudio"),
            "title": record.get("titulo"),
            "level": record.get("nivel_academico"),
            "source_state": record.get("estado_fuente"),
            "direct_source_url": record.get("web_fuente_directa_url"),
            "boe_url": record.get("boe_url"),
            "has_candidate": bool(record.get("candidato_plan_estudios")),
        }
        rows.append(row)
        action_counts[action] += 1
        university_counts[str(row["university_code"])] += 1
    rows.sort(key=lambda row: (-row["priority"], row["university_code"], str(row["study_code"])))
    return {
        "root": str(Path(root).resolve()),
        "total_items": len(rows),
        "actions": dict(action_counts),
        "top_universities": university_counts.most_common(30),
        "items": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = build_queue(args.root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("root", "total_items", "actions", "top_universities")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
