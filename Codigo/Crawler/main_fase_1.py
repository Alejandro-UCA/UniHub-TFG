#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orquestador troncal de las cuatro partes de la Fase 1 de UniHub."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import Iterable, Optional

from checkpoint import CheckpointManager
from config import LOGS_DIR, PLANES_DIR, TEMP_PDF_DIR, HTTP_CACHE_DIR, HTTP_CACHE_MAX_BYTES
from fase1_parte1_ruct_boe import run_phase1_part1
from fase1_parte2_web_crawler import run_phase1_part2
from fase1_parte3_precios import run_phase1_part3
from fase1_parte4_asignaturas import run_phase1_part4
from metrics import PerformanceTracker
from phase_common import PHASE_DESCRIPTIONS, normalize_phase_selection, trigger_api_etl_sync
from crawl_ledger import CrawlLedger
from progress_emitter import ProgressEmitter
from run_manifest import RunManifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main_fase_1")

_active_metrics: Optional[PerformanceTracker] = None
_active_checkpoint: Optional[CheckpointManager] = None


def handle_shutdown(signum, _frame):
    """Persiste el estado antes de finalizar por una señal del sistema."""
    logger.warning("Señal %s recibida; guardando métricas y checkpoints.", signum)
    if _active_metrics is not None:
        _active_metrics.save()
    if _active_checkpoint is not None:
        _active_checkpoint.flush()
    raise SystemExit(130)


def _run_part(
    part: int,
    *,
    limit_universities: Optional[int],
    limit_degrees: Optional[int],
    force: bool,
    workers: Optional[int],
    metrics: PerformanceTracker,
    progress: ProgressEmitter,
) -> dict:
    """Invoca cualquier parte usando el contrato común de la migración."""
    runners = {
        1: run_phase1_part1,
        2: run_phase1_part2,
        3: run_phase1_part3,
        4: run_phase1_part4,
    }
    result = runners[part](
        limit_universities=limit_universities,
        limit_degrees=limit_degrees,
        force=force,
        max_workers=workers,
        metrics_tracker=metrics,
        progress_emitter=progress,
    )
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
    global _active_metrics, _active_checkpoint

    selected_parts = normalize_phase_selection(parts)
    os.makedirs(PLANES_DIR, exist_ok=True)
    os.makedirs(TEMP_PDF_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    metrics = PerformanceTracker()
    progress = ProgressEmitter()
    checkpoint = CheckpointManager()
    _active_metrics = metrics
    _active_checkpoint = checkpoint

    started_at = time.time()
    results: dict = {"parts_requested": selected_parts, "parts": {}}
    manifest = RunManifest(
        parts=selected_parts,
        limit_universities=limit_universities,
        limit_degrees=limit_degrees,
        force=force,
        workers=workers,
    )
    results["run_id"] = manifest.start()
    failed_parts = []
    skipped_parts = []
    partial_parts = []

    print("\n" + "=" * 76)
    print("                 UNIHUB · PIPELINE DE FASE 1")
    print("=" * 76)

    try:
        for part in selected_parts:
            description = PHASE_DESCRIPTIONS[part]
            progress.update_part(part, description)
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
                )
                status = part_result.get("status", "completed")
                part_result["status"] = status
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.exception("La Parte %s terminó con error", part)
                part_result = {"status": "failed", "error": str(exc)}
                status = "failed"

            part_result["duration_seconds"] = round(time.time() - part_started_at, 2)
            results["parts"][f"parte{part}"] = part_result
            manifest.record_part(part, part_result)

            if status == "failed":
                failed_parts.append(part)
                if not continue_on_error:
                    break
            elif status == "skipped":
                skipped_parts.append(part)
            elif status == "partial":
                partial_parts.append(part)

        completed_count = len(results["parts"]) - len(failed_parts) - len(skipped_parts)
        if sync_etl and not failed_parts and not partial_parts and completed_count > 0:
            etl_succeeded = trigger_api_etl_sync()
            results["etl_sync"] = {"status": "completed" if etl_succeeded else "failed"}
        else:
            results["etl_sync"] = {"status": "skipped"}
        manifest.record_etl_sync(results["etl_sync"])

        if failed_parts:
            final_status = "failed" if len(failed_parts) == len(results["parts"]) else "partial"
            progress.set_failed(f"Fallaron las partes: {failed_parts}")
        elif skipped_parts or partial_parts:
            final_status = "skipped" if skipped_parts and len(skipped_parts) == len(results["parts"]) else "partial"
            progress.set_failed(f"Partes incompletas/omitidas: partial={partial_parts}, skipped={skipped_parts}")
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
        except Exception:
            logger.exception("No se pudo podar la caché HTTP")
        checkpoint.flush()
        metrics.save()
        if manifest.data.get("status") == "running":
            manifest.finish("interrupted")
        _active_checkpoint = None
        _active_metrics = None


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
