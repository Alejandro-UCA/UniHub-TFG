"""Sonda empírica no mutante de URLs BOE históricas persistidas."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CRAWLER_DIR = BASE_DIR / "Codigo" / "Crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from boe_search_discovery import rebuild_persisted_boe_candidates  # noqa: E402
from checkpoint import load_json_safe  # noqa: E402
from config import PLANES_DIR  # noqa: E402
from curriculum_validator import get_curriculum_completeness_status  # noqa: E402
from fase1_parte1_ruct_boe import RUCTDownloader  # noqa: E402
from parsers import parse_boe_pdf  # noqa: E402


def _select_cases(max_cases: int) -> list[dict]:
    selected = []
    seen_universities = set()
    for path in sorted(Path(PLANES_DIR).rglob("*.json")):
        record = load_json_safe(path, default=None)
        if not isinstance(record, dict):
            continue
        if record.get("plan_estudios") is not None or record.get("candidato_plan_estudios"):
            continue
        level = str(record.get("nivel_academico") or "").casefold()
        if not any(marker in level for marker in ("grado", "master", "máster")):
            continue
        candidates = rebuild_persisted_boe_candidates(record.get("all_boe_urls"), record.get("boe_fecha"), limit=3)
        if not candidates:
            continue
        university = str(record.get("universidad_codigo") or "").zfill(3)
        if not university or university in seen_universities:
            continue
        seen_universities.add(university)
        selected.append({"record": record, "candidates": candidates})
        if len(selected) >= max(0, int(max_cases)):
            break
    return selected


def run(max_cases: int = 30, max_urls: int = 3) -> dict:
    cases = _select_cases(max_cases)
    results = []
    with RUCTDownloader(delay=0.2, timeout=15, max_retries=1, phase="persisted_boe_empirical_probe") as downloader:
        for item in cases:
            record = item["record"]
            best = None
            tested = 0
            downloaded = 0
            errors = 0
            for candidate in item["candidates"][: max(0, int(max_urls))]:
                tested += 1
                try:
                    content = downloader.fetch_content(candidate["url"], max_size_bytes=12 * 1024 * 1024)
                    if not content:
                        continue
                    downloaded += 1
                    parsed = parse_boe_pdf(
                        content,
                        target_title=str(record.get("titulo") or ""),
                        univ_name=str(record.get("universidad_nombre") or ""),
                    )
                    status = get_curriculum_completeness_status({
                        "nivel_academico": record.get("nivel_academico"),
                        "titulo": record.get("titulo"),
                        "plan_estudios": parsed,
                    })
                    rank = (
                        int(bool(status.get("is_complete"))),
                        float(status.get("total_ects_obtained") or 0.0),
                        int(status.get("total_elementos") or 0),
                    )
                    if best is None or rank > best["rank"]:
                        best = {"rank": rank, "status": status}
                except Exception:
                    errors += 1
            status = best["status"] if best else {}
            results.append({
                "urls_tested": tested,
                "documents_downloaded": downloaded,
                "errors": errors,
                "has_curriculum": bool(status.get("total_elementos")),
                "complete": bool(status.get("is_complete")),
                "completeness": status.get("status"),
                "elements": int(status.get("total_elementos") or 0),
                "ects_obtained": float(status.get("total_ects_obtained") or 0.0),
                "ects_required": float(status.get("required_ects") or 0.0),
            })
    return {
        "probe": "persisted_boe_empirical_probe",
        "cases_selected": len(cases),
        "results": results,
        "summary": {
            "documents_tested": sum(item["urls_tested"] for item in results),
            "documents_downloaded": sum(item["documents_downloaded"] for item in results),
            "cases_with_curriculum": sum(int(item["has_curriculum"]) for item in results),
            "complete_candidates": sum(int(item["complete"]) for item in results),
            "errors": sum(item["errors"] for item in results),
            "completeness": dict(Counter(str(item["completeness"]) for item in results)),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=30)
    parser.add_argument("--max-urls", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run(args.max_cases, args.max_urls)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
