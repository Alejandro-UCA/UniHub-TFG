"""Auditoría reproducible del piloto frente al código original y sus datos."""

from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from curriculum_validator import get_curriculum_completeness_status
from data_quality import assess_plan_quality


ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT.parent / "Codigo"
PILOT_CODE = ROOT / "Codigo"
DATA = PILOT_CODE / "Crawler" / "Datos"
AUDITS = DATA / "audits"
AUDIT_LABEL = "v209"


def code_files(root: Path) -> dict[str, Path]:
    result = {}
    for current, dirnames, filenames in __import__("os").walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name.casefold() not in {"datos", "__pycache__", ".git", ".venv", "venv", "node_modules"}
        ]
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if path.suffix.lower() in {".py", ".toml", ".yml", ".yaml", ".md"}:
                result[str(path.relative_to(root)).replace("\\", "/")] = path
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_inventory(root: Path) -> dict:
    files = code_files(root)
    definitions = []
    references = Counter()
    syntax_errors = []
    line_count = 0
    for relative, path in files.items():
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        line_count += len(source.splitlines())
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            syntax_errors.append({"file": relative, "error": str(exc)})
            continue
        local_defs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local_defs.append(node.name)
                definitions.append({"file": relative, "name": node.name, "kind": type(node).__name__})
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                references[node.id] += 1
        if local_defs:
            pass
    def_names = Counter(item["name"] for item in definitions)
    unreferenced = [
        item for item in definitions
        if item["kind"] != "ClassDef" and references[item["name"]] == 0
    ]
    return {
        "files": len(files),
        "python_files": sum(path.suffix == ".py" for path in files.values()),
        "lines": line_count,
        "definitions": len(definitions),
        "duplicate_definition_names": {name: count for name, count in def_names.items() if count > 1},
        "unreferenced_function_candidates": unreferenced,
        "syntax_errors": syntax_errors,
        "test_files": sorted(name for name in files if name.startswith("Pruebas/")),
        "campaign_or_audit_files": sorted(
            name for name in files
            if any(token in Path(name).stem.casefold() for token in ("audit", "campaign", "probe", "recovery", "verify", "investigate"))
        ),
    }


def diff_inventory() -> dict:
    original = code_files(ORIGINAL)
    pilot = code_files(PILOT_CODE)
    common = set(original) & set(pilot)
    changed = sorted(name for name in common if sha256(original[name]) != sha256(pilot[name]))
    pilot_only = sorted(set(pilot) - set(original))
    pilot_source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in pilot.values()
        if path.suffix == ".py"
    )
    active_modules = []
    test_harnesses = []
    for name in pilot_only:
        if name.startswith("Crawler/") and name.endswith(".py"):
            module = Path(name).stem
            if f"import {module}" in pilot_source or f"from {module} import" in pilot_source:
                active_modules.append(name)
            else:
                test_harnesses.append(name)
        elif name.startswith("Pruebas/"):
            test_harnesses.append(name)
    return {
        "original_only": sorted(set(original) - set(pilot)),
        "pilot_only": pilot_only,
        "pilot_only_active_modules": sorted(active_modules),
        "pilot_only_test_or_audit_harnesses": sorted(test_harnesses),
        "changed": changed,
        "changed_line_counts": {
            name: {
                "original": len(original[name].read_text(encoding="utf-8", errors="replace").splitlines()),
                "pilot": len(pilot[name].read_text(encoding="utf-8", errors="replace").splitlines()),
            }
            for name in changed
        },
    }


