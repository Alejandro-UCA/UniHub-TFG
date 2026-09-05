"""Diagnóstico, cuarentena y recuperación unificada de bases de datos SQLite dañadas.

Garantiza que cualquier base de datos SQLite corrupta se aísle de forma reversible
junto con sus ficheros WAL y SHM, preservando la evidencia forense sin bloquear
la ejecución de los procesos de rastreo e indexación.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

_CORRUPTION_MARKERS = (
    "file is not a database",
    "database disk image is malformed",
    "malformed database schema",
    "unsupported file format",
)


def is_sqlite_corruption(error: Exception) -> bool:
    """Distingue la corrupción física del fichero de bloqueos o errores de sintaxis."""
    if not isinstance(error, sqlite3.DatabaseError):
        return False
    message = str(error).lower()
    return any(marker in message for marker in _CORRUPTION_MARKERS)


def inspect_sqlite_database(path: str, timeout: float = 5.0) -> dict[str, Any]:
    """Realiza un diagnóstico de sólo lectura sin modificar la base de datos."""
    result: dict[str, Any] = {
        "path": os.path.abspath(path) if path else path,
        "exists": bool(path and os.path.exists(path)),
        "readable": False,
        "integrity": None,
        "tables": [],
        "error": None,
    }
    if not result["exists"]:
        return result

    connection = None
    try:
        connection = sqlite3.connect(
            f"file:{os.path.abspath(path)}?mode=ro",
            uri=True,
            timeout=timeout,
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        result["integrity"] = integrity[0] if integrity else "unknown"
        result["readable"] = True
        result["tables"] = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    except (OSError, sqlite3.Error) as error:
        result["error"] = str(error)
    finally:
        if connection is not None:
            connection.close()
    return result


def quarantine_corrupt_sqlite(db_path: str) -> str | None:
    """Mueve atómicamente una SQLite corrupta y sus ficheros WAL/SHM a cuarentena con nombre único.

    Devuelve la ruta a la que fue movida la base de datos o None si no existía.
    """
    if not db_path or db_path == ":memory:" or not os.path.isfile(db_path):
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    quarantine_path = f"{db_path}.corrupt.{stamp}.{uuid.uuid4().hex[:8]}"
    os.replace(db_path, quarantine_path)
    for suffix in ("-wal", "-shm"):
        companion = f"{db_path}{suffix}"
        if os.path.isfile(companion):
            os.replace(companion, f"{quarantine_path}{suffix}")
    return quarantine_path


def quarantine_and_recreate_sqlite(path: str, backup_dir: str | None = None) -> dict[str, Any]:
    """Aparta una base de datos corrupta y genera una base vacía limpia en su lugar."""
    diagnosis = inspect_sqlite_database(path)
    if not diagnosis["exists"]:
        raise FileNotFoundError(path)
    if diagnosis["readable"] and diagnosis["integrity"] == "ok":
        raise ValueError("La base SQLite es legible e íntegra; no se debe poner en cuarentena")

    source = os.path.abspath(path)
    parent = os.path.abspath(backup_dir or os.path.dirname(source))
    os.makedirs(parent, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    token = uuid.uuid4().hex[:10]
    backup_base = os.path.join(parent, f"{os.path.basename(source)}.corrupt.{stamp}.{token}")

    moved = []
    for suffix in ("", "-wal", "-shm"):
        candidate = source + suffix
        if not os.path.exists(candidate):
            continue
        target = backup_base + suffix
        shutil.move(candidate, target)
        moved.append(target)

    # Crear una SQLite válida y vacía
    conn = sqlite3.connect(source)
    conn.close()

    return {
        "original": source,
        "backup_base": backup_base,
        "moved_files": moved,
        "diagnosis": diagnosis,
        "recreated": True,
    }
