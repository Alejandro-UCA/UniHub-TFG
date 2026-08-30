"""Diagnóstico y recuperación reversible de cachés SQLite.

SQLite es una optimización del crawler; el estado canónico también se guarda
en JSON. Este módulo permite reparar una base ilegible de forma explícita,
conservando siempre el fichero original y sus acompañantes WAL/SHM.
"""

from __future__ import annotations

import os
import argparse
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone

from config import SQLITE_CONNECT_TIMEOUT


def inspect_sqlite_database(path: str) -> dict:
    """Devuelve un diagnóstico serializable sin modificar la base de datos."""
    result = {
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
            timeout=SQLITE_CONNECT_TIMEOUT,
        )
        result["integrity"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
        result["readable"] = True
        result["tables"] = [
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    except (OSError, sqlite3.Error) as error:
        result["error"] = str(error)
    finally:
        if connection is not None:
            connection.close()
    return result


def quarantine_corrupt_sqlite(path: str, backup_dir: str | None = None) -> dict:
    """Aparta una SQLite corrupta y crea una base vacía en su ubicación.

    La operación sólo procede si el diagnóstico confirma que el fichero existe
    pero no puede leerse. El original, ``-wal`` y ``-shm`` se mueven juntos a
    una carpeta de respaldo con nombre único; por tanto la recuperación es
    reversible y no sobreescribe una copia anterior.
    """
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

    # Los consumidores crean su esquema al arrancar. Dejamos una SQLite
    # válida y vacía para que el siguiente proceso no entre automáticamente en
    # modo degradado.
    connection = sqlite3.connect(source)
    connection.close()
    return {
        "original": source,
        "backup_base": backup_base,
        "moved_files": moved,
        "diagnosis": diagnosis,
        "recreated": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnostica o aparta una caché SQLite corrupta de forma reversible")
    parser.add_argument("path", help="Ruta exacta de la base SQLite")
    parser.add_argument("--repair", action="store_true", help="Mover la base corrupta y crear una SQLite vacía válida")
    parser.add_argument("--backup-dir", default=None, help="Directorio para la copia de respaldo")
    arguments = parser.parse_args()
    if arguments.repair:
        output = quarantine_corrupt_sqlite(arguments.path, arguments.backup_dir)
    else:
        output = inspect_sqlite_database(arguments.path)
    print(json.dumps(output, ensure_ascii=False, indent=2))
