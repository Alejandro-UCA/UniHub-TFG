"""Campaña genérica y reproducible para másteres incompletos."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRAWLER = ROOT / "Codigo" / "Crawler"
if str(CRAWLER) not in sys.path:
    sys.path.insert(0, str(CRAWLER))

from core.checkpoint import load_json_safe
from core.config import find_plan_filepath
from extractors.curriculum_recovery import matches_academic_level
from quality.data_quality import assess_plan_quality
from pipelines.parte2_web_crawler import UniversityWebCrawler
from extractors.web_source_recovery import is_explicitly_historical


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _json_default(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _master_record(record: dict) -> bool:
    return matches_academic_level(record.get("titulo"), record.get("nivel_academico"), "master")


def _bucket(record: dict) -> str:
    quality = record.get("calidad_datos") or {}
    completeness = quality.get("completitud") or "sin_plan"
    source = str(record.get("estado_fuente") or "")
    if "robots" in source:
        return "robots"
    if "web_no_disponible" in source or "fuente_no_disponible" in source:
        return "web_no_disponible"
    if record.get("candidato_plan_estudios") or source == "candidata_no_publicable":
        return "candidato_parcial"
    return completeness


def _evidence_score(record: dict) -> tuple[int, int, int]:
    direct_url = str(record.get("web_fuente_directa_url") or "")
    candidate = record.get("candidato_plan_estudios") or {}
    elements = candidate.get("elementos_curriculares", []) if isinstance(candidate, dict) else []
    return (
        int(bool(direct_url and not is_explicitly_historical(direct_url))),
        int(bool(record.get("web_fuente_directa_url"))),
        len(elements) if isinstance(elements, list) else 0,
    )


def _load_records(university_filter: str = "", degree_filter: str = "") -> tuple[dict, dict]:
    universities = load_json_safe(ROOT / "Codigo" / "Crawler" / "Datos" / "universidades.json", default=[])
    degrees = load_json_safe(ROOT / "Codigo" / "Crawler" / "Datos" / "titulaciones.json", default={})
    university_map = {
        str(item.get("codigo")).zfill(3): item
        for item in universities if isinstance(item, dict) and item.get("codigo")
    }
    all_records = {}
    for path in (ROOT / "Codigo" / "Crawler" / "Datos" / "planes_estudio").rglob("*.json"):
        data = load_json_safe(path, default=None)
        if not isinstance(data, dict) or not _master_record(data):
            continue
        if university_filter and university_filter.casefold() not in str(data.get("universidad_nombre") or "").casefold():
            continue
        if degree_filter and degree_filter.casefold() not in str(data.get("titulo") or "").casefold():
            continue
        quality = assess_plan_quality(data, data.get("origen_fuente"))
        if quality.get("publicable"):
            continue
        code = str(data.get("universidad_codigo") or "").zfill(3)
        if not university_map.get(code, {}).get("web"):
            continue
        all_records[str(path)] = data
    return university_map, all_records


def select_cohort(
    per_bucket: int = 3,
    seed: int = 20260903,
    evidence_first: bool = False,
    university_filter: str = "",
    degree_filter: str = "",
) -> list[dict]:
    university_map, records = _load_records(university_filter, degree_filter)
    grouped = defaultdict(list)
    for path, record in records.items():
        grouped[_bucket(record)].append({"path": path, "record": record})
    if evidence_first:
        candidates = [
            {"path": path, "record": record}
            for path, record in records.items()
            if _evidence_score(record) > (0, 0, 0)
        ]
        candidates.sort(
            key=lambda item: (
                tuple(-value for value in _evidence_score(item["record"])),
                item["record"].get("universidad_nombre", ""),
                item["record"].get("titulo", ""),
            )
        )
        selected = []
        seen_universities = set()
        for item in candidates:
            university = str(item["record"].get("universidad_codigo") or "").zfill(3)
            if university in seen_universities:
                continue
            seen_universities.add(university)
            selected.append(item)
            if len(selected) >= max(1, per_bucket):
                break
        return selected
    rng = random.Random(seed)
    selected = []
    for bucket in sorted(grouped):
        choices = grouped[bucket][:]
        rng.shuffle(choices)
        selected.extend(choices[:per_bucket])
    selected.sort(
        key=lambda item: (
            tuple(-value for value in _evidence_score(item["record"])),
            item["record"].get("universidad_nombre", ""),
            item["record"].get("titulo", ""),
        )
    )
    return selected


def run(
    output: str,
    per_bucket: int = 3,
    max_universities: int | None = None,
    evidence_first: bool = False,
    max_degrees_per_university: int | None = None,
    university_filter: str = "",
    degree_filter: str = "",
) -> dict:
    university_map, records = _load_records(university_filter, degree_filter)
    cohort = select_cohort(
        per_bucket=per_bucket,
        evidence_first=evidence_first,
        university_filter=university_filter,
        degree_filter=degree_filter,
    )
    crawler = UniversityWebCrawler()
    before = {}
    for item in cohort:
        path = Path(item["path"])
        before[str(path)] = {"sha256": _digest(load_json_safe(path, default={})), "record": load_json_safe(path, default={})}

    campaign = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "selection": {"strategy": "estratificacion_por_estado", "per_bucket": per_bucket, "cohort_size": len(cohort)},
        "cohort": [
            {"path": item["path"], "bucket": _bucket(item["record"]), "title": item["record"].get("titulo"), "university": item["record"].get("universidad_nombre")}
            for item in cohort
        ],
        "before": before,
        "runs": [],
    }
    by_university = defaultdict(list)
    for item in cohort:
        by_university[str(item["record"].get("universidad_codigo") or "").zfill(3)].append(item)

    university_groups = list(by_university.items())
    university_groups.sort(
        key=lambda pair: max((_evidence_score(item["record"]) for item in pair[1]), default=(0, 0, 0)),
        reverse=True,
    )
    if max_universities is not None:
        university_groups = university_groups[: max(0, int(max_universities))]
    for code, items in university_groups:
        university = university_map.get(code)
        if not university:
            continue
        if max_degrees_per_university is not None:
            items = items[: max(0, int(max_degrees_per_university))]
            if not items:
                continue
        try:
            result = crawler.process_university_web(
                university,
                {code: {"titulaciones_vigentes": [item["record"] for item in items]}},
                force=False,
            )
            campaign["runs"].append({
                "paths": [item["path"] for item in items],
                "result": {key: value for key, value in result.items() if not str(key).startswith("_")},
            })
        except Exception as exc:
            campaign["runs"].append({"paths": [item["path"] for item in items], "error": f"{type(exc).__name__}: {exc}"})

    modified = []
    recovered = []
    plan_loss = []
    verified_loss = []
    for item in cohort:
        path = Path(item["path"])
        old = before[str(path)]["record"]
        new = load_json_safe(path, default={})
        if _digest(old) != _digest(new):
            modified.append(str(path))
        old_plan = old.get("plan_estudios")
        new_plan = new.get("plan_estudios") if isinstance(new, dict) else None
        old_quality = assess_plan_quality(old, old.get("origen_fuente"))
        new_quality = assess_plan_quality(new, new.get("origen_fuente"))
        if isinstance(old_plan, dict) and not isinstance(new_plan, dict):
            plan_loss.append(str(path))
        if old_quality.get("publicable") and not new_quality.get("publicable"):
            verified_loss.append(str(path))
        if not old_quality.get("publicable") and new_quality.get("publicable"):
            recovered.append({"path": str(path), "title": new.get("titulo"), "source": new.get("web_fuente_directa_url"), "quality": new_quality})

    campaign["finished_at"] = datetime.now(timezone.utc).isoformat()
    campaign["audit"] = {
        "modified_count": len(modified),
        "recovered_count": len(recovered),
        "plan_loss": plan_loss,
        "verified_loss": verified_loss,
        "no_plan_loss": not plan_loss,
        "no_verified_loss": not verified_loss,
        "recovered": recovered,
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        json.dumps(campaign, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(Path(output).resolve()), "cohort": len(cohort), **campaign["audit"]}, ensure_ascii=False, indent=2))
    return campaign


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-bucket", type=int, default=3)
    parser.add_argument("--max-universities", type=int, default=None)
    parser.add_argument("--evidence-first", action="store_true")
    parser.add_argument("--max-degrees-per-university", type=int, default=None)
    parser.add_argument("--university-contains", default="")
    parser.add_argument("--degree-contains", default="")
    args = parser.parse_args()
    run(
        args.output,
        max(1, args.per_bucket),
        args.max_universities,
        args.evidence_first,
        args.max_degrees_per_university,
        args.university_contains,
        args.degree_contains,
    )


if __name__ == "__main__":
    main()
