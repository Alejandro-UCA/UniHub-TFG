"""Fachada de compatibilidad hacia atrás para la configuración del Crawler.

Re-exporta todas las definiciones de core.config y sus diccionarios léxicos
asociados, asegurando compatibilidad 100% con suites de pruebas y scripts legados.
"""

from __future__ import annotations

import importlib
import core.config

# En caso de reload(config), recargar también el módulo subyacente core.config
importlib.reload(core.config)

from core.config import *
