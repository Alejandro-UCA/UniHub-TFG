"""Audita candidatos pendientes contra un snapshot web, sin red ni escrituras de datos.

El objetivo de este módulo es medir la capacidad real de recuperación antes de
integrarla en una campaña. Cada candidato se evalúa con los parsers y las
reglas de calidad del piloto, pero ningún JSON de ``planes_estudio`` se modifica.
"""

from __future__ import annotations

import gc
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urldefrag, urlsplit, urlunsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Codigo" / "Crawler"))
sys.path.insert(0, str(ROOT / "Codigo" / "Pruebas"))

from boe_pdf_parser import parse_boe_pdf  # noqa: E402
from curriculum_recovery import infer_declared_total_ects  # noqa: E402
from data_quality import assess_plan_quality  # noqa: E402
from fase1_parte2_web_crawler import (  # noqa: E402
    build_html_curriculum_payload,
    extract_html_subjects,
    is_html_page_matching_degree,
    is_source_url_level_compatible,
)
from in_memory_web_snapshot import InMemoryWebSnapshot, SnapshotMiss, assert_snapshot_only  # noqa: E402


DATA = ROOT / "Codigo" / "Crawler" / "Datos"
SNAPSHOT_DIR = DATA / "web_snapshots" / "v204"
OUTPUT = DATA / "audits" / "snapshot_candidate_audit_v210.json"
SUMMARY_OUTPUT = ROOT / "Documentacion" / "AUDITORIA_CANDIDATOS_SNAPSHOT_v210.md"


def _canonical_candidate_url(value: object) -> str:
    clean, _ = urldefrag(str(value or "").strip())
    parts = urlsplit(clean)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, "")).rstrip("/")


