"""Motor canónico de inventario, respaldo y limpieza segura de datos de la Fase 1.

Distingue estrictamente entre:
1. Semillas Maestras de Entrada (universidades.json, titulaciones_universidad.json, precios_ccaa.json):
   INMUTABLES. Se preservan siempre y se respaldan antes de cualquier purga.
2. Artefactos Volátiles de Ejecución (planes_estudio/, cachés SQLite WAL/SHM, logs, checkpoints):
   PURGABLES. Se eliminan para permitir un arranque limpio desde cero.
"""

from __future__ import annotations

import os
import shutil
import hashlib
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("unihub_data_cleanup")

SEED_FILENAMES = frozenset({
    "universidades.json",
    "titulaciones_universidad.json",
    "precios_ccaa.json",
})

DISPOSABLE_DIRS = (
    "planes_estudio",
    "http_cache",
    "discovery_cache",
    "logs",
    "runs",
    "run_manifests",
    "history",
    "web_snapshots",
)

DISPOSABLE_FILE_PATTERNS = (
    "cache_guias_docentes.db",
    "cache_guias_docentes.db-wal",
    "cache_guias_docentes.db-shm",
    "crawl_ledger.sqlite3",
    "crawl_ledger.sqlite3-wal",
    "crawl_ledger.sqlite3-shm",
    "unihub_cache.sqlite3",
    "unihub_cache.sqlite3-wal",
    "unihub_cache.sqlite3-shm",
    "checkpoint.json",
    "progreso_en_vivo.json",
    "estadisticas_rendimiento.json",
    "errores_crawler.json",
)


def _file_sha256(filepath: str | Path) -> str:
    """Calcula el hash SHA-256 de un fichero para verificar su integridad."""
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def get_crawler_data_inventory(
    data_dir: str | Path | None = None,
    temp_pdf_dir: str | Path | None = None,
) -> dict:
    """Inspecciona y clasifica exhaustivamente todos los ficheros del entorno de datos."""
    if data_dir is None:
        from core.config import DATA_DIR
        data_dir = DATA_DIR
    if temp_pdf_dir is None:
        from core.config import TEMP_PDF_DIR
        temp_pdf_dir = TEMP_PDF_DIR

    data_path = Path(data_dir)
    temp_pdf_path = Path(temp_pdf_dir)

    seeds = {}
    disposable_files = []
    disposable_dirs = []
    other_items = []

    total_seed_bytes = 0
    total_disposable_bytes = 0

    if data_path.exists():
        for entry in data_path.iterdir():
            name = entry.name
            if name in SEED_FILENAMES:
                size = entry.stat().st_size if entry.is_file() else 0
                total_seed_bytes += size
                seeds[name] = {
                    "path": str(entry),
                    "size_bytes": size,
                    "sha256": _file_sha256(entry) if entry.is_file() else "",
                    "is_file": entry.is_file(),
                }
            elif name in DISPOSABLE_DIRS or name == "seed_backups":
                if entry.is_dir():
                    dir_size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                    total_disposable_bytes += dir_size
                    disposable_dirs.append({
                        "path": str(entry),
                        "name": name,
                        "size_bytes": dir_size,
                    })
            elif any(
                name == pat
                or name.startswith(pat + ".")
                or ".corrupt." in name
                or ".backup_before_repair" in name
                for pat in DISPOSABLE_FILE_PATTERNS
            ):
                size = entry.stat().st_size if entry.is_file() else 0
                total_disposable_bytes += size
                disposable_files.append({
                    "path": str(entry),
                    "name": name,
                    "size_bytes": size,
                })
            else:
                size = entry.stat().st_size if entry.is_file() else 0
                other_items.append({
                    "path": str(entry),
                    "name": name,
                    "size_bytes": size,
                    "is_dir": entry.is_dir(),
                })

    # Temp PDFs
    temp_pdf_bytes = 0
    temp_pdf_count = 0
    if temp_pdf_path.exists():
        for f in temp_pdf_path.rglob("*"):
            if f.is_file():
                sz = f.stat().st_size
                temp_pdf_bytes += sz
                temp_pdf_count += 1
        total_disposable_bytes += temp_pdf_bytes

    return {
        "data_dir": str(data_path),
        "temp_pdf_dir": str(temp_pdf_path),
        "seeds": seeds,
        "total_seed_bytes": total_seed_bytes,
        "disposable_files": disposable_files,
        "disposable_dirs": disposable_dirs,
        "other_items": other_items,
        "temp_pdfs": {
            "count": temp_pdf_count,
            "size_bytes": temp_pdf_bytes,
        },
        "total_disposable_bytes": total_disposable_bytes,
    }


