"""Promoción genérica y auditable de candidatos que ya superan la calidad."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path

from quality.data_quality import assess_plan_quality, promote_verified_candidate
from utils.degree_persistence import save_degree_payload


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _curricular_digest(plan: dict) -> str:
    """Hash del contenido curricular, excluyendo metadatos derivados."""
    return _digest({
        "resumen_creditos": plan.get("resumen_creditos"),
        "elementos_curriculares": plan.get("elementos_curriculares"),
    })


def _files(root: Path) -> list[Path]:
    return sorted((root / "Codigo" / "Crawler" / "Datos" / "planes_estudio").rglob("*.json"))


def _snapshot(root: Path) -> dict:
    snapshot = {}
    for path in _files(root):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        plan = record.get("plan_estudios") if isinstance(record, dict) else None
        assessment = assess_plan_quality(record, record.get("origen_fuente")) if isinstance(record, dict) else {}
        snapshot[str(path)] = {
            "record": _digest(record),
            "plan": _digest(plan) if isinstance(plan, dict) else None,
            "elements": len(plan.get("elementos_curriculares") or []) if isinstance(plan, dict) else 0,
            "publicable": bool(assessment.get("publicable")),
        }
    return snapshot


def run(root: str, output: str) -> dict:
    root_path = Path(root).resolve()
    before = _snapshot(root_path)
    evaluated = 0
    promoted = 0
    errors = []
    candidate_content_preserved = 0
    for path in _files(root_path):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            candidate = record.get("candidato_plan_estudios")
            if not isinstance(candidate, dict) or not candidate:
                continue
            evaluated += 1
            candidate_digest = _curricular_digest(candidate)
            working = copy.deepcopy(record)
            decision = promote_verified_candidate(working)
            if not decision.get("promoted"):
                continue
            if not isinstance(working.get("plan_estudios"), dict):
                errors.append("promocion_sin_plan")
                continue
            if not working["plan_estudios"].get("elementos_curriculares"):
                errors.append("promocion_sin_elementos")
                continue
            promoted_candidate = working["plan_estudios"]
            if _curricular_digest(promoted_candidate) != candidate_digest:
                errors.append("candidato_alterado_antes_de_persistir")
                continue
            save_degree_payload(
                plan_file=str(path),
                d_code=str(working.get("codigo_estudio") or ""),
                d_title=str(working.get("titulo") or ""),
                u_code=str(working.get("universidad_codigo") or ""),
                u_name=str(working.get("universidad_nombre") or ""),
                nivel_academico=str(working.get("nivel_academico") or ""),
                boe_url=working.get("boe_url"),
                boe_fecha=working.get("boe_fecha"),
                plan_estudios=promoted_candidate,
                all_boe_urls=working.get("all_boe_urls"),
                origen_fuente=working.get("origen_fuente"),
                existing_data=working,
                source_status="verificada",
                source_checked_at=datetime.now().isoformat(),
            )
            promoted += 1
            candidate_content_preserved += 1
        except Exception as exc:
            errors.append(type(exc).__name__)

    after = _snapshot(root_path)
    original_verified_loss = sum(
        int(before[key]["publicable"] and (key not in after or not after[key]["publicable"])
        )
        for key in before
    )
    original_plan_loss = sum(
        int(before[key]["plan"] is not None and (key not in after or after[key]["plan"] is None))
        for key in before
    )
    spurious = sum(
        int(not before[key]["publicable"] and after.get(key, {}).get("publicable") and after[key]["elements"] == 0)
        for key in before
        if key in after
    )
    result = {
        "campaign": "generic_candidate_quality_promotion",
        "files_before": len(before),
        "files_after": len(after),
        "candidates_evaluated": evaluated,
        "promoted": promoted,
        "candidate_content_preserved": candidate_content_preserved,
        "original_plan_loss": original_plan_loss,
        "original_verified_loss": original_verified_loss,
        "spurious_publications": spurious,
        "errors": errors,
        "no_original_plan_loss": original_plan_loss == 0,
        "no_verified_plan_loss": original_verified_loss == 0,
        "no_spurious_publication": spurious == 0,
        "no_promotion_errors": not errors,
        "publicable_before": sum(item["publicable"] for item in before.values()),
        "publicable_after": sum(item["publicable"] for item in after.values()),
    }
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = run(args.root, args.output)
    return 0 if result["no_promotion_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
