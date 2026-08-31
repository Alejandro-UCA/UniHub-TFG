#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orquestador troncal de las cuatro partes de la Fase 1 de UniHub."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from typing import Iterable, Optional

import config
from checkpoint import CheckpointManager, atomic_json_dump
from config import LOGS_DIR, PLANES_DIR, TEMP_PDF_DIR, HTTP_CACHE_DIR, HTTP_CACHE_MAX_BYTES, TITULACIONES_JSON, TARGET_UNIVERSITY_CODES, HTTP_CLIENT_LOG_LEVEL
from fase1_parte1_ruct_boe import run_phase1_part1
from fase1_parte2_web_crawler import run_phase1_part2
from fase1_parte3_precios import run_phase1_part3
from fase1_parte4_asignaturas import run_phase1_part4
from metrics import PerformanceTracker
from phase_common import PHASE_DESCRIPTIONS, normalize_phase_selection, trigger_api_etl_sync
from crawl_ledger import CrawlLedger
from progress_emitter import ProgressEmitter
from run_manifest import RunManifest
from plan_quality_audit import audit_plan_records
from console_encoding import configure_console_encoding
from cancellation import (
    CrawlerCancelled,
    clear_shutdown,
    is_shutdown_requested,
    raise_if_shutdown_requested,
    request_shutdown,
)

configure_console_encoding()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
_http_log_level = getattr(logging, HTTP_CLIENT_LOG_LEVEL, logging.WARNING)
for _http_logger_name in ("httpx", "httpx2", "httpcore", "httpcore2"):
    logging.getLogger(_http_logger_name).setLevel(_http_log_level)
logger = logging.getLogger("main_fase_1")

_active_metrics: Optional[PerformanceTracker] = None
_active_checkpoint: Optional[CheckpointManager] = None
_active_progress: Optional[ProgressEmitter] = None
_active_manifest: Optional[RunManifest] = None
_active_log_handler: Optional[logging.Handler] = None


class _JsonLinesFormatter(logging.Formatter):
    """Formato estructurado, estable y legible por herramientas de auditoría."""

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_run_log(run_id: str, path: str | None = None) -> logging.Handler:
    """Añade un log JSONL por ejecución sin duplicar handlers entre runs."""
    global _active_log_handler
    root = logging.getLogger()
    if _active_log_handler is not None:
        root.removeHandler(_active_log_handler)
        _active_log_handler.close()
    path = path or os.path.join(LOGS_DIR, f"fase1_{run_id}.jsonl")
    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(_JsonLinesFormatter())
    root.addHandler(handler)
    _active_log_handler = handler
    logger.info("Log estructurado iniciado para la ejecución %s", run_id)
    return handler


def _flush_run_log() -> None:
    if _active_log_handler is not None:
        try:
            _active_log_handler.flush()
        except Exception:
            logger.debug("No se pudo vaciar el log estructurado", exc_info=True)


def handle_shutdown(signum, _frame):
    """Solicita una parada cooperativa sin abortar antes de cerrar el manifiesto."""
    logger.warning("Señal %s recibida; solicitando cancelación segura.", signum)
    request_shutdown()
    if _active_metrics is not None:
        _active_metrics.save()
    if _active_checkpoint is not None:
        _active_checkpoint.flush()
    if _active_progress is not None:
        _active_progress.set_cancelled()
    _flush_run_log()
    if _active_manifest is not None and _active_manifest.data.get("status") == "running":
        _active_manifest.finish("cancelled", error=f"Cancelación solicitada por señal {signum}")


def _run_part(
    part: int,
    *,
    limit_universities: Optional[int],
    limit_degrees: Optional[int],
    force: bool,
    workers: Optional[int],
    metrics: PerformanceTracker,
    progress: ProgressEmitter,
    robots_denied_university_codes: Optional[set[str]] = None,
) -> dict:
    """Invoca cualquier parte usando el contrato común de la migración."""
    runners = {
        1: run_phase1_part1,
        2: run_phase1_part2,
        3: run_phase1_part3,
        4: run_phase1_part4,
    }
    runner_kwargs = {
        "limit_universities": limit_universities,
        "limit_degrees": limit_degrees,
        "force": force,
        "max_workers": workers,
        "metrics_tracker": metrics,
        "progress_emitter": progress,
    }
    if part == 4:
        runner_kwargs["robots_denied_university_codes"] = robots_denied_university_codes or set()
    result = runners[part](**runner_kwargs)
    return result if isinstance(result, dict) else {"status": "completed"}