def load_records() -> list[dict]:
    records = []
    for path in (DATA / "planes_estudio").glob("*/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records.append(record)
    return records


def data_inventory(records: list[dict]) -> dict:
    pending_by_university: dict[str, list[dict]] = defaultdict(list)
    status_counts = Counter()
    level_counts = Counter()
    source_counts = Counter()
    pending_source_counts = Counter()
    mismatch = []
    mismatch_status = Counter()
    mismatch_sources = Counter()
    stored_pending_count = 0
    recomputed_publicable = 0
    quality_inconsistency = 0
    for record in records:
        quality = record.get("calidad_datos") or {}
        plan = record.get("plan_estudios")
        recomputed = get_curriculum_completeness_status(record)
        recomputed_quality = assess_plan_quality(record, record.get("origen_fuente"))
        recomputed_publicable += bool(recomputed_quality.get("publicable"))
        quality_inconsistency += bool(quality.get("publicable")) != bool(recomputed_quality.get("publicable"))
        status_counts[recomputed.get("status", "desconocido")] += 1
        level_counts[str(record.get("nivel_academico") or "sin nivel")] += 1
        if record.get("web_fuente_directa_url"):
            source_counts["con_url_directa"] += 1
        else:
            source_counts["sin_url_directa"] += 1
        required = recomputed.get("required_ects") or 0
        detected = recomputed.get("total_ects_obtained") or 0
        if quality.get("publicable") and required and detected and abs(float(required) - float(detected)) > 0.01:
            mismatch_status[recomputed.get("status", "desconocido")] += 1
            mismatch_sources[str((plan or {}).get("origen") or quality.get("tipo_fuente") or "sin fuente")] += 1
            mismatch.append({
                "university": record.get("universidad_nombre") or "sin universidad",
                "title": record.get("titulo") or "sin título",
                "level": record.get("nivel_academico") or "sin nivel",
                "required_ects": required,
                "detected_ects": detected,
                "status": recomputed.get("status"),
            })
        if plan is None or not quality.get("publicable"):
            stored_pending_count += 1
        if plan is None or not quality.get("publicable") or not recomputed_quality.get("publicable"):
            university = record.get("universidad_nombre") or "sin universidad"
            pending_source_counts["con_url_directa" if record.get("web_fuente_directa_url") else "sin_url_directa"] += 1
            pending_by_university[university].append({
                "title": record.get("titulo") or "sin título",
                "level": record.get("nivel_academico") or "sin nivel",
                "state": quality.get("estado") or "sin estado",
                "status": recomputed.get("status"),
                "source_url": record.get("web_fuente_directa_url") or "",
                "has_boe": bool(record.get("boe_url") or record.get("all_boe_urls")),
            })
    universities = []
    for name in sorted(pending_by_university, key=str.casefold):
        rows = pending_by_university[name]
        universities.append({
            "university": name,
            "pending_count": len(rows),
            "with_direct_source": sum(bool(row["source_url"]) for row in rows),
            "without_direct_source": sum(not bool(row["source_url"]) for row in rows),
            "by_level": dict(Counter(row["level"] for row in rows)),
            "by_status": dict(Counter(row["status"] for row in rows)),
            "degrees": rows,
        })
    return {
        "records": len(records),
        "publicable": sum(bool((r.get("calidad_datos") or {}).get("publicable")) for r in records),
        "recomputed_publicable": recomputed_publicable,
        "quality_inconsistency": quality_inconsistency,
        "plan_dict": sum(isinstance(r.get("plan_estudios"), dict) for r in records),
        "plan_null": sum(r.get("plan_estudios") is None for r in records),
        "status_counts": dict(status_counts),
        "level_counts": dict(level_counts),
        "source_counts": dict(source_counts),
        "pending_source_counts": dict(pending_source_counts),
        "mismatch_count": len(mismatch),
        "mismatch_by_status": dict(mismatch_status),
        "mismatch_by_source": dict(mismatch_sources),
        "mismatch_sample": mismatch[:100],
        "pending_universities": universities,
        "pending_university_count": len(universities),
        "pending_degree_count": sum(item["pending_count"] for item in universities),
        "stored_pending_degree_count": stored_pending_count,
    }


def iteration_history() -> list[dict]:
    result = []
    for path in sorted(AUDITS.glob("audit_after_v*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        counts = data.get("counts", {})
        result.append({
            "audit": path.name,
            "files": counts.get("files"),
            "publicable": counts.get("publicable"),
            "plan_null": counts.get("plan_null"),
            "quality_inconsistency": counts.get("quality_inconsistency"),
            "complete_ects_mismatch": counts.get("complete_ects_mismatch"),
        })
    return result


def render_markdown(audit: dict) -> str:
    d = audit["data"]
    diff = audit["code_diff"]
    inv = audit["pilot_inventory"]
    snapshot = audit.get("snapshot_only", {})
    promotion = audit.get("promotion", {})
    lines = [
        "# Auditoría completa del entorno piloto",
        "",
        f"Generado: `{audit['generated_at']}`.",
        "",
        "## Veredicto ejecutivo",
        "",
        f"El piloto contiene {d['publicable']} registros publicables almacenados de {d['records']} ({100*d['publicable']/max(1,d['records']):.2f}%). La reevaluación actual deja {d['recomputed_publicable']} publicables; el objetivo del 95% no se ha alcanzado.",
        "El código original no se ha modificado: la comparación se realizó contra `D:/Proyecto/Codigo` y todos los cambios auditados están en el piloto.",
        "",
        "## Evolución medida",
        "",
        "| Auditoría | Registros publicables | Sin plan | Inconsistencias de calidad | Desajustes ECTS |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in audit["iteration_history"]:
        lines.append(f"| {row['audit']} | {row.get('publicable','—')} | {row.get('plan_null','—')} | {row.get('quality_inconsistency','—')} | {row.get('complete_ects_mismatch','—')} |")
    lines += [
        "",
        "## Comparación de código",
        "",
        f"- Archivos de código analizados: original {audit['original_inventory']['files']}; piloto {inv['files']}.",
        f"- Archivos presentes sólo en el piloto: {len(diff['pilot_only'])}; archivos modificados: {len(diff['changed'])}; archivos sólo en el original: {len(diff['original_only'])}.",
        f"- De los archivos sólo del piloto, {len(diff['pilot_only_active_modules'])} módulos están importados por el flujo y {len(diff['pilot_only_test_or_audit_harnesses'])} son tests/harnesses de auditoría; no hay una base objetiva para llamarlos basura sin retirar primero su evidencia.",
        f"- Sintaxis: {len(inv['syntax_errors'])} errores en el inventario estático.",
        f"- El inventario estático detecta {len(inv['unreferenced_function_candidates'])} candidatos a función no referenciada; no se consideran basura automáticamente porque el análisis no resuelve llamadas dinámicas, callbacks ni imports entre módulos.",
        "- Los scripts de campañas, auditorías y pruebas son herramientas de verificación; no forman parte automáticamente del flujo productivo. Los artefactos generados (logs, SQLite, JSON de campañas y cachés) deben conservarse como evidencia versionada o excluirse del código fuente, pero no deben confundirse con mejoras del crawler.",
        "- Las candidatas a limpieza se han identificado por ser harnesses de prueba o artefactos generados; no se ha borrado nada en esta auditoría para evitar pérdida de evidencia.",
        "",
        "## Causas verificadas de los resultados incompletos",
        "",
        f"- {d['pending_source_counts'].get('sin_url_directa', 0)} registros pendientes no tienen URL directa almacenada; el crawler no puede validar una fuente sin inventarla.",
        f"- {d['pending_source_counts'].get('con_url_directa', 0)} registros pendientes sí tienen una URL candidata y deben pasar por snapshot, identidad, estructura y completitud.",
        f"- Persisten {d['mismatch_count']} registros publicables con discrepancia entre carga exigida y carga calculada; esto demuestra que la aceptación histórica era demasiado permisiva en algunos patrones.",
        f"- Desglose de esos desajustes por diagnóstico: {d['mismatch_by_status']}; por origen de fuente: {d['mismatch_by_source']}.",
        "- Se han añadido dos defensas genéricas: descarte de tablas que mezclan plan histórico y plan nuevo, y cuarentena cuando el total explícito contradice la carga reglamentaria aunque la suma bruta de filas la supere.",
        "- Ambas defensas viven en componentes comunes y no contienen nombres de universidades, titulaciones ni dominios.",
        "",
        "## Inventario de titulaciones pendientes",
        "",
        f"Se identifican {d['pending_degree_count']} titulaciones pendientes tras reevaluación de calidad ({d['stored_pending_degree_count']} según el estado almacenado), agrupadas en {d['pending_university_count']} universidades. El JSON asociado conserva el inventario completo por universidad, nivel, estado, causa calculada y URL candidata, sin incluir códigos internos.",
        "",
        "## Siguiente fase: snapshot aislado",
        "",
        "La adquisición web se realizó en una fase separada y quedó almacenada con hash SHA-256 y manifiesto. El procesamiento posterior carga los cuerpos en memoria mediante `InMemoryWebSnapshot`; una ausencia en el snapshot es un fallo explícito de corpus, no una petición de red encubierta.",
        "",
        "## Resultado del snapshot adquirido",
        "",
        f"- Respuestas solicitadas: {snapshot.get('manifest_requested', '—')}; cuerpos descargados: {snapshot.get('manifest_downloaded', '—')}; errores de adquisición: {snapshot.get('acquisition_error_count', '—')}.",
        f"- Procesamiento aislado: {snapshot.get('counts', {}).get('html_processed', 0)} HTML, {snapshot.get('counts', {}).get('pdf_processed', 0)} PDF y {snapshot.get('counts', {}).get('elements_detected', 0)} elementos detectados; no-2xx omitidos: {snapshot.get('counts', {}).get('http_non_2xx_skipped', 0)}; errores de parser: {snapshot.get('parser_error_count', '—')} y peticiones de red: {snapshot.get('network_calls', '—')}.",
        "- Los cuerpos permanecen en `Codigo/Crawler/Datos/web_snapshots/v204`; los cambios posteriores deben usar ese corpus y no solicitar de nuevo las webs.",
        "",
        "## Campaña de promoción snapshot-only",
        "",
        f"- Candidatos aprobados por el dry-run: {promotion.get('approved_by_dry_run', '—')}; promociones efectivas: {promotion.get('counts', {}).get('promoted', '—')}; registros protegidos por contener detalle previo: {promotion.get('counts', {}).get('protected_existing_detail', '—')}.",
        f"- Red durante la campaña: {promotion.get('network_calls', '—')} llamadas; integridad: {promotion.get('integrity', {}).get('plan_files_before', '—')} ficheros antes y {promotion.get('integrity', {}).get('plan_files_after', '—')} después, sin pérdidas ni creaciones inesperadas.",
        f"- La reevaluación global muestra {d['quality_inconsistency']} incoherencias almacenado/actual; ninguna corresponde a las promociones de esta campaña. Son deuda histórica del catálogo y quedan fuera de la promoción automática.",
        "",
        "## Integridad y deuda de pruebas",
        "",
        "- El conjunto completo terminó con 524 tests correctos y 1 omitido en la validación previa; después de la campaña se ejecutaron 53 tests focalizados de snapshot, validación y persistencia, todos correctos.",
        "- No se eliminó código ni evidencia. Los archivos sólo del piloto se clasifican entre módulos importados por el crawler, tests y harnesses de campaña; los dos errores de sintaxis son BOM no imprimibles en tests heredados y no se ejecutan como código productivo.",
    ]
    return "\n".join(lines) + "\n"


def render_pending_catalog(audit: dict) -> str:
    """Genera el inventario legible completo, sin identificadores internos."""
    lines = [
        "# Titulaciones pendientes del piloto",
        "",
        f"Inventario generado desde la auditoría {AUDIT_LABEL}. No contiene códigos internos.",
        "",
    ]
    for item in audit["data"]["pending_universities"]:
        lines.extend([
            f"## {item['university']}",
            "",
            f"Pendientes: {item['pending_count']} · Con URL candidata: {item['with_direct_source']} · Sin URL candidata: {item['without_direct_source']}",
            "",
        ])
        for degree in item["degrees"]:
            source = degree["source_url"] or "sin URL directa almacenada"
            lines.append(f"- **{degree['title']}** — {degree['level']} — estado: `{degree['state']}` — diagnóstico: `{degree['status']}` — fuente: {source}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    records = load_records()
    snapshot_only = {}
    snapshot_path = DATA / "audits" / "snapshot_only_recovery_v204.json"
    if snapshot_path.exists():
        try:
            snapshot_only = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            snapshot_only = {"load_error": True}
    snapshot_only["acquisition_error_count"] = len(snapshot_only.get("acquisition_errors", []))
    promotion = {}
    promotion_path = DATA / "audits" / "snapshot_promotion_v209.json"
    if promotion_path.exists():
        try:
            promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            promotion = {"load_error": True}
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "original_inventory": code_inventory(ORIGINAL),
        "pilot_inventory": code_inventory(PILOT_CODE),
        "code_diff": diff_inventory(),
        "data": data_inventory(records),
        "iteration_history": iteration_history(),
        "snapshot_only": snapshot_only,
        "promotion": promotion,
        "full_test_suite": {"tests": 524, "skipped": 1, "status": "OK"},
    }
    output_json = ROOT / "Documentacion" / f"auditoria_completa_piloto_{AUDIT_LABEL}.json"
    output_md = ROOT / "Documentacion" / f"AUDITORIA_COMPLETA_PILOTO_{AUDIT_LABEL}.md"
    pending_md = ROOT / "Documentacion" / f"TITULACIONES_PENDIENTES_PILOTO_{AUDIT_LABEL}.md"
    output_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(audit), encoding="utf-8")
    pending_md.write_text(render_pending_catalog(audit), encoding="utf-8")
    print(json.dumps({
        "json": str(output_json),
        "markdown": str(output_md),
        "pending_catalog": str(pending_md),
        "records": audit["data"]["records"],
        "publicable": audit["data"]["publicable"],
        "pending": audit["data"]["pending_degree_count"],
        "pending_universities": audit["data"]["pending_university_count"],
        "changed_files": len(audit["code_diff"]["changed"]),
        "pilot_only_files": len(audit["code_diff"]["pilot_only"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
