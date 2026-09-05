"""Sincronización, propagación y resolución de consorcios y titulaciones conjuntas interuniversitarias."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

from core.checkpoint import atomic_json_dump, load_json_safe
from core.config import PLANES_DIR
from quality.curriculum_validator import is_curriculum_complete
from quality.data_quality import apply_plan_quality, assess_plan_quality, source_record
from core.downloader import normalize_url
from lexicon.academic_keywords import EUROPEAN_ALLIANCES_KEYWORDS
from pipelines.common import iter_plan_files
from utils.text_utils import normalize_joint_title as _canonical_normalize_joint_title

_PROPAGATION_VOLATILE_FIELDS = frozenset({
    "fecha_procesado",
    "fecha_ultima_comprobacion_fuente",
    "snapshot_hash",
    "previous_snapshot",
})


def normalize_joint_title(title: str, strip_consortium: bool = True) -> str:
    """Normaliza el título de una titulación interuniversitaria para indexación y emparejamiento."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title.lower()).encode("ASCII", "ignore").decode("utf-8")
    t = re.sub(r"[\(\[].*?[\)\]]", "", t)
    t = t.replace("universitat", "universidad").replace("politècnica", "politecnica").replace("de la", "de")
    if strip_consortium:
        t = re.split(
            r"\s+(?:por\s+las?|por\s+els?|por\s+los?|per\s+les?|per\s+la|pola|by)\s+universidad",
            t,
            maxsplit=1,
        )[0]
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