def run_phase1(
    parts: Optional[Iterable[int]] = None,
    *,
    limit_universities: Optional[int] = None,
    limit_degrees: Optional[int] = None,
    force: bool = False,
    workers: Optional[int] = None,
    sync_etl: bool = True,
    continue_on_error: bool = True,
) -> dict:
    """Ejecuta, en orden, las partes seleccionadas de la Fase 1.

    Todas las partes reciben la misma configuración de ejecución, el mismo
    recolector de métricas y el mismo emisor de progreso. Un error se registra
    por parte y, por defecto, no destruye el trabajo ya completado.
    """
    global _active_metrics, _active_checkpoint, _active_progress, _active_manifest, _active_log_handler

    selected_parts = normalize_phase_selection(parts)
    clear_shutdown()
    os.makedirs(PLANES_DIR, exist_ok=True)
    os.makedirs(TEMP_PDF_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    RunManifest.recover_orphaned_manifests()

    metrics = PerformanceTracker()
    progress = ProgressEmitter()
    checkpoint = CheckpointManager()
    _active_metrics = metrics
    _active_checkpoint = checkpoint
    _active_progress = progress

    started_at = time.time()
    results: dict = {"parts_requested": selected_parts, "parts": {}}
    manifest = RunManifest(
        parts=selected_parts,
        limit_universities=limit_universities,
        limit_degrees=limit_degrees,
        force=force,
        workers=workers,
    )
    _active_manifest = manifest
    results["run_id"] = manifest.start()
    run_artifacts = config.get_run_artifact_paths(results["run_id"])
    # Un run nunca hereda errores de una campaña anterior. El JSON histórico
    # queda como compatibilidad; el estado operativo vive en esta carpeta.
    config.ERRORES_JSON = run_artifacts["errors"]
    atomic_json_dump([], config.ERRORES_JSON)
    set_metrics_context = getattr(metrics, "set_run_context", None)
    if callable(set_metrics_context):
        set_metrics_context(
            results["run_id"],
            filepath=run_artifacts["performance"],
            latest_filepath=config.ESTADISTICAS_JSON,
        )
    run_artifacts["manifest"] = manifest.path
    record_artifacts = getattr(manifest, "record_artifacts", None)
    if callable(record_artifacts):
        record_artifacts(run_artifacts)
    _configure_run_log(results["run_id"], run_artifacts["structured_log"])
    failed_parts = []
    skipped_parts = []
    partial_parts = []
    robots_denied_for_following_parts: set[str] = set()

    print("\n" + "=" * 76)
    print("                 UNIHUB · PIPELINE DE FASE 1")
    print("=" * 76)

    try:
        for part in selected_parts:
            if is_shutdown_requested():
                break
            description = PHASE_DESCRIPTIONS[part]
            progress.update_part(part, description)
            record_part_progress = getattr(manifest, "record_part_progress", None)
            if callable(record_part_progress):
                record_part_progress(part)
            print(f"\n>>> PARTE {part}: {description}")
            part_started_at = time.time()

            try:
                part_result = _run_part(
                    part,
                    limit_universities=limit_universities,
                    limit_degrees=limit_degrees,
                    force=force,
                    workers=workers,
                    metrics=metrics,
                    progress=progress,
                    robots_denied_university_codes=robots_denied_for_following_parts,
                )
                status = part_result.get("status", "completed")
                part_result["status"] = status
                if part in (1, 2, 4):
                    part_result["plan_audit"] = audit_plan_records(
                        PLANES_DIR,
                        TITULACIONES_JSON,
                        TARGET_UNIVERSITY_CODES,
                    )
            except (KeyboardInterrupt, CrawlerCancelled) as exc:
                request_shutdown()
                part_result = {"status": "cancelled", "error": str(exc) or "Cancelación solicitada"}
                status = "cancelled"
            except Exception as exc:
                logger.exception("La Parte %s terminó con error", part)
                part_result = {"status": "failed", "error": str(exc)}
                status = "failed"

            part_result["duration_seconds"] = round(time.time() - part_started_at, 2)
            results["parts"][f"parte{part}"] = part_result
            record_metrics_part = getattr(metrics, "record_part_result", None)
            if callable(record_metrics_part):
                record_metrics_part(part, part_result, part_result["duration_seconds"])
            manifest.record_part(part, part_result)
            if part == 2:
                robots_denied_for_following_parts = {
                    str(code).zfill(3)
                    for code in (part_result.get("robots_denied_university_codes") or [])
                    if str(code).strip()
                }

            if status == "failed":
                failed_parts.append(part)
                if not continue_on_error:
                    break
            elif status == "skipped":
                skipped_parts.append(part)
            elif status == "partial":
                partial_parts.append(part)
            elif status == "cancelled":
                request_shutdown()
                break

        completed_count = len(results["parts"]) - len(failed_parts) - len(skipped_parts)
        if is_shutdown_requested():
            final_status = "cancelled"
            results["cancelled_parts"] = [part for part in selected_parts if part not in results["parts"]]
            results["etl_sync"] = {"status": "skipped", "reason": "cancelled"}
            manifest.record_etl_sync(results["etl_sync"])
            progress.set_cancelled()
        elif sync_etl and not failed_parts and not partial_parts and completed_count > 0:
            etl_succeeded = trigger_api_etl_sync()
            results["etl_sync"] = {"status": "completed" if etl_succeeded else "failed"}
        else:
            results["etl_sync"] = {"status": "skipped"}
        manifest.record_etl_sync(results["etl_sync"])

        if is_shutdown_requested():
            final_status = "cancelled"
            progress.set_cancelled()
        elif failed_parts:
            final_status = "failed" if len(failed_parts) == len(results["parts"]) else "partial"
            progress.set_failed(f"Fallaron las partes: {failed_parts}")
        elif skipped_parts or partial_parts:
            final_status = "skipped" if skipped_parts and len(skipped_parts) == len(results["parts"]) else "partial"
            progress.set_partial(f"Partes incompletas/omitidas: partial={partial_parts}, skipped={skipped_parts}")
        elif results["etl_sync"]["status"] == "failed":
            # Los ficheros del crawler aún no se han cargado en la API: la
            # campaña no puede declararse completada hasta que eso ocurra.
            final_status = "partial"
            progress.set_failed("Las partes terminaron, pero falló la sincronización ETL con la API")
        else:
            final_status = "completed"
            progress.set_finished()

        results["status"] = final_status
        results["failed_parts"] = failed_parts
        results["skipped_parts"] = skipped_parts
        results["partial_parts"] = partial_parts
        results["total_pipeline_duration_seconds"] = round(time.time() - started_at, 2)
        manifest.finish(final_status)
        return results
    finally:
        try:
            CrawlLedger.prune_http_cache(HTTP_CACHE_DIR, HTTP_CACHE_MAX_BYTES)
        except (OSError, IOError):
            logger.exception("No se pudo podar la caché HTTP")
        checkpoint.flush()
        metrics.save()
        if manifest.data.get("status") == "running":
            manifest.finish(
                "cancelled" if is_shutdown_requested() else "interrupted",
                error="Cancelación solicitada antes de completar el manifiesto" if is_shutdown_requested() else None,
            )
        _flush_run_log()
        if _active_log_handler is not None:
            root_logger = logging.getLogger()
            root_logger.removeHandler(_active_log_handler)
            _active_log_handler.close()
            _active_log_handler = None
        _active_checkpoint = None
        _active_metrics = None
        _active_progress = None
        _active_manifest = None


def run_all_phase1(
    limit_univ: Optional[int] = None,
    limit_deg: Optional[int] = None,
    force: bool = False,
    workers: Optional[int] = None,
    **kwargs,
) -> dict:
    """Compatibilidad: ejecuta las cuatro partes de la Fase 1."""
    return run_phase1(
        parts=(1, 2, 3, 4),
        limit_universities=limit_univ,
        limit_degrees=limit_deg,
        force=force,
        workers=workers,
        **kwargs,
    )


def run_crawler(
    limit_univ: Optional[int] = None,
    limit_degrees: Optional[int] = None,
    run_parts: Optional[Iterable[int]] = None,
    force: bool = False,
    workers: Optional[int] = None,
    **kwargs,
) -> dict:
    """Nombre histórico conservado para scripts, Docker y tests existentes."""
    return run_phase1(
        parts=run_parts,
        limit_universities=limit_univ,
        limit_degrees=limit_degrees,
        force=force,
        workers=workers,
        **kwargs,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="UniHub - Orquestador de la Fase 1")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="Ejecutar las cuatro partes (valor predeterminado).")
    selection.add_argument("--parte", type=int, choices=(1, 2, 3, 4), help="Ejecutar una sola parte.")
    selection.add_argument("--parts", type=int, nargs="+", choices=(1, 2, 3, 4), help="Ejecutar varias partes en orden.")
    parser.add_argument("--limit-univ", type=int, default=None)
    parser.add_argument("--limit-deg", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-sync-etl", action="store_true", help="No solicitar la sincronización ETL final.")
    parser.add_argument("--stop-on-error", action="store_true", help="Detenerse en el primer error de una parte.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    args = parse_args(argv)
    parts = [args.parte] if args.parte else args.parts
    result = run_phase1(
        parts=parts,
        limit_universities=args.limit_univ,
        limit_degrees=args.limit_deg,
        force=args.force,
        workers=args.workers,
        sync_etl=not args.no_sync_etl,
        continue_on_error=not args.stop_on_error,
    )
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
