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
            },
            "parts": {},
            "coverage": {
                "universities_attempted": 0,
                "degrees_discovered": 0,
                "degrees_resolved": 0,
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

    def record_part(self, part: int, result: dict):
        result = result if isinstance(result, dict) else {}
        self.data["parts"][f"parte{part}"] = result
        coverage = self.data["coverage"]
        coverage["universities_attempted"] += int(result.get("universities_processed", 0) or 0)
        coverage["degrees_discovered"] += int(result.get("missing_degrees", 0) or 0)
        coverage["degrees_resolved"] += int(result.get("resolved_degrees", 0) or 0)
        if result.get("status") in {"partial", "failed", "skipped"} and part not in coverage["partial_or_failed_parts"]:
            coverage["partial_or_failed_parts"].append(part)
        self._persist()

    def finish(self, status: str, *, error: str | None = None):
        self.data["status"] = status
        self.data["finished_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            self.data["error"] = str(error)
        self._persist()
