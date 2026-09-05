"""Fachada de compatibilidad hacia atrás para parsers.spa_engine."""

from __future__ import annotations

import sys
import parsers.spa_engine as _mod

globals().update({k: v for k, v in _mod.__dict__.items() if not (k.startswith("__") and k.endswith("__"))})
sys.modules[__name__] = _mod
