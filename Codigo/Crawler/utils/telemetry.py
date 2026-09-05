"""Fachada centralizada de telemetría, métricas, logs y manifiestos de ejecución."""

from __future__ import annotations

from core.error_logger import ErrorLogger
from core.metrics import PerformanceTracker
from core.progress import ProgressEmitter
from core.manifest import RunManifestManager

__all__ = [
    "ErrorLogger",
    "PerformanceTracker",
    "ProgressEmitter",
    "RunManifestManager",
]
