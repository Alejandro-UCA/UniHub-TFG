"""Audita una campaña focalizada: recuperación, no pérdida y no espurios."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

_CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if _CRAWLER_DIR not in sys.path:
    sys.path.insert(0, _CRAWLER_DIR)
from data_quality import assess_plan_quality


TARGET_QUERIES = (
    "antropología social y cultural",
    "fisioterapia",
    "bioinformática",
    "economía, organización y gestión",
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _record_key(record: dict) -> str:
    return "|".join((
        str(record.get("universidad_codigo") or "").zfill(3),
        str(record.get("codigo_estudio") or ""),
    ))


def _is_target(record: dict, target_universities: set[str] | None = None) -> bool:
    if target_universities and str(record.get("universidad_codigo") or "").zfill(3) not in target_universities:
        return False
    title = str(record.get("titulo") or "").casefold()
    return any(query in title for query in TARGET_QUERIES)


def _plan_files(root: str) -> list[Path]:
    return sorted(Path(root, "Codigo", "Crawler", "Datos", "planes_estudio").rglob("*.json"))


def _profile(record: dict) -> dict:
    plan = record.get("plan_estudios")
    quality = assess_plan_quality(record, record.get("origen_fuente"))
    return {
        "key": _record_key(record),
        "title": record.get("titulo"),
        "plan_present": isinstance(plan, dict),
        "plan_elements": len((plan or {}).get("elementos_curriculares", [])) if isinstance(plan, dict) else 0,
        "publicable": bool(quality.get("publicable")),
        "quality_status": record.get("estado_calidad"),
        "source": record.get("web_fuente_directa_url") or record.get("boe_url") or record.get("programa_doctoral"),
    }


def snapshot(root: str, output: str, target_universities: set[str] | None = None) -> dict:
    files = {}
    profiles = {}
    targets = {}
    for path in _plan_files(root):
        rel = str(path.relative_to(root))
        digest = _canonical_digest(path.read_bytes().decode("utf-8"))
        files[rel] = {"sha256": digest, "bytes": path.stat().st_size}
        try:
            record = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        profiles[rel] = _profile(record)
        if _is_target(record, target_universities):
            targets[_record_key(record)] = {
                "path": rel,
                "record": record,
            }
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": os.path.abspath(root),
        "target_universities": sorted(target_universities or []),
        "plan_file_count": len(files),
        "files": files,
        "profiles": profiles,
        "targets": targets,
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def compare(root: str, before_path: str, output: str) -> dict:
    before = _read(Path(before_path))
    after_files = {str(path.relative_to(root)): path for path in _plan_files(root)}
    modified = []
    for rel, old_meta in before.get("files", {}).items():
        path = Path(root, rel)
        if not path.exists():
            modified.append({"path": rel, "change": "removed"})
            continue
        raw = path.read_bytes().decode("utf-8")
        new_meta = {"sha256": _canonical_digest(raw), "bytes": path.stat().st_size}
        if new_meta != old_meta:
            modified.append({"path": rel, "change": "modified", "before": old_meta, "after": new_meta})
    for rel in sorted(set(after_files) - set(before.get("files", {}))):
        modified.append({"path": rel, "change": "added"})

    before_profiles = before.get("profiles", {})
    after_profiles = {}
    for rel, path in after_files.items():
        try:
            after_profiles[rel] = _profile(_read(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    all_plan_loss = []
    all_verified_plan_loss = []
    new_publicable = []
    for rel, old_profile in before_profiles.items():
        new_profile = after_profiles.get(rel)
        if not new_profile:
            continue
        if old_profile.get("plan_present") and not new_profile.get("plan_present"):
            all_plan_loss.append(rel)
        if old_profile.get("publicable") and not new_profile.get("publicable"):
            all_verified_plan_loss.append(rel)
        if not old_profile.get("publicable") and new_profile.get("publicable"):
            new_publicable.append({"path": rel, "profile": new_profile})
    # Una reescritura JSON puede cambiar saltos de línea/indentación sin
    # cambiar datos. La integridad se decide con perfiles semánticos, no con
    # el hash textual, para no confundir formato con pérdida o contaminación.
    semantic_modified = []
    for item in modified:
        rel = item.get("path")
        if before_profiles.get(rel) != after_profiles.get(rel):
            semantic_modified.append(item)
            item["semantic_change"] = True
        else:
            item["semantic_change"] = False
    target_paths = {item.get("path") for item in before.get("targets", {}).values()}
    collateral_modified = [item for item in semantic_modified if item.get("path") not in target_paths]

    target_results = []
    verified_plan_loss = []
    plan_loss = []
    suspicious = []
    for key, item in before.get("targets", {}).items():
        old = item.get("record") or {}
        path = Path(root, item["path"])
        new = _read(path) if path.exists() else None
        old_plan = old.get("plan_estudios")
        new_plan = new.get("plan_estudios") if isinstance(new, dict) else None
        old_quality = assess_plan_quality(old, old.get("origen_fuente"))
        new_quality = assess_plan_quality(new, new.get("origen_fuente")) if isinstance(new, dict) else {"publicable": False}
        if isinstance(old_plan, dict) and not isinstance(new_plan, dict):
            plan_loss.append(key)
        if old_quality.get("publicable") and not new_quality.get("publicable"):
            verified_plan_loss.append(key)
        if isinstance(new_plan, dict) and new_quality.get("publicable") and not (
            new.get("boe_url") or new.get("web_fuente_directa_url") or new.get("programa_doctoral")
        ):
            suspicious.append({"key": key, "reason": "plan_publicable_sin_fuente_trazable"})
        target_results.append({
            "key": key,
            "title": new.get("titulo") if isinstance(new, dict) else old.get("titulo"),
            "before_quality": old_quality,
            "after_quality": new_quality,
            "before_plan_elements": len((old_plan or {}).get("elementos_curriculares", [])) if isinstance(old_plan, dict) else 0,
            "after_plan_elements": len((new_plan or {}).get("elementos_curriculares", [])) if isinstance(new_plan, dict) else 0,
            "after_source": (new or {}).get("web_fuente_directa_url") if isinstance(new, dict) else None,
            "after_quality_status": (new or {}).get("estado_calidad") if isinstance(new, dict) else None,
        })

    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": os.path.abspath(root),
        "before": os.path.abspath(before_path),
        "plan_files_before": before.get("plan_file_count", 0),
        "plan_files_after": len(after_files),
        "modified_plan_files": modified,
        "semantic_modified_plan_files": semantic_modified,
        "collateral_modified_plan_files": collateral_modified,
        "all_plan_loss": all_plan_loss,
        "all_verified_plan_loss": all_verified_plan_loss,
        "new_publicable_records": new_publicable,
        "target_results": target_results,
        "recovered_target_count": sum(1 for row in target_results if row["after_quality"].get("publicable")),
        "plan_loss": plan_loss,
        "verified_plan_loss": verified_plan_loss,
        "suspicious_records": suspicious,
        "no_original_plan_loss": not all_plan_loss and not plan_loss,
        "no_verified_plan_loss": not all_verified_plan_loss and not verified_plan_loss,
        "no_spurious_publication": not suspicious,
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--compare")
    parser.add_argument("--output", required=True)
    parser.add_argument("--universities", nargs="*")
    args = parser.parse_args(argv)
    targets = {str(value).zfill(3) for value in (args.universities or [])}
    if args.snapshot:
        result = snapshot(args.root, args.output, targets or None)
    elif args.compare:
        result = compare(args.root, args.compare, args.output)
    else:
        parser.error("Se requiere --snapshot o --compare")
    print(json.dumps({
        "output": os.path.abspath(args.output),
        "plan_file_count": result.get("plan_file_count", result.get("plan_files_after")),
        "target_count": len(result.get("targets", result.get("target_results", []))),
        "modified_plan_files": len(result.get("modified_plan_files", [])),
        "all_plan_loss": len(result.get("all_plan_loss", [])),
        "all_verified_plan_loss": len(result.get("all_verified_plan_loss", [])),
        "new_publicable_records": len(result.get("new_publicable_records", [])),
        "recovered_target_count": result.get("recovered_target_count"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
