"""Campaña genérica de revalidación de candidatos BOE sólo-resumen."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CRAWLER_DIR = BASE_DIR / "Codigo" / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from config import PLANES_DIR, find_plan_filepath  # noqa: E402
from fase1_parte1_ruct_boe import run_phase1_part1  # noqa: E402
from data_quality import assess_plan_quality  # noqa: E402


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _select_cases(
    max_cases: int,
    max_universities: int,
    evidence: str = "summary",
    offset: int = 0,
) -> list[dict]:
    selected = []
    seen_universities = set()
    skipped = 0
    for path in sorted(Path(PLANES_DIR).rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        quality = record.get("calidad_datos") or {}
        if evidence == "persisted_urls":
            if record.get("plan_estudios") is not None:
                continue
            if record.get("candidato_plan_estudios"):
                continue
            persisted_urls = record.get("all_boe_urls")
            if not isinstance(persisted_urls, list) or not persisted_urls:
                continue
            academic_level = str(record.get("nivel_academico") or "").casefold()
            if not any(marker in academic_level for marker in ("grado", "master", "máster")):
                continue
        elif not isinstance(record.get("candidato_plan_estudios"), dict):
            continue
        if evidence != "persisted_urls" and quality.get("completitud") != "solo_resumen":
            continue
        university = str(record.get("universidad_codigo") or "").zfill(3)
        title = str(record.get("titulo") or "").strip()
        if not university or not title or university in seen_universities:
            continue
        seen_universities.add(university)
        if skipped < max(0, int(offset)):
            skipped += 1
            continue
        selected.append({
            "university": university,
            "title": title,
            "path": str(path),
        })
        if len(selected) >= max(0, int(max_cases)) or len(seen_universities) >= max(0, int(max_universities)):
            break
    return selected


def run_campaign(
    max_cases: int = 8,
    max_universities: int = 8,
    evidence: str = "summary",
    offset: int = 0,
) -> dict:
    if evidence not in {"summary", "persisted_urls"}:
        raise ValueError("evidence must be 'summary' or 'persisted_urls'")
    cases = _select_cases(max_cases, max_universities, evidence, offset)
    results = []
    for case in cases:
        path = Path(case["path"])
        try:
            before = json.loads(path.read_text(encoding="utf-8"))
            before_plan = before.get("plan_estudios")
            before_elements = _digest((before_plan or {}).get("elementos_curriculares") if isinstance(before_plan, dict) else None)
            before_publicable = bool((before.get("calidad_datos") or {}).get("publicable"))
            run_result = run_phase1_part1(
                target_universities=[case["university"]],
                degree_title_filter=case["title"],
                force=True,
                max_workers=1,
            )
            after = json.loads(path.read_text(encoding="utf-8"))
            after_plan = after.get("plan_estudios")
            after_quality = assess_plan_quality(after, after.get("origen_fuente"))
            after_elements = _digest((after_plan or {}).get("elementos_curriculares") if isinstance(after_plan, dict) else None)
            curricular_content_unchanged = (
                not isinstance(before_plan, dict)
                or not isinstance(after_plan, dict)
                or before_elements == after_elements
            )
            results.append({
                "status": run_result.get("status"),
                "plan_before": isinstance(before_plan, dict),
                "plan_after": isinstance(after_plan, dict),
                "elements_after": len((after_plan or {}).get("elementos_curriculares", [])) if isinstance(after_plan, dict) else 0,
                "publicable_before": before_publicable,
                "publicable_after": bool((after.get("calidad_datos") or {}).get("publicable")),
                "recomputed_publicable_after": bool(after_quality.get("publicable")),
                "curricular_content_unchanged": curricular_content_unchanged,
                "pipeline_boe_search": run_result.get("boe_search_discovery", {}),
                "pipeline_boe_summary": run_result.get("boe_summary_discovery", {}),
                "pipeline_persisted_boe": run_result.get("persisted_boe_revalidation", {}),
            })
        except Exception as exc:
            results.append({"status": "error", "error": type(exc).__name__})
    return {
        "campaign": f"generic_boe_{evidence}_revalidation",
        "evidence": evidence,
        "offset": max(0, int(offset)),
        "cases_selected": len(cases),
        "results": results,
        "summary": {
            "plans_recovered": sum(int(item.get("plan_after") and not item.get("plan_before")) for item in results),
            "new_publications": sum(int(item.get("publicable_after") and not item.get("publicable_before")) for item in results),
            "content_loss": sum(
                int(
                    not item.get("curricular_content_unchanged", False)
                    and item.get("plan_before", False)
                    and item.get("plan_after", False)
                )
                for item in results
                if item.get("status") != "error"
            ),
            "errors": sum(int(item.get("status") == "error") for item in results),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=8)
    parser.add_argument("--max-universities", type=int, default=8)
    parser.add_argument("--evidence", choices=("summary", "persisted_urls"), default="summary")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run_campaign(args.max_cases, args.max_universities, args.evidence, args.offset)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
