"""Campaña real de reconciliación de candidatos persistidos.

La campaña opera sobre el corpus indicado, registra un snapshot semántico
antes de consolidar y audita pérdidas, promociones y publicaciones espurias.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if _CRAWLER_DIR not in sys.path:
    sys.path.insert(0, _CRAWLER_DIR)

from data_quality import assess_plan_quality
from fase1_parte2_web_crawler import propagate_interuniversity_and_shared_boe_plans


def _digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted((root / "Codigo" / "Crawler" / "Datos" / "planes_estudio").rglob("*.json"))


def _snapshot(root: Path) -> dict:
    records = {}
    for path in _files(root):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        plan = record.get("plan_estudios") if isinstance(record, dict) else None
        quality = assess_plan_quality(record, record.get("origen_fuente")) if isinstance(record, dict) else {}
        records[str(path.relative_to(root))] = {
            "record_digest": _digest(record),
            "plan_digest": _digest(plan) if isinstance(plan, dict) else None,
            "plan_present": isinstance(plan, dict),
            "plan_elements": len(plan.get("elementos_curriculares") or []) if isinstance(plan, dict) else 0,
            "publicable": bool(quality.get("publicable")),
            "candidate_present": bool(record.get("candidato_plan_estudios")) if isinstance(record, dict) else False,
        }
    return records


def run(root: str, output: str) -> dict:
    root_path = Path(root).resolve()
    before = _snapshot(root_path)
    propagation = propagate_interuniversity_and_shared_boe_plans(str(root_path / "Codigo" / "Crawler" / "Datos" / "planes_estudio"))
    after = _snapshot(root_path)

    removed = sorted(set(before) - set(after))
    added = sorted(set(after) - set(before))
    changed = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    original_plan_loss = sorted(
        path for path in set(before) & set(after)
        if before[path]["plan_present"] and not after[path]["plan_present"]
    )
    original_verified_loss = sorted(
        path for path in set(before) & set(after)
        if before[path]["publicable"] and not after[path]["publicable"]
    )
    plan_changed_with_existing_detail = sorted(
        path for path in set(before) & set(after)
        if before[path]["plan_present"]
        and before[path]["plan_elements"] > 0
        and before[path]["plan_digest"] != after[path]["plan_digest"]
    )
    promoted = sorted(
        path for path in set(before) & set(after)
        if not before[path]["publicable"] and after[path]["publicable"]
        and before[path]["candidate_present"]
    )
    spurious = sorted(
        path for path in promoted
        if after[path]["plan_elements"] == 0
    )
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root_path),
        "plan_files_before": len(before),
        "plan_files_after": len(after),
        "propagation": propagation,
        "changed_plan_files": len(changed),
        "promoted_candidate_files": promoted,
        "removed_files": removed,
        "added_files": added,
        "original_plan_loss": original_plan_loss,
        "original_verified_loss": original_verified_loss,
        "plan_changed_with_existing_detail": plan_changed_with_existing_detail,
        "spurious_publications": spurious,
        "no_original_plan_loss": not removed and not original_plan_loss,
        "no_verified_plan_loss": not original_verified_loss,
        "no_spurious_publication": not spurious,
        "before_counts": {
            "publicable": sum(item["publicable"] for item in before.values()),
            "candidates": sum(item["candidate_present"] for item in before.values()),
        },
        "after_counts": {
            "publicable": sum(item["publicable"] for item in after.values()),
            "candidates": sum(item["candidate_present"] for item in after.values()),
        },
    }
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    run(args.root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
