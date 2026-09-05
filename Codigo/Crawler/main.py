#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Punto de entrada principal para el rastreador / crawler de UniHub (Fase 1)."""

from __future__ import annotations

import sys
from pathlib import Path

# Asegurar que el directorio raíz del crawler esté en sys.path
_crawler_root = str(Path(__file__).resolve().parent)
if _crawler_root not in sys.path:
    sys.path.insert(0, _crawler_root)

from pipelines.main import (
    main,
    run_all_phase1,
    run_crawler,
    run_phase1,
)

if __name__ == "__main__":
    raise SystemExit(main())