def backup_seed_files(
    data_dir: str | Path | None = None,
    backup_root: str | Path | None = None,
) -> list[dict]:
    """Crea una copia de seguridad fechada e inmutable de las semillas maestras."""
    if data_dir is None:
        from core.config import DATA_DIR
        data_dir = DATA_DIR

    data_path = Path(data_dir)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    if backup_root is None:
        backup_dir = data_path / "seed_backups" / timestamp
    else:
        backup_dir = Path(backup_root) / timestamp

    backup_dir.mkdir(parents=True, exist_ok=True)
    backups_created = []

    for seed_name in sorted(SEED_FILENAMES):
        src = data_path / seed_name
        if src.exists() and src.is_file():
            dst = backup_dir / seed_name
            shutil.copy2(src, dst)
            backups_created.append({
                "seed": seed_name,
                "src": str(src),
                "dst": str(dst),
                "size_bytes": dst.stat().st_size,
                "sha256": _file_sha256(dst),
            })
            logger.info("Semilla respaldada: %s -> %s", seed_name, dst)

    return backups_created


def clean_crawler_runtime_data(
    data_dir: str | Path | None = None,
    temp_pdf_dir: str | Path | None = None,
    dry_run: bool = False,
    backup_seed: bool = True,
) -> dict:
    """Limpia de forma idempotente y segura todos los datos volátiles de ejecución.

    Garantiza que:
    1. Las semillas maestras NO se eliminan bajo ninguna circunstancia.
    2. Se realiza una copia de seguridad preventiva antes de proceder.
    3. Se eliminan diarios SQLite, bases de datos de guías, ledger y cachés.
    4. Se limpian cerrojos huérfanos del sistema.
    5. Se recrean los directorios canónicos vacíos listos para un arranque desde cero.
    """
    if data_dir is None:
        from core.config import DATA_DIR
        data_dir = DATA_DIR
    if temp_pdf_dir is None:
        from core.config import TEMP_PDF_DIR
        temp_pdf_dir = TEMP_PDF_DIR

    data_path = Path(data_dir)
    temp_pdf_path = Path(temp_pdf_dir)

    inventory = get_crawler_data_inventory(data_path, temp_pdf_path)

    # 1. Verificar presencia de semillas
    seed_report = []
    for seed_name in sorted(SEED_FILENAMES):
        seed_info = inventory["seeds"].get(seed_name)
        if seed_info and seed_info.get("size_bytes", 0) > 0:
            seed_report.append({
                "name": seed_name,
                "status": "intact",
                "size_bytes": seed_info["size_bytes"],
                "sha256": seed_info["sha256"],
            })
        else:
            seed_report.append({
                "name": seed_name,
                "status": "missing_or_empty",
                "size_bytes": 0,
                "sha256": "",
            })

    # 2. Respaldar semillas si no es dry_run
    backups = []
    if backup_seed and not dry_run:
        backups = backup_seed_files(data_path)

    deleted_files = []
    deleted_dirs = []
    freed_bytes = 0

    # 3. Eliminar ficheros volátiles
    for item in inventory["disposable_files"]:
        p = Path(item["path"])
        # Doble verificación: jamás borrar una semilla
        if p.name in SEED_FILENAMES:
            continue
        freed_bytes += item["size_bytes"]
        if not dry_run:
            try:
                if p.exists():
                    p.unlink(missing_ok=True)
                deleted_files.append(str(p))
            except OSError as err:
                logger.warning("No se pudo eliminar el fichero volátil %s: %s", p, err)
        else:
            deleted_files.append(str(p))

    # 4. Eliminar directorios volátiles
    for item in inventory["disposable_dirs"]:
        p = Path(item["path"])
        # No eliminar el directorio de seed_backups recién creado
        if p.name == "seed_backups":
            continue
        freed_bytes += item["size_bytes"]
        if not dry_run:
            try:
                if p.exists() and p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                deleted_dirs.append(str(p))
            except OSError as err:
                logger.warning("No se pudo eliminar el directorio volátil %s: %s", p, err)
        else:
            deleted_dirs.append(str(p))

    # 5. Vaciar temporales de PDFs
    if temp_pdf_path.exists():
        freed_bytes += inventory["temp_pdfs"]["size_bytes"]
        if not dry_run:
            for f in temp_pdf_path.iterdir():
                try:
                    if f.is_file():
                        f.unlink(missing_ok=True)
                    elif f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
                except OSError:
                    pass

    # 6. Limpiar lock ETL huérfano si existe
    etl_lock = Path(tempfile.gettempdir()) / "etl_running.lock"
    cleared_lock = False
    if etl_lock.exists() and not dry_run:
        try:
            etl_lock.unlink(missing_ok=True)
            cleared_lock = True
        except OSError:
            pass

    # 7. Recrear estructura vacía requerida para cold-start
    recreated_dirs = []
    if not dry_run:
        target_dirs = [
            data_path / "planes_estudio",
            data_path / "http_cache",
            data_path / "logs",
            data_path / "runs",
            temp_pdf_path,
        ]
        for d in target_dirs:
            d.mkdir(parents=True, exist_ok=True)
            recreated_dirs.append(str(d))

    return {
        "dry_run": dry_run,
        "seed_files_preserved": seed_report,
        "backups_created": backups,
        "files_deleted_count": len(deleted_files),
        "dirs_deleted_count": len(deleted_dirs),
        "bytes_freed": freed_bytes,
        "recreated_directories": recreated_dirs,
        "cleared_orphan_lock": cleared_lock,
    }
