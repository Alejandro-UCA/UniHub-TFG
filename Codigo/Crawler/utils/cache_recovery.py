"""Diagnóstico y recuperación reversible de cachés SQLite.

SQLite es una optimización del crawler; el estado canónico también se guarda
en JSON. Este módulo permite reparar una base ilegible de forma explícita,
conservando siempre el fichero original y sus acompañantes WAL/SHM.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from core.config import SQLITE_CONNECT_TIMEOUT
from utils.sqlite_recovery import (
    inspect_sqlite_database,
    is_sqlite_corruption,
    quarantine_and_recreate_sqlite,
)


def quarantine_corrupt_sqlite(path: str, backup_dir: str | None = None) -> dict:
    """Aparta una SQLite corrupta y crea una base vacía en su ubicación."""
    return quarantine_and_recreate_sqlite(path, backup_dir=backup_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Diagnostica o aparta una caché SQLite corrupta de forma reversible"
    )
    parser.add_argument("path", help="Ruta exacta de la base SQLite")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Mover la base corrupta y crear una SQLite vacía válida",
    )
    parser.add_argument(
        "--backup-dir", default=None, help="Directorio para la copia de respaldo"
    )
    arguments = parser.parse_args()
    if arguments.repair:
        output = quarantine_corrupt_sqlite(arguments.path, arguments.backup_dir)
    else:
        output = inspect_sqlite_database(arguments.path)
    print(json.dumps(output, ensure_ascii=False, indent=2))
