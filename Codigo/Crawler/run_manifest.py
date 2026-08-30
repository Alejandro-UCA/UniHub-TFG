"""Manifiestos auditables de ejecuciones de la Fase 1.

Cada ejecución conserva su configuración, estado de las partes y métricas
resumidas. El manifiesto no reemplaza los datos del crawler: permite comparar
campañas nacionales y justificar cualquier resultado parcial.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from checkpoint import atomic_json_dump
from config import DATA_DIR, FULL_REVALIDATION, REDISCOVER_URLS_EVERY_RUN, TARGET_UNIVERSITY_CODES
from runtime_capabilities import detect_runtime_capabilities


RUN_MANIFESTS_DIR = os.getenv("CRAWLER_RUN_MANIFESTS_DIR", os.path.join(DATA_DIR, "run_manifests"))


class RunManifest:
    def __init__(self, *, parts, limit_universities=None, limit_degrees=None, force=False, workers=None):
        started = datetime.now(timezone.utc).isoformat()
        self.data = {
            "run_id": uuid.uuid4().hex,
            "started_at": started,
            "finished_at": None,
            "status": "running",
            "execution": {
                "parts": list(parts),
                "limit_universities": limit_universities,
                "limit_degrees": limit_degrees,
                "force": bool(force),
                "workers": workers,
                "target_university_codes": list(TARGET_UNIVERSITY_CODES),
                "full_revalidation": bool(FULL_REVALIDATION or force),
                "rediscover_urls": bool(REDISCOVER_URLS_EVERY_RUN or force),
                "runtime_capabilities": detect_runtime_capabilities(),
            },
            "parts": {},
            "coverage": {
                "universities_attempted": 0,
                "university_codes_attempted": [],
                "degrees_discovered": 0,
                "degrees_resolved": 0,
                "subjects_considered": 0,
                "guides_found": 0,
                "cached_hits": 0,
                "guides_not_found": 0,
                "guide_identity_rejected": 0,
                "guide_discovery_files": 0,
                "guide_discovery_urls": 0,
                "guide_discovery_blocked": 0,
                "guide_discovery_cache_hits": 0,
                "guide_spa_fallbacks": 0,
                "guide_candidate_urls_generated": 0,
                "guide_candidate_urls_requested": 0,
                "guide_http_200": 0,
                "guide_http_404": 0,
                "guide_http_other": 0,
                "guide_request_errors": 0,
                "guide_robots_denied": 0,
                "guide_quality_score_total": 0.0,
                "guide_quality_scored": 0,
                "guide_quality_average": 0.0,
                "subjects_resumed": 0,
                "negative_cache_hits": 0,
                "metrics_by_university": {},
                "metrics_by_domain": {},
                "incidencias_controladas": 0,
                "partial_or_failed_parts": [],
            },
        }
        self.path = ""

    def _persist(self):
        os.makedirs(RUN_MANIFESTS_DIR, exist_ok=True)
        if not self.path:
            self.path = os.path.join(RUN_MANIFESTS_DIR, f"{self.data['run_id']}.json")
        atomic_json_dump(self.data, self.path)

    def start(self):
        self._persist()
        return self.data["run_id"]

    def record_part_progress(self, part: int, *, status: str = "running"):
        """Persiste la parte activa antes de iniciar trabajo de red."""
        key = f"parte{part}"
        current = self.data["parts"].get(key)
        if not isinstance(current, dict):
            current = {}
        current["status"] = status
        current["started_at"] = datetime.now(timezone.utc).isoformat()
        self.data["parts"][key] = current
        self.data["active_part"] = int(part)
        self._persist()

    def record_part(self, part: int, result: dict):
        result = result if isinstance(result, dict) else {}
        self.data["parts"][f"parte{part}"] = result
        coverage = self.data["coverage"]
        processed_codes = result.get("university_codes_processed")
        if isinstance(processed_codes, (list, tuple, set)):
            known_codes = set(coverage.get("university_codes_attempted") or [])
            known_codes.update(str(code).zfill(3) for code in processed_codes if str(code).strip())
            coverage["university_codes_attempted"] = sorted(known_codes)
            coverage["universities_attempted"] = len(known_codes)
        else:
            # Compatibilidad con resultados de fases antiguas sin desglose.
            coverage["universities_attempted"] += self._non_negative_int(result.get("universities_processed"))
        # ``missing_degrees`` es el número de titulaciones pendientes antes de
        # la Parte 2; no representa titulaciones descubiertas por el crawler.
        coverage["degrees_pending_resolution"] = coverage.get("degrees_pending_resolution", 0) + self._non_negative_int(
            result.get("missing_degrees")
        )
        coverage["degrees_resolved"] += self._non_negative_int(result.get("resolved_degrees"))
        coverage["subjects_considered"] += self._non_negative_int(result.get("guide_subjects_considered"))
        processed_guides = self._non_negative_int(result.get("processed_guides"))
        cached_hits = self._non_negative_int(result.get("cached_hits"))
        coverage["guides_found"] += processed_guides + cached_hits
        coverage["cached_hits"] += cached_hits
        coverage["guides_not_found"] += self._non_negative_int(result.get("guide_subjects_not_found"))
        coverage["guide_identity_rejected"] += self._non_negative_int(result.get("guide_identity_rejected"))
        coverage["guide_discovery_files"] += self._non_negative_int(result.get("guide_discovery_files"))
        coverage["guide_discovery_urls"] += self._non_negative_int(result.get("guide_discovery_urls"))
        coverage["guide_discovery_blocked"] += self._non_negative_int(result.get("guide_discovery_blocked"))
        coverage["guide_discovery_cache_hits"] += self._non_negative_int(result.get("guide_discovery_cache_hits"))
        coverage["guide_spa_fallbacks"] += self._non_negative_int(result.get("guide_spa_fallbacks"))
        coverage["guide_candidate_urls_generated"] += self._non_negative_int(result.get("guide_candidate_urls_generated"))
        coverage["guide_candidate_urls_requested"] += self._non_negative_int(result.get("guide_candidate_urls_requested"))
        coverage["guide_http_200"] += self._non_negative_int(result.get("guide_http_200"))
        coverage["guide_http_404"] += self._non_negative_int(result.get("guide_http_404"))
        coverage["guide_http_other"] += self._non_negative_int(result.get("guide_http_other"))
        coverage["guide_request_errors"] += self._non_negative_int(result.get("guide_request_errors"))
        coverage["guide_robots_denied"] += self._non_negative_int(result.get("guide_robots_denied"))
        coverage["guide_quality_score_total"] += self._non_negative_float(result.get("guide_quality_score_total"))
        coverage["guide_quality_scored"] += self._non_negative_int(result.get("guide_quality_scored"))
        if coverage["guide_quality_scored"]:
            coverage["guide_quality_average"] = round(
                coverage["guide_quality_score_total"] / coverage["guide_quality_scored"], 2
            )
        coverage["subjects_resumed"] += self._non_negative_int(result.get("resumed_subjects"))
        coverage["negative_cache_hits"] += self._non_negative_int(result.get("negative_cache_hits"))
        self._merge_numeric_metrics(coverage["metrics_by_university"], result.get("metrics_by_university"))
        self._merge_numeric_metrics(coverage["metrics_by_domain"], result.get("metrics_by_domain"))
        coverage["incidencias_controladas"] += self._non_negative_int(result.get("incidencias_controladas"))
        if result.get("status") in {"partial", "failed", "skipped", "cancelled"} and part not in coverage["partial_or_failed_parts"]:
            coverage["partial_or_failed_parts"].append(part)
        self._persist()

    @classmethod
    def _merge_numeric_metrics(cls, target: dict, source) -> None:
        """Fusiona métricas anidadas sin permitir valores no numéricos."""
        if not isinstance(source, dict):
            return
        for key, values in source.items():
            if not isinstance(values, dict):
                continue
            destination = target.setdefault(str(key), {})
            for metric, value in values.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                destination[str(metric)] = destination.get(str(metric), 0) + max(0, value)

    @staticmethod
    def _non_negative_int(value) -> int:
        """Convierte métricas externas sin permitir que un dato inválido rompa el manifiesto."""
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _non_negative_float(value) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def record_etl_sync(self, result: dict):
        """Registra la sincronización posterior para que el manifiesto sea fiel al pipeline."""
        self.data["etl_sync"] = result if isinstance(result, dict) else {"status": "failed"}
        self._persist()

    def finish(self, status: str, *, error: str | None = None):
        self.data["status"] = status
        self.data["finished_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            self.data["error"] = str(error)
        self.data.pop("active_part", None)
        self._persist()
