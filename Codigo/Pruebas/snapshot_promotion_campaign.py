"""Promueve candidatos verificados desde un snapshot local, con auditoría transaccional.

La campaña no realiza peticiones web. Solo considera candidatos previamente
clasificados como publicables por ``snapshot_candidate_audit`` y vuelve a
ejecutar el parser antes de escribir. Los planes verificados quedan protegidos.
Un parcial sólo se sustituye por evidencia validada, archivando el JSON original.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from urllib.parse import urldefrag, urlsplit, urlunsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Codigo" / "Crawler"))
sys.path.insert(0, str(ROOT / "Codigo" / "Pruebas"))

from parsers.boe_pdf import parse_boe_pdf  # noqa: E402
from extractors.curriculum_recovery import infer_declared_total_ects  # noqa: E402
from quality.data_quality import apply_plan_quality, assess_plan_quality  # noqa: E402
from utils.degree_persistence import _stable_degree_snapshot_hash  # noqa: E402
from quality.payload_contract import validate_degree_payload  # noqa: E402
from quality.curriculum_validator import is_doctorate_program  # noqa: E402
from pipelines.parte2_web_crawler import (  # noqa: E402
    build_html_curriculum_payload,
    extract_html_subjects,
    is_html_page_matching_degree,
    is_source_url_level_compatible,
    extract_doctoral_lines_from_soup,
)
from in_memory_web_snapshot import InMemoryWebSnapshot, SnapshotMiss, assert_snapshot_only  # noqa: E402


DATA = ROOT / "Codigo" / "Crawler" / "Datos"
PLAN_DIR = DATA / "planes_estudio"
SNAPSHOT_DIR = DATA / "web_snapshots" / "v204"
DRY_RUN_AUDIT = DATA / "audits" / "snapshot_candidate_audit_v208.json"
OUTPUT = DATA / "audits" / "snapshot_promotion_v209.json"
BACKUP_DIR = DATA / "history" / "snapshot_promotion_v209"


def _url(value: object) -> str:
    clean, _ = urldefrag(str(value or "").strip())
    parts = urlsplit(clean)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, "")).rstrip("/")


def _source_type(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    return "boe" if host == "boe.es" or host.endswith(".boe.es") else "web_oficial_universidad"


def _dataset_hashes() -> dict[str, str]:
    result = {}
    for path in sorted(PLAN_DIR.glob("*/*.json")):
        result[str(path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _index_records() -> dict[tuple[str, str, str], list[tuple[Path, dict]]]:
    index = {}
    for path in sorted(PLAN_DIR.glob("*/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        candidate_url = _url(record.get("web_fuente_directa_url") or record.get("web"))
        key = (
            str(record.get("universidad_nombre") or "").strip(),
            str(record.get("titulo") or "").strip(),
            candidate_url,
        )
        index.setdefault(key, []).append((path, record))
    return index


def _candidate_plan(candidate: dict, entry, body: bytes) -> tuple[dict | None, dict]:
    """Repite la extracción del dry-run y devuelve plan más diagnóstico."""
    url = candidate["url"]
    content_type = (entry.content_type or "").split(";", 1)[0].casefold()
    if not 200 <= int(entry.status_code) < 300:
        return None, {"outcome": "http_non_2xx"}
    if content_type == "application/pdf" or url.casefold().endswith((".pdf", ".pdf.gz")):
        plan = parse_boe_pdf(body, target_title=candidate["title"], univ_name=candidate["university"])
        kind = "pdf"
    elif content_type == "text/html" or "html" in content_type:
        soup = BeautifulSoup(body, "html.parser")
        if not is_source_url_level_compatible(url, candidate["academic_level"]):
            return None, {"outcome": "source_level_mismatch"}
        strict = is_html_page_matching_degree(soup, candidate["title"], candidate["university"], url, allow_curriculum_url_identity=False)
        assisted = False if strict else is_html_page_matching_degree(soup, candidate["title"], candidate["university"], url, allow_curriculum_url_identity=True)
        if not strict and not assisted:
            return None, {"outcome": "identity_rejected"}
        if is_doctorate_program(candidate["academic_level"], candidate["title"]):
            lines = extract_doctoral_lines_from_soup(soup, url)
            if len(lines) < 2:
                return None, {"outcome": "doctorate_without_research_lines"}
            plan = {
                "nombre_plan": candidate["title"],
                "tipo_estructura": "programa_doctorado_investigacion",
                "elementos_curriculares": [
                    {"nombre_elemento": line, "caracter": "INVESTIGACION", "creditos_ects": None}
                    for line in lines
                ],
            }
        else:
            elements = extract_html_subjects(soup, url)
            plan = build_html_curriculum_payload(elements, candidate["title"], infer_declared_total_ects(soup))
        kind = "html"
    else:
        return None, {"outcome": "unsupported_content_type"}

    payload = {
        "codigo_estudio": candidate.get("codigo_estudio"),
        "titulo": candidate["title"],
        "nivel_academico": candidate["academic_level"],
        "universidad_nombre": candidate["university"],
        "web_fuente_directa_url": url,
        "origen_fuente": _source_type(url),
        "plan_estudios": plan,
    }
    assessment = assess_plan_quality(payload, payload["origen_fuente"])
    return plan, {
        "outcome": "recoverable_publicable" if assessment.get("publicable") else "revalidation_failed",
        "content_kind": kind,
        "element_count": len(plan.get("elementos_curriculares") or []) if isinstance(plan, dict) else 0,
        "assessment": assessment,
    }


def _write_atomic(path: Path, record: dict) -> None:
    temporary = path.with_name(path.name + ".snapshot.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _protect_existing_plan(record: dict) -> bool:
    """Protege tanto la verificación persistida como la reevaluación actual."""
    return bool(
        (record.get("calidad_datos") or {}).get("publicable")
        or assess_plan_quality(record, record.get("origen_fuente")).get("publicable")
    )


def main() -> None:
    dry_run = json.loads(DRY_RUN_AUDIT.read_text(encoding="utf-8"))
    approved = [item for item in dry_run.get("candidates", []) if item.get("outcome") == "recoverable_publicable"]
    snapshot = InMemoryWebSnapshot().load_directory(SNAPSHOT_DIR)
    records = _index_records()
    before_hashes = _dataset_hashes()
    counts = Counter()
    changes = []
    errors = []

    for item in approved:
        key = (item.get("university", ""), item.get("title", ""), _url(item.get("url")))
        matches = records.get(key, [])
        if len(matches) != 1:
            counts["record_match_ambiguous_or_missing"] += 1
            errors.append({"university": key[0], "title": key[1], "url": key[2], "reason": "registro_ambiguo_o_ausente"})
            continue
        path, original = matches[0]
        current_plan = original.get("plan_estudios")
        current_has_detail = isinstance(current_plan, dict) and bool(current_plan.get("elementos_curriculares"))
        if _protect_existing_plan(original):
            counts["protected_existing_verified"] += 1
            continue
        candidate = {
            "university": key[0],
            "title": key[1],
            "academic_level": item.get("academic_level", ""),
            "url": key[2],
            "codigo_estudio": original.get("codigo_estudio"),
        }
        try:
            entry, body = snapshot.get(candidate["url"])
            plan, diagnostic = _candidate_plan(candidate, entry, body)
            if diagnostic.get("outcome") != "recoverable_publicable" or not isinstance(plan, dict):
                counts[diagnostic.get("outcome", "revalidation_failed")] += 1
                errors.append({"university": key[0], "title": key[1], "url": key[2], "reason": diagnostic.get("outcome"), "assessment": diagnostic.get("assessment")})
                continue
            updated = deepcopy(original)
            updated["web_fuente_directa_url"] = candidate["url"]
            updated["origen_fuente"] = _source_type(candidate["url"])
            assessment = apply_plan_quality(updated, plan, updated["origen_fuente"])
            if not assessment.get("publicable"):
                counts["promotion_quality_guard"] += 1
                errors.append({"university": key[0], "title": key[1], "url": key[2], "reason": "quality_guard", "assessment": assessment})
                continue
            updated["contrato_datos"] = validate_degree_payload(updated)
            if not updated["contrato_datos"]["valid"]:
                counts["promotion_contract_guard"] += 1
                continue
            backup_path = BACKUP_DIR / path.relative_to(PLAN_DIR)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            if backup_path.exists() and backup_path.read_bytes() != path.read_bytes():
                counts["backup_conflict"] += 1
                continue
            if not backup_path.exists():
                shutil.copy2(path, backup_path)
            updated["previous_snapshot"] = str(backup_path)
            updated["snapshot_recovery"] = {
                "source_sha256": entry.sha256,
                "source_url": entry.final_url or entry.url,
                "snapshot_directory": str(SNAPSHOT_DIR),
            }
            updated["snapshot_hash"] = _stable_degree_snapshot_hash(updated)
            _write_atomic(path, updated)
            counts["promoted"] += 1
            changes.append({
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "university": key[0],
                "title": key[1],
                "url": key[2],
                "before_sha256": before_hashes.get(str(path.relative_to(ROOT)).replace("\\", "/")),
                "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "before_element_count": len(current_plan.get("elementos_curriculares") or []) if current_has_detail else 0,
                "after_element_count": len((updated.get("plan_estudios") or {}).get("elementos_curriculares") or []),
                "quality_state": assessment.get("estado"),
            })
        except SnapshotMiss:
            counts["snapshot_miss_on_revalidation"] += 1
            errors.append({"university": key[0], "title": key[1], "url": key[2], "reason": "snapshot_miss"})
        except Exception as exc:  # pragma: no cover - campaign boundary
            counts["campaign_error"] += 1
            errors.append({"university": key[0], "title": key[1], "url": key[2], "reason": str(exc)[:500]})

    assert_snapshot_only(snapshot)
    after_hashes = _dataset_hashes()
    all_paths = set(before_hashes) | set(after_hashes)
    unchanged = [path for path in all_paths if path not in {item["file"] for item in changes} and before_hashes.get(path) == after_hashes.get(path)]
    missing = sorted(set(before_hashes) - set(after_hashes))
    created = sorted(set(after_hashes) - set(before_hashes))
    result = {
        "schema": 1,
        "mode": "snapshot_only_transactional_promotion",
        "snapshot": str(SNAPSHOT_DIR),
        "network_calls": snapshot.network_calls,
        "approved_by_dry_run": len(approved),
        "counts": dict(counts),
        "changes": changes,
        "errors": errors,
        "integrity": {
            "plan_files_before": len(before_hashes),
            "plan_files_after": len(after_hashes),
            "missing_files": missing,
            "unexpected_created_files": created,
            "unmodified_files_preserved": len(unchanged) == len(all_paths) - len(changes),
            "unmodified_file_count": len(unchanged),
            "backup_count": sum(1 for _ in BACKUP_DIR.glob("*/*.json")) if BACKUP_DIR.exists() else 0,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "network_calls": result["network_calls"],
        "approved_by_dry_run": result["approved_by_dry_run"],
        "counts": result["counts"],
        "integrity": result["integrity"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
