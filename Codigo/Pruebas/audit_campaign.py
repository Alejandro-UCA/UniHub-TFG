"""Auditoría de una campaña real sin alterar sus datos de entrada."""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from datetime import datetime, timezone

_CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler"))
if _CRAWLER_DIR not in sys.path:
    sys.path.insert(0, _CRAWLER_DIR)
from data_quality import assess_plan_quality


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def audit_root(root: str) -> dict:
    data_dir = os.path.join(root, "Codigo", "Crawler", "Datos")
    files = glob.glob(os.path.join(data_dir, "planes_estudio", "**", "*.json"), recursive=True)
    counts = collections.Counter()
    quality = collections.Counter()
    levels = collections.Counter()
    mismatches = []
    guide = collections.Counter()
    candidate_samples = []
    review_queue = []

    for path in files:
        try:
            record = _load(path)
        except Exception:
            counts["json_error"] += 1
            continue
        counts["files"] += 1
        plan = record.get("plan_estudios")
        plan_quality = record.get("calidad_datos") or {}
        recomputed_quality = assess_plan_quality(record, record.get("origen_fuente"))
        counts["plan_null"] += int(plan is None)
        counts["plan_dict"] += int(isinstance(plan, dict))
        counts["publicable"] += int(bool(plan_quality.get("publicable")))
        counts["recomputed_publicable"] += int(bool(recomputed_quality.get("publicable")))
        counts["quality_inconsistency"] += int(
            bool(plan_quality.get("publicable")) != bool(recomputed_quality.get("publicable"))
        )
        counts["candidate_plan"] += int(bool(record.get("candidato_plan_estudios")))
        counts["boe_missing"] += int(not bool(record.get("boe_url")))
        counts["web_missing"] += int(not bool(record.get("web_fuente_directa_url")))
        counts["price_missing"] += int(record.get("precio_credito_ects") is None)
        quality[str(record.get("estado_calidad"))] += 1
        levels[str(record.get("nivel_academico"))] += 1
        if "doctor" in str(record.get("nivel_academico") or "").lower():
            counts["doctorate_files"] += 1
        quality_errors = plan_quality.get("errores") or []
        counts["historical_source"] += int("fuente_historica_o_plan_extinguido" in quality_errors)
        counts["pdf_extraction_incomplete"] += int("extraccion_pdf_incompleta" in quality_errors)
        counts["recomputed_historical_source"] += int(
            "fuente_historica_o_plan_extinguido" in (recomputed_quality.get("errores") or [])
        )
        counts["recomputed_alternative_review"] += int(
            recomputed_quality.get("completitud") == "optatividad_no_resuelta"
        )
        needs_review = bool(
            record.get("candidato_plan_estudios")
            or record.get("estado_calidad") in {"pendiente_revision", "parcial"}
            or quality_errors
        )
        if needs_review:
            counts["review_required"] += 1
            if len(review_queue) < 100:
                review_queue.append({
                    "file": path,
                    "code": record.get("codigo_estudio"),
                    "title": record.get("titulo"),
                    "state": record.get("estado_calidad"),
                    "errors": quality_errors,
                    "candidate": bool(record.get("candidato_plan_estudios")),
                })
        if record.get("proveniencia_precio"):
            counts["price_provenance"] += 1
            counts["price_unverified"] += int(not record["proveniencia_precio"].get("verificado"))
        if isinstance(plan, dict):
            counts["plan_complete"] += int(bool(plan.get("plan_completo")))
            counts["alternative_review"] += int(bool(plan.get("optatividad_no_resuelta")))
            total = plan.get("ects_totales_detectados")
            required = plan.get("ects_exigidos")
            if bool(plan.get("plan_completo")) and isinstance(total, (int, float)) and isinstance(required, (int, float)) and required > 0 and abs(total - required) > 0.1:
                counts["complete_ects_mismatch"] += 1
                if len(mismatches) < 20:
                    mismatches.append({"file": path, "code": record.get("codigo_estudio"), "title": record.get("titulo"), "required": required, "detected": total})
            for element in plan.get("elementos_curriculares") or []:
                if not isinstance(element, dict):
                    continue
                state = element.get("estado_guia_docente")
                if state:
                    guide["state_" + str(state)] += 1
                g = element.get("guia_docente")
                if isinstance(g, dict):
                    guide["embedded"] += 1
                    q = g.get("calidad_extraccion") or {}
                    guide["quality_" + str(q.get("nivel"))] += 1
                    guide["blank_name"] += int(not bool(g.get("nombre_asignatura")))
                    guide["blank_code"] += int(not bool(g.get("codigo_asignatura")))
                    identity = g.get("identidad") or {}
                    guide["identity_verified"] += int(bool(identity.get("verificada")))
                    guide["identity_unverified"] += int(not bool(identity.get("verificada")))
        if len(candidate_samples) < 10 and record.get("candidato_plan_estudios"):
            candidate_samples.append({"file": path, "code": record.get("codigo_estudio"), "title": record.get("titulo"), "state": record.get("estado_calidad")})

    catalog_path = os.path.join(data_dir, "titulaciones_universidad.json")
    catalog_entries = 0
    catalog_universities = 0
    if os.path.exists(catalog_path):
        catalog = _load(catalog_path)
        catalog_universities = len(catalog) if isinstance(catalog, dict) else 0
        catalog_entries = sum(int(value.get("total_titulaciones_vigentes", 0)) for value in catalog.values() if isinstance(value, dict))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": os.path.abspath(root),
        "data_dir": data_dir,
        "catalog_universities": catalog_universities,
        "catalog_entries": catalog_entries,
        "counts": dict(counts),
        "quality": dict(quality),
        "levels": dict(levels),
        "guides": dict(guide),
        "review_queue_count": len(review_queue),
        "review_queue": review_queue,
        "mismatch_samples": mismatches,
        "candidate_samples": candidate_samples,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit_root(args.root)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