def _stable_propagation_signature(payload: dict) -> str:
    """Firma el contenido relevante para evitar escrituras temporales repetidas."""
    stable_payload = {
        key: value
        for key, value in (payload or {}).items()
        if key not in _PROPAGATION_VOLATILE_FIELDS
    }
    return json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _quarantine_incompatible_direct_source_collisions(
    source_groups: dict,
    stats: dict,
) -> None:
    """Retira fuentes web reutilizadas por titulaciones incompatibles."""
    from pipelines.parte2_web_crawler import are_degree_titles_compatible

    for source_key, entries in source_groups.items():
        if not source_key or len(entries) < 2 or "boe.es" in source_key:
            continue
        titles = []
        for _, record in entries:
            title = str(record.get("titulo") or "").strip()
            if title and title not in titles:
                titles.append(title)
        if len(titles) < 2:
            continue
        incompatible = any(
            not are_degree_titles_compatible(first, second, str(record.get("universidad_nombre") or ""))
            for index, first in enumerate(titles)
            for second in titles[index + 1:]
            for _, record in entries[:1]
        )
        if not incompatible:
            continue

        for path, record in entries:
            direct_url = record.pop("web_fuente_directa_url", None)
            if not direct_url:
                continue
            rejected = record.setdefault("fuentes_rechazadas", [])
            if not isinstance(rejected, list):
                rejected = []
                record["fuentes_rechazadas"] = rejected
            rejected_key = normalize_url(direct_url)
            if rejected_key and not any(
                isinstance(item, dict)
                and normalize_url(item.get("url")) == rejected_key
                for item in rejected
            ):
                rejected.append({
                    "url": direct_url,
                    "motivo": "fuente_web_compartida_por_titulos_incompatibles",
                    "fecha": datetime.now().isoformat(),
                })
            sources = record.get("fuentes")
            if isinstance(sources, list):
                record["fuentes"] = [
                    item for item in sources
                    if not (
                        isinstance(item, dict)
                        and normalize_url(item.get("url")) == rejected_key
                        and "web" in str(item.get("tipo") or "").lower()
                    )
                ]
            if isinstance(record.get("plan_estudios"), dict):
                quality = apply_plan_quality(
                    record,
                    record.get("plan_estudios"),
                    record.get("origen_fuente"),
                )
                record["estado_fuente"] = (
                    "verificada"
                    if quality.get("publicable")
                    else "candidata_no_publicable"
                )
            record["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
            atomic_json_dump(record, path)
            stats["source_collisions_quarantined"] = stats.get("source_collisions_quarantined", 0) + 1


def propagate_interuniversity_and_shared_boe_plans(planes_dir: str = PLANES_DIR) -> dict:
    """Sincroniza y propaga atómicamente planes de estudio completos entre consorcios y BOEs compartidos."""
    from pipelines.parte2_web_crawler import extract_participating_universities, promote_verified_candidate

    stats = {
        "boe_shared_rescued": 0,
        "interuniv_shared_rescued": 0,
        "total_propagated": 0,
        "quality_metadata_reconciled": 0,
        "source_collisions_quarantined": 0,
        "candidate_plans_promoted": 0,
        "candidate_plans_preserved": 0,
    }
    if not os.path.exists(planes_dir):
        return stats

    file_paths = iter_plan_files(planes_dir)

    boe_index = {}
    title_index = {}
    empty_records = []
    direct_source_groups = defaultdict(list)

    for path in file_paths:
        d = load_json_safe(path)
        if not d:
            continue

        candidate_reconciliation = promote_verified_candidate(d)
        if candidate_reconciliation.get("promoted"):
            d["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
            atomic_json_dump(d, path)
            stats["candidate_plans_promoted"] += 1
        elif candidate_reconciliation.get("reason") == "plan_actual_con_detalle_preservado":
            stats["candidate_plans_preserved"] += 1

        boe = d.get("boe_url") or ""
        elems = d.get("plan_estudios", {}).get("elementos_curriculares", []) if d.get("plan_estudios") else []
        direct_url = normalize_url(d.get("web_fuente_directa_url"))
        if direct_url and "boe.es" not in direct_url:
            direct_source_groups[direct_url].append((path, d))
        norm_t = normalize_joint_title(d.get("titulo", ""), strip_consortium=True)
        is_interuniv = bool(
            d.get("interuniversitario")
            or d.get("universidades_participantes")
            or "interuniversitari" in norm_t
            or "consorcio" in norm_t
            or "conjunto" in norm_t
            or "erasmus mundus" in norm_t
            or re.search(r"\b(?:por\s+las?|per\s+les?)\s+universidad", d.get("titulo", ""), re.I)
            or any(k in d.get("titulo", "").lower() for k in EUROPEAN_ALLIANCES_KEYWORDS)
        )

        level_key = normalize_joint_title(d.get("nivel_academico", ""), strip_consortium=False)
        title_key = f"{norm_t}|{level_key}" if level_key else norm_t
        
        if isinstance(d.get("plan_estudios"), dict):
            stored_quality = d.get("calidad_datos") or {}
            current_quality = assess_plan_quality(
                d,
                d.get("origen_fuente"),
            )
            if bool(stored_quality.get("publicable")) != bool(current_quality.get("publicable")):
                refreshed_quality = apply_plan_quality(
                    d,
                    d.get("plan_estudios"),
                    d.get("origen_fuente"),
                )
                d["estado_fuente"] = (
                    "verificada"
                    if refreshed_quality.get("publicable")
                    else "candidata_no_publicable"
                )
                d["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                atomic_json_dump(d, path)
                stats["quality_metadata_reconciled"] += 1

        has_sufficient_detail = len(elems) >= 5 or is_curriculum_complete(d)
        if has_sufficient_detail:
            if (
                d.get("origen_fuente") == "resolucion_boe_compartida"
                and boe
                and d.get("web_fuente_directa_url")
                and normalize_url(d.get("web_fuente_directa_url")) != normalize_url(boe)
            ):
                inherited_url = d.pop("web_fuente_directa_url", None)
                rejected = d.setdefault("fuentes_rechazadas", [])
                if not isinstance(rejected, list):
                    rejected = []
                    d["fuentes_rechazadas"] = rejected
                inherited_key = normalize_url(inherited_url)
                if inherited_key and not any(
                    isinstance(item, dict)
                    and normalize_url(item.get("url")) == inherited_key
                    for item in rejected
                ):
                    rejected.append({
                        "url": inherited_url,
                        "motivo": "fuente_web_no_propagable_con_resolucion_boe",
                        "fecha": datetime.now().isoformat(),
                    })
                sources = d.get("fuentes")
                if isinstance(sources, list):
                    d["fuentes"] = [
                        item for item in sources
                        if not (
                            isinstance(item, dict)
                            and normalize_url(item.get("url")) == inherited_key
                            and "web" in str(item.get("tipo") or "").lower()
                        )
                    ]
                d["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                atomic_json_dump(d, path)

            if d.get("origen_fuente") in {
                "resolucion_boe_compartida",
                "interuniversitario_compartido",
            } and isinstance(d.get("plan_estudios"), dict):
                before_semantic = _stable_propagation_signature(d)
                refreshed_quality = apply_plan_quality(
                    d,
                    d.get("plan_estudios"),
                    d.get("origen_fuente"),
                )
                if refreshed_quality.get("publicable"):
                    d["estado_fuente"] = "verificada"
                if _stable_propagation_signature(d) != before_semantic:
                    d["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                    atomic_json_dump(d, path)
            if boe and "boe.es" in boe:
                if boe not in boe_index or len(elems) > len(boe_index[boe][0].get("elementos_curriculares", [])):
                    boe_index[boe] = (d.get("plan_estudios", {}), boe)
            if title_key and is_interuniv:
                donor_univ = str(d.get("universidad_nombre") or d.get("universidad_codigo") or "")
                if title_key not in title_index or len(elems) > len(title_index[title_key][0].get("elementos_curriculares", [])):
                    title_index[title_key] = (d.get("plan_estudios", {}), d.get("web_fuente_directa_url") or boe, donor_univ)
        else:
            empty_records.append((path, d, boe, norm_t, is_interuniv))

    _quarantine_incompatible_direct_source_collisions(
        direct_source_groups,
        stats,
    )

    for path, d, boe, norm_t, is_interuniv_target in empty_records:
        matched_plan = None
        source_url = ""
        origen = ""
        donor_univ = ""

        if boe and boe in boe_index:
            matched_plan, source_url = boe_index[boe]
            origen = "resolucion_boe_compartida"
            stats["boe_shared_rescued"] += 1
        elif is_interuniv_target:
            title_key = f"{norm_t}|{normalize_joint_title(d.get('nivel_academico', ''), strip_consortium=False)}" if d.get("nivel_academico") else norm_t
            if title_key in title_index:
                info = title_index[title_key]
                matched_plan = info[0]
                source_url = info[1]
                donor_univ = info[2] if len(info) >= 3 else ""
                origen = "interuniversitario_compartido"
                stats["interuniv_shared_rescued"] += 1

        is_european = any(k in d.get("titulo", "").lower() for k in EUROPEAN_ALLIANCES_KEYWORDS)
        if matched_plan:
            d["plan_estudios"] = matched_plan
            d["origen_fuente"] = origen
            if origen == "resolucion_boe_compartida":
                d.pop("web_fuente_directa_url", None)
            else:
                d["web_fuente_directa_url"] = source_url
                if origen == "interuniversitario_compartido" and donor_univ:
                    d["fuente_delegada_universidad"] = donor_univ
            if is_interuniv_target and not d.get("universidades_participantes"):
                d["universidades_participantes"] = extract_participating_universities(d.get("titulo", ""))
            d["fecha_procesado"] = datetime.now().isoformat()
            if source_url:
                sources = d.setdefault("fuentes", [])
                if not isinstance(sources, list):
                    sources = []
                    d["fuentes"] = sources
                source = source_record(
                    source_url,
                    "RESOLUCION_BOE_COMPARTIDA"
                    if origen == "resolucion_boe_compartida"
                    else "INTERUNIVERSITARIO_COMPARTIDO",
                    confidence=0.95,
                )
                sources[:] = [item for item in sources if item.get("url") != source["url"]]
                sources.append(source)
            refreshed_quality = apply_plan_quality(d, matched_plan, origen)
            if refreshed_quality.get("publicable"):
                d["estado_fuente"] = "verificada"
                d["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                atomic_json_dump(d, path)
                stats["total_propagated"] += 1
            else:
                d["fecha_ultima_comprobacion_fuente"] = datetime.now().isoformat()
                atomic_json_dump(d, path)

    return stats


__all__ = [
    "_quarantine_incompatible_direct_source_collisions",
    "normalize_joint_title",
    "propagate_interuniversity_and_shared_boe_plans",
]
