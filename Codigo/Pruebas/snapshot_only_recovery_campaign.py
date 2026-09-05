"""Audita parsers contra el snapshot cargado en memoria, sin red."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Codigo" / "Crawler"))
from boe_pdf_parser import parse_boe_pdf  # noqa: E402
from fase1_parte2_web_crawler import extract_html_subjects  # noqa: E402
from in_memory_web_snapshot import InMemoryWebSnapshot, SnapshotMiss, assert_snapshot_only  # noqa: E402


DATA = ROOT / "Codigo" / "Crawler" / "Datos"
SNAPSHOT_DIR = DATA / "web_snapshots" / "v204"
OUTPUT = DATA / "audits" / "snapshot_only_recovery_v204.json"


def pending_titles_by_url() -> dict[str, list[dict]]:
    result = defaultdict(list)
    for path in (DATA / "planes_estudio").glob("*/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        quality = record.get("calidad_datos") or {}
        if record.get("plan_estudios") is None or not quality.get("publicable"):
            url = str(record.get("web_fuente_directa_url") or record.get("web") or "").strip()
            if url:
                result[url.rstrip("/")].append({
                    "university": record.get("universidad_nombre") or "",
                    "title": record.get("titulo") or "",
                })
    return result


def main() -> None:
    snapshot = InMemoryWebSnapshot().load_directory(SNAPSHOT_DIR)
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
    candidates = pending_titles_by_url()
    counts = Counter()
    errors = []
    samples = []
    for raw in manifest.get("entries", []):
        url = str(raw.get("url") or "").strip()
        try:
            entry, body = snapshot.get(url)
        except SnapshotMiss:
            counts["manifest_entry_not_loaded"] += 1
            continue
        if not 200 <= int(entry.status_code) < 300:
            counts["http_non_2xx_skipped"] += 1
            continue
        content_type = (entry.content_type or "").split(";", 1)[0].casefold()
        try:
            if content_type == "application/pdf" or url.casefold().endswith(".pdf"):
                parsed = parse_boe_pdf(body, target_title="", univ_name="")
                element_count = len(parsed.get("elementos_curriculares") or [])
                counts["pdf_processed"] += 1
                counts["pdf_with_elements"] += bool(element_count)
            elif content_type == "text/html" or "html" in content_type:
                soup = BeautifulSoup(body, "html.parser")
                elements = extract_html_subjects(soup, url)
                element_count = len(elements)
                counts["html_processed"] += 1
                counts["html_with_elements"] += bool(element_count)
            else:
                counts["other_processed"] += 1
                element_count = 0
            counts["elements_detected"] += element_count
            if element_count and len(samples) < 50:
                samples.append({
                    "url": url,
                    "content_type": content_type,
                    "elements": element_count,
                    "pending_titles_on_url": candidates.get(url.rstrip("/"), [])[:5],
                })
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)[:500]})
    assert_snapshot_only(snapshot)
    result = {
        "schema": 1,
        "mode": "snapshot_only",
        "network_calls": snapshot.network_calls,
        "manifest_requested": manifest.get("requested"),
        "manifest_downloaded": manifest.get("downloaded"),
        "loaded_aliases": len(snapshot.urls),
        "counts": dict(counts),
        "parser_errors": errors[:200],
        "parser_error_count": len(errors),
        "samples": samples,
        "acquisition_errors": manifest.get("errors", []),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "network_calls": result["network_calls"],
        "downloaded": result["manifest_downloaded"],
        "loaded_aliases": result["loaded_aliases"],
        "counts": result["counts"],
        "parser_error_count": result["parser_error_count"],
        "acquisition_error_count": len(result["acquisition_errors"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
