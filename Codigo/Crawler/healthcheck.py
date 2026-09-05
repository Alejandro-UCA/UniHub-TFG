#!/usr/bin/env python3
"""Comprueba que la última ejecución del crawler terminó correctamente."""

from __future__ import annotations

import glob
import json
import os
import sys
import time


def safe_getmtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except (FileNotFoundError, OSError):
        return 0.0


def main() -> int:
    manifests_dir = os.getenv("CRAWLER_RUN_MANIFESTS_DIR", "/app/Datos/run_manifests")
    manifests = glob.glob(os.path.join(manifests_dir, "*.json"))
    if not manifests:
        # Antes de la primera ejecución programada no hay manifiesto que
        # evaluar; Docker ya comprueba que el proceso cron siga vivo.
        return 0

    latest = max(manifests, key=safe_getmtime)
    try:
        with open(latest, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"No se pudo leer el manifiesto más reciente: {exc}", file=sys.stderr)
        return 1

    status = manifest.get("status")
    if status == "completed":
        return 0

    if status == "running":
        # Comprobar el latido en vivo (heartbeat) de progreso_en_vivo.json
        progress_path = os.path.join(os.path.dirname(latest), "..", "progreso_en_vivo.json")
        if os.path.exists(progress_path):
            try:
                if time.time() - os.path.getmtime(progress_path) <= 600:
                    return 0
            except OSError:
                pass

        max_running_age = float(os.getenv("CRAWLER_HEALTH_RUNNING_MAX_SECONDS", "86400"))
        if time.time() - os.path.getmtime(latest) <= max_running_age:
            return 0

    print(f"La última ejecución del crawler no está sana: status={status!r}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
