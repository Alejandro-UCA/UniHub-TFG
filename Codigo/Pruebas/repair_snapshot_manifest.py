"""Reconstruye metadatos del snapshot sin tocar internet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "Codigo" / "Crawler" / "Datos" / "web_snapshots" / "v204"


def body_for_url(url: str) -> Path | None:
    prefix = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    matches = sorted((SNAPSHOT / "bodies").glob(prefix + ".*"))
    return matches[0] if matches else None


def main() -> None:
    input_manifest = json.loads((SNAPSHOT / "acquisition_input.json").read_text(encoding="utf-8"))
    previous = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    old_by_url = {}
    for entry in previous.get("entries", []):
        old_by_url.setdefault(entry.get("url"), entry)
    entries, missing = [], []
    for url in input_manifest.get("urls", []):
        body = body_for_url(url)
        if body is None:
            missing.append(url)
            continue
        entry = old_by_url.get(url)
        if entry is None:
            suffix = body.suffix.lower()
            content_type = "application/pdf" if suffix == ".pdf" else "text/html; charset=utf-8" if suffix in {".html", ".htm"} else "application/octet-stream"
            content = body.read_bytes()
            entry = {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": content_type,
                "sha256": hashlib.sha256(content).hexdigest(),
                "byte_length": len(content),
                "relative_path": f"bodies/{body.name}",
                "error": "",
            }
        entries.append(entry)
    result = {
        "schema": 1,
        "requested": len(input_manifest.get("urls", [])),
        "downloaded": len(entries),
        "reindexed_without_network": True,
        "errors": previous.get("errors", []),
        "missing_body_for_input": missing,
        "entries": entries,
    }
    (SNAPSHOT / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"requested": result["requested"], "downloaded": result["downloaded"], "missing": len(missing), "errors": len(result["errors"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
