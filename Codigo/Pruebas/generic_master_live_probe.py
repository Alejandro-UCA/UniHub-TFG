"""Sonda web real, genérica y no destructiva para másteres incompletos."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
CRAWLER = ROOT / "Codigo" / "Crawler"
if str(CRAWLER) not in sys.path:
    sys.path.insert(0, str(CRAWLER))

from core.checkpoint import load_json_safe
from extractors.curriculum_recovery import (
    discover_related_academic_origins,
    generic_curriculum_path_candidates,
    matches_academic_level,
)
from quality.data_quality import assess_plan_quality
from pipelines.parte2_web_crawler import (
    RUCTDownloader,
    ensure_https_url,
    extract_html_subjects,
    infer_declared_total_ects,
    is_html_page_matching_degree,
)
from core.robots_policy import RobotsPolicy


def _records(per_bucket: int) -> list[dict]:
    universities = load_json_safe(ROOT / "Codigo" / "Crawler" / "Datos" / "universidades.json", default=[])
    university_map = {
        str(item.get("codigo")).zfill(3): item
        for item in universities
        if isinstance(item, dict) and item.get("codigo") and item.get("web")
    }
    grouped: dict[str, list[dict]] = {}
    for path in (ROOT / "Codigo" / "Crawler" / "Datos" / "planes_estudio").rglob("*.json"):
        data = load_json_safe(path, default=None)
        if not isinstance(data, dict) or not matches_academic_level(
            data.get("titulo"), data.get("nivel_academico"), "master"
        ):
            continue
        if assess_plan_quality(data, data.get("origen_fuente")).get("publicable"):
            continue
        code = str(data.get("universidad_codigo") or "").zfill(3)
        if code not in university_map:
            continue
        bucket = str(data.get("estado_fuente") or "sin_plan")
        if "robots" in bucket:
            bucket = "robots"
        elif "web_no_disponible" in bucket or "fuente_no_disponible" in bucket:
            bucket = "web_no_disponible"
        elif data.get("candidato_plan_estudios") or bucket == "candidata_no_publicable":
            bucket = "candidato_parcial"
        else:
            bucket = (data.get("calidad_datos") or {}).get("completitud") or "sin_plan"
        grouped.setdefault(bucket, []).append({"path": str(path), "record": data, "university": university_map[code]})

    selected = []
    for bucket in sorted(grouped):
        selected.extend(sorted(grouped[bucket], key=lambda x: x["path"])[: max(1, per_bucket)])
    return selected


def run(output: str, per_bucket: int) -> dict:
    cohort = _records(per_bucket)
    downloader = RUCTDownloader(delay=0.2, timeout=8, phase="fase1_parte2_live_probe")
    robots = RobotsPolicy(timeout=8)
    results = []
    try:
        for item in cohort:
            record = item["record"]
            university = item["university"]
            base_url = ensure_https_url(str(university.get("web") or "").strip())
            result = {
                "path": item["path"],
                "bucket": str(record.get("estado_fuente") or "sin_plan"),
                "title": record.get("titulo"),
                "status": "unresolved",
                "routes_tested": 0,
                "best_elements": 0,
                "declared_total_ects": None,
                "cause": None,
            }
            if not base_url:
                result["cause"] = "no_official_web_registered"
                results.append(result)
                continue
            try:
                allowed, _ = robots.check(base_url)
            except Exception:
                allowed = False
            if not allowed:
                result["cause"] = "robots_or_policy_block"
                results.append(result)
                continue

            route_origins = [base_url]
            try:
                home_html = downloader.fetch_text(base_url)
                home_soup = BeautifulSoup(home_html or "", "html.parser")
                route_origins.extend(discover_related_academic_origins(home_soup, base_url))
            except Exception:
                pass
            route_origins = list(dict.fromkeys(route_origins))
            result["related_origins"] = route_origins[1:]
            candidates = []
            for origin in route_origins:
                if origin != base_url:
                    related_allowed, _ = robots.check(origin)
                    if not related_allowed:
                        continue
                candidates.extend(generic_curriculum_path_candidates(origin, "master")[:16])
            candidates = list(dict.fromkeys(candidates))[:48]
            for url in candidates:
                result["routes_tested"] += 1
                try:
                    raw = downloader.fetch_text(url)
                    if not raw:
                        continue
                    soup = BeautifulSoup(raw, "html.parser")
                    elements = extract_html_subjects(soup, url)
                    result["best_elements"] = max(result["best_elements"], len(elements))
                    if len(elements) < 3 or not is_html_page_matching_degree(
                        soup, record.get("titulo", ""), university.get("nombre", ""), url
                    ):
                        continue
                    result["declared_total_ects"] = infer_declared_total_ects(soup)
                    result["status"] = "recoverable_candidate"
                    result["source_url"] = url
                    break
                except Exception:
                    continue
            if result["status"] == "unresolved":
                result["cause"] = (
                    "routes_without_matching_curriculum"
                    if result["routes_tested"]
                    else "no_generic_routes"
                )
            results.append(result)
    finally:
        downloader.close()

    summary = Counter(item["status"] for item in results)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "cohorte_dinamica_por_estado_y_sonda_de_rutas_genericas",
        "mutating": False,
        "cohort_size": len(cohort),
        "status_counts": dict(summary),
        "cause_counts": dict(Counter(item["cause"] for item in results if item["cause"])),
        "results": results,
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target.resolve()), **payload["status_counts"], "causes": payload["cause_counts"]}, ensure_ascii=False, indent=2))
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-bucket", type=int, default=1)
    args = parser.parse_args()
    run(args.output, max(1, args.per_bucket))


if __name__ == "__main__":
    main()
