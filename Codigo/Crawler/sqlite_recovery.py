"""Recuperación segura de bases SQLite dañadas.

Una base corrupta no se elimina: se aparta con un nombre único y el
componente puede crear una base nueva. Así se conserva evidencia para
auditoría y se evita bloquear toda la ejecución del crawler.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone


_CORRUPTION_MARKERS = (
    "file is not a database",
    "database disk image is malformed",
    "malformed database schema",
    "unsupported file format",
)


def is_sqlite_corruption(error: Exception) -> bool:
    """Distingue corrupción del fichero de bloqueos o rutas no utilizables."""
    if not isinstance(error, sqlite3.DatabaseError):
        return False
    message = str(error).lower()
    return any(marker in message for marker in _CORRUPTION_MARKERS)


def quarantine_corrupt_sqlite(db_path: str) -> str | None:
    """Mueve una SQLite corrupta y sus ficheros WAL a cuarentena recuperable."""
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
