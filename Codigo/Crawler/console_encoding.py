"""Configuración portable de la salida de consola del crawler.

Las universidades pueden publicar nombres con Unicode completo y el crawler
también emite diagnósticos que contienen esos valores. En Windows la consola
puede seguir usando una página de códigos heredada; ``backslashreplace`` evita
que un mensaje de diagnóstico cause una excepción dentro de ``logging``.
"""
from __future__ import annotations

import sys
from typing import Iterable, TextIO


def configure_console_encoding(streams: Iterable[TextIO] | None = None) -> None:
    """Configura stdout/stderr en UTF-8 sin fallar en streams embebidos.

    Algunos runners de pruebas y contenedores exponen streams sin
    ``reconfigure``. En ese caso se conserva el stream y la función permanece
    deliberadamente fail-open: la persistencia estructurada sigue funcionando.
    """
    targets = tuple(streams) if streams is not None else (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            # No convertir una limitación del terminal en un fallo del crawler.
            continue
