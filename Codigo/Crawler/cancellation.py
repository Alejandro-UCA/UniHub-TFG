"""Señal cooperativa de cancelación para ejecuciones reanudables."""
from __future__ import annotations

import threading


class CrawlerCancelled(Exception):
    """Indica que una fase ha terminado de forma segura por petición externa."""


_shutdown_event = threading.Event()


def request_shutdown() -> None:
    _shutdown_event.set()


def clear_shutdown() -> None:
    _shutdown_event.clear()


def is_shutdown_requested() -> bool:
    return _shutdown_event.is_set()


def raise_if_shutdown_requested() -> None:
    if is_shutdown_requested():
        raise CrawlerCancelled("Cancelación solicitada; se conserva el progreso persistido")
