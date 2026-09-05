"""Campaña acotada para validar la prioridad SPA de fuentes directas."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from data_quality import assess_plan_quality
from fase1_parte2_web_crawler import UniversityWebCrawler
from robots_policy import RobotsPolicy


def _snapshot(path: Path) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    quality = assess_plan_quality(record, record.get("origen_fuente"))
    return {
        "has_plan": isinstance(record.get("plan_estudios"), dict),
        "publicable": bool(quality.get("publicable")),
        "quality": record.get("estado_calidad"),
    }


def _eligible_groups(
    root: Path, max_groups: int | None = None
) -> list[tuple[dict, list[tuple[Path, dict]]]]:
    plans_root = root / "Codigo" / "Crawler" / "Datos" / "planes_estudio"
    universities = json.loads(
        (root / "Codigo" / "Crawler" / "Datos" / "universidades.json").read_text(
            encoding="utf-8"
        )
    )
    university_by_code = {
        str(item.get("codigo") or "").zfill(3): item
        for item in universities
        if isinstance(item, dict)
    }
    groups: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for path in sorted(plans_root.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not record.get("web_fuente_directa_url"):
            continue
        if not isinstance(record.get("candidato_plan_estudios"), dict):
            continue
        if isinstance(record.get("plan_estudios"), dict) and record["plan_estudios"].get(
            "elementos_curriculares"
        ):
            continue
        code = str(record.get("universidad_codigo") or "").zfill(3)
        if code in university_by_code:
            groups[code].append((path, record))

    policy = RobotsPolicy(timeout=2)
    selected = []
    for code, records in groups.items():
        allowed, _ = policy.check(str(records[0][1]["web_fuente_directa_url"]))
        if allowed:
            selected.append((university_by_code[code], records))
            if max_groups is not None and len(selected) >= max(1, max_groups):
                break
    return selected


def run(root: str, output: str, limit: int = 2, groups: int = 1) -> dict:
    root_path = Path(root).resolve()
    chosen_groups = _eligible_groups(root_path, max_groups=max(1, groups))
    if not chosen_groups:
        raise RuntimeError("No se encontró una cohorte directa con robots permitido.")
    selected = [
        (university, records[:max(1, limit)])
        for university, records in chosen_groups
    ]
    flat_selected = [item for _, records in selected for item in records]
    before = {str(path): _snapshot(path) for path, _ in flat_selected}
    results = []
    for university, records in selected:
        degrees = [
            {
                "codigo_estudio": record.get("codigo_estudio"),
                "titulo": record.get("titulo"),
                "nivel_academico": record.get("nivel_academico"),
            }
            for _, record in records
        ]
        results.append(
            UniversityWebCrawler().process_university_web(university, degrees, force=True)
        )
    after = {str(path): _snapshot(path) for path, _ in flat_selected}
    report = {
        "campaign": "generic_direct_spa_priority",
        "selected": len(flat_selected),
        "groups_selected": len(selected),
        "robots_allowed_groups": sum(bool(item.get("robots_allowed")) for item in results),
        "crawler_resolved": sum(int(item.get("resolved_degrees_count") or 0) for item in results),
        "recovered": sum(
            not before[path]["publicable"] and after[path]["publicable"]
            for path in before
        ),
        "original_plan_loss": sum(
            before[path]["has_plan"] and not after[path]["has_plan"] for path in before
        ),
        "original_verified_loss": sum(
            before[path]["publicable"] and not after[path]["publicable"] for path in before
        ),
        "before": before,
        "after": after,
    }
    report["no_original_plan_loss"] = report["original_plan_loss"] == 0
    report["no_verified_plan_loss"] = report["original_verified_loss"] == 0
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--groups", type=int, default=1)
    args = parser.parse_args(argv)
    run(args.root, args.output, args.limit, args.groups)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