def _source_type(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    return "boe" if host == "boe.es" or host.endswith(".boe.es") else "web_oficial_universidad"


def _pending_candidates() -> tuple[list[dict], Counter]:
    """Carga candidatos sin exponer ni persistir identificadores internos."""
    records = []
    counts = Counter()
    for path in sorted((DATA / "planes_estudio").glob("*/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            counts["record_read_error"] += 1
            continue
        quality = record.get("calidad_datos") or {}
        if record.get("plan_estudios") is not None and quality.get("publicable"):
            counts["already_publicable_skipped"] += 1
            continue
        direct = _canonical_candidate_url(record.get("web_fuente_directa_url"))
        fallback = _canonical_candidate_url(record.get("web"))
        url = direct or fallback
        if not url:
            counts["pending_without_candidate_url"] += 1
            continue
        records.append({
            "university": str(record.get("universidad_nombre") or "").strip(),
            "title": str(record.get("titulo") or "").strip(),
            "academic_level": str(record.get("nivel_academico") or "").strip(),
            "url": url,
            "url_kind": "direct" if direct else "fallback",
            "codigo_estudio": record.get("codigo_estudio"),
        })
        counts["pending_with_candidate_url"] += 1
        counts[f"candidate_{'direct' if direct else 'fallback'}"] += 1
    return records, counts


def _base_payload(candidate: dict, plan: dict) -> dict:
    """Monta el payload realista que recibiría la evaluación de calidad."""
    return {
        "codigo_estudio": candidate.get("codigo_estudio"),
        "titulo": candidate.get("title", ""),
        "nivel_academico": candidate.get("academic_level", ""),
        "universidad_nombre": candidate.get("university", ""),
        "web_fuente_directa_url": candidate.get("url", ""),
        "origen_fuente": _source_type(candidate.get("url", "")),
        "plan_estudios": plan,
    }


def _quality_result(candidate: dict, plan: dict) -> dict:
    payload = _base_payload(candidate, plan)
    assessment = assess_plan_quality(payload, payload["origen_fuente"])
    return {
        "assessment": assessment,
        "element_count": len(plan.get("elementos_curriculares") or []) if isinstance(plan, dict) else 0,
        "plan_total_ects": plan.get("total_creditos_extraidos") if isinstance(plan, dict) else None,
    }


def _html_candidate(
    candidate: dict,
    soup: BeautifulSoup,
    url: str,
    *,
    extracted_elements: list[dict] | None = None,
    declared_total: float | None = None,
) -> dict:
    level_compatible = is_source_url_level_compatible(url, candidate["academic_level"])
    if not level_compatible:
        return {
            "outcome": "source_level_mismatch",
            "identity": {"strict": False, "url_assisted": False},
            "element_count": 0,
        }

    strict = is_html_page_matching_degree(
        soup, candidate["title"], candidate["university"], url,
        allow_curriculum_url_identity=False,
    )
    assisted = False
    if not strict:
        assisted = is_html_page_matching_degree(
            soup, candidate["title"], candidate["university"], url,
            allow_curriculum_url_identity=True,
        )
    if not strict and not assisted:
        return {
            "outcome": "identity_rejected",
            "identity": {"strict": False, "url_assisted": False},
            "element_count": 0,
        }

    elements = extracted_elements if extracted_elements is not None else extract_html_subjects(soup, url)
    if declared_total is None:
        declared_total = infer_declared_total_ects(soup)
    plan = build_html_curriculum_payload(elements, candidate["title"], declared_total)
    quality = _quality_result(candidate, plan)
    assessment = quality["assessment"]
    if assessment.get("publicable"):
        outcome = "recoverable_publicable"
    elif quality["element_count"] == 0:
        outcome = "identity_match_without_elements"
    else:
        outcome = "extracted_but_not_publicable"
    return {
        "outcome": outcome,
        "identity": {"strict": bool(strict), "url_assisted": bool(assisted)},
        "declared_total_ects": declared_total,
        "element_count": quality["element_count"],
        "assessment": assessment,
    }


def _pdf_candidate(candidate: dict, body: bytes, url: str) -> dict:
    parsed = parse_boe_pdf(
        body,
        target_title=candidate["title"],
        univ_name=candidate["university"],
    )
    quality = _quality_result(candidate, parsed)
    assessment = quality["assessment"]
    if assessment.get("publicable"):
        outcome = "recoverable_publicable"
    elif quality["element_count"] == 0:
        outcome = "pdf_without_elements"
    else:
        outcome = "extracted_but_not_publicable"
    return {
        "outcome": outcome,
        "element_count": quality["element_count"],
        "assessment": assessment,
        "document_has_any_curriculum": bool(parsed.get("document_has_any_curriculum")),
    }


def _results_for_url(snapshot: InMemoryWebSnapshot, url: str, candidates: list[dict]) -> list[dict]:
    """Procesa una respuesta una vez y la evalúa para todos sus destinatarios."""
    base = {
        "url": url,
    }
    try:
        entry, body = snapshot.get(url)
    except SnapshotMiss:
        return [
            {**base, "university": item["university"], "title": item["title"], "academic_level": item["academic_level"], "url_kind": item["url_kind"], "outcome": "snapshot_miss"}
            for item in candidates
        ]
    response_metadata = {
        "status_code": int(entry.status_code),
        "content_type": (entry.content_type or "").split(";", 1)[0].casefold(),
        "snapshot_final_url": entry.final_url or entry.url,
    }
    if not 200 <= int(entry.status_code) < 300:
        return [
            {**base, **response_metadata, "university": item["university"], "title": item["title"], "academic_level": item["academic_level"], "url_kind": item["url_kind"], "outcome": "http_non_2xx"}
            for item in candidates
        ]

    content_type = response_metadata["content_type"]
    results = []
    try:
        if content_type == "application/pdf" or url.casefold().endswith((".pdf", ".pdf.gz")):
            parsed_by_title = {}
            for candidate in candidates:
                cache_key = (candidate["title"], candidate["university"])
                if cache_key not in parsed_by_title:
                    parsed_by_title[cache_key] = parse_boe_pdf(
                        body,
                        target_title=candidate["title"],
                        univ_name=candidate["university"],
                    )
                parsed = parsed_by_title[cache_key]
                quality = _quality_result(candidate, parsed)
                assessment = quality["assessment"]
                outcome = (
                    "recoverable_publicable" if assessment.get("publicable")
                    else "pdf_without_elements" if quality["element_count"] == 0
                    else "extracted_but_not_publicable"
                )
                results.append({
                    **base, **response_metadata,
                    "university": candidate["university"], "title": candidate["title"],
                    "academic_level": candidate["academic_level"], "url_kind": candidate["url_kind"],
                    "outcome": outcome, "element_count": quality["element_count"],
                    "assessment": assessment,
                    "document_has_any_curriculum": bool(parsed.get("document_has_any_curriculum")),
                })
        elif content_type == "text/html" or "html" in content_type:
            soup = BeautifulSoup(body, "html.parser")
            extracted_elements = extract_html_subjects(soup, url)
            declared_total = infer_declared_total_ects(soup)
            for candidate in candidates:
                result = _html_candidate(
                    candidate, soup, url,
                    extracted_elements=extracted_elements,
                    declared_total=declared_total,
                )
                results.append({
                    **base, **response_metadata,
                    "university": candidate["university"], "title": candidate["title"],
                    "academic_level": candidate["academic_level"], "url_kind": candidate["url_kind"],
                    **result,
                })
        else:
            results = [
                {**base, **response_metadata, "university": item["university"], "title": item["title"], "academic_level": item["academic_level"], "url_kind": item["url_kind"], "outcome": "unsupported_content_type", "element_count": 0}
                for item in candidates
            ]
    except Exception as exc:  # pragma: no cover - defensive audit boundary
        results = [
            {**base, **response_metadata, "university": item["university"], "title": item["title"], "academic_level": item["academic_level"], "url_kind": item["url_kind"], "outcome": "parser_error", "element_count": 0, "error": str(exc)[:500]}
            for item in candidates
        ]
    finally:
        gc.collect()
    return results


def _write_summary(result: dict) -> None:
    counts = result["counts"]
    recoverable = [item for item in result["candidates"] if item.get("outcome") == "recoverable_publicable"]
    by_level = Counter(item.get("academic_level") or "sin nivel" for item in recoverable)
    lines = [
        "# Auditoría de candidatos contra snapshot v204",
        "",
        "Auditoría dry-run: procesa únicamente bytes del snapshot y no modifica registros del piloto.",
        "",
        f"- Candidatos pendientes evaluados: {result['candidate_count']}",
        f"- URLs únicas: {result['unique_candidate_urls']}",
        f"- URLs no presentes en snapshot: {counts.get('snapshot_miss', 0)}",
        f"- Respuestas no 2xx descartadas: {counts.get('http_non_2xx', 0)}",
        f"- Identidades rechazadas: {counts.get('identity_rejected', 0)}",
        f"- Candidatos con datos extraídos pero no publicables: {counts.get('extracted_but_not_publicable', 0)}",
        f"- Candidatos recuperables y publicables: {len(recoverable)}",
        f"- Llamadas de red durante el procesamiento: {result['network_calls']}",
        "",
        "## Recuperables por nivel académico",
        "",
    ]
    if by_level:
        lines.extend(f"- {level}: {count}" for level, count in sorted(by_level.items()))
    else:
        lines.append("- Ninguno en este corpus.")
    lines.extend([
        "",
        "La etiqueta ‘recuperable y publicable’ significa que identidad, procedencia y completitud superan las reglas actuales; no implica todavía escritura ni promoción automática.",
        "",
        "## Muestra de candidatos recuperables",
        "",
    ])
    for item in recoverable[:100]:
        lines.append(f"- {item.get('university') or 'Universidad no indicada'} — {item.get('title') or 'Titulación no indicada'} ({item.get('academic_level') or 'nivel no indicado'}): {item.get('element_count', 0)} elementos")
    SUMMARY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    snapshot = InMemoryWebSnapshot().load_directory(SNAPSHOT_DIR)
    candidates, input_counts = _pending_candidates()
    grouped = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["url"]].append(candidate)

    results = []
    counts = Counter()
    for url in sorted(grouped):
        for item in _results_for_url(snapshot, url, grouped[url]):
            results.append(item)
            counts[item["outcome"]] += 1

    assert_snapshot_only(snapshot)
    result = {
        "schema": 1,
        "mode": "snapshot_only_candidate_dry_run",
        "snapshot": str(SNAPSHOT_DIR),
        "network_calls": snapshot.network_calls,
        "loaded_aliases": len(snapshot.urls),
        "candidate_count": len(results),
        "unique_candidate_urls": len(grouped),
        "input_counts": dict(input_counts),
        "counts": dict(counts),
        "candidates": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary(result)
    print(json.dumps({
        "output": str(OUTPUT),
        "summary": str(SUMMARY_OUTPUT),
        "candidate_count": result["candidate_count"],
        "unique_candidate_urls": result["unique_candidate_urls"],
        "network_calls": result["network_calls"],
        "counts": result["counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
