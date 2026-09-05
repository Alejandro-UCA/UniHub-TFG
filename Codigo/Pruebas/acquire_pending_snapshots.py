"""Adquiere una vez el corpus oficial candidato para la campaña aislada."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from in_memory_web_snapshot import acquire_snapshot


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Codigo" / "Crawler" / "Datos"
RECORDS = DATA / "planes_estudio"
SNAPSHOT_DIR = DATA / "web_snapshots" / "v204"


def normalize_web_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlsplit(value)
    if not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def pending_records() -> list[dict]:
    result = []
    for path in RECORDS.glob("*/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        quality = record.get("calidad_datos") or {}
        if record.get("plan_estudios") is None or not quality.get("publicable"):
            result.append(record)
    return result


def main() -> None:
    records = pending_records()
    direct_urls = {
        normalize_web_url(record.get("web_fuente_directa_url"))
        for record in records
    }
    institutional_urls = {
        normalize_web_url(record.get("web"))
        for record in records
    }
    urls = sorted(url for url in direct_urls | institutional_urls if url)
    input_manifest = {
        "schema": 1,
        "scope": "titulaciones pendientes del piloto",
        "pending_records": len(records),
        "pending_universities": len({record.get("universidad_nombre") for record in records}),
        "unique_direct_or_institutional_urls": len(urls),
        "direct_urls": len({normalize_web_url(record.get("web_fuente_directa_url")) for record in records if normalize_web_url(record.get("web_fuente_directa_url"))}),
        "urls": urls,
    }
    input_path = SNAPSHOT_DIR / "acquisition_input.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps(input_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result = acquire_snapshot(
        urls,
        SNAPSHOT_DIR,
        timeout=20.0,
        max_bytes=25_000_000,
        per_host_delay=0.20,
    )
    result["input_manifest"] = str(input_path)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
