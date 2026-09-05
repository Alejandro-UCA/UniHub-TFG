"""Fachada de compatibilidad hacia atrás para parsers.ruct_catalog."""

from __future__ import annotations

import sys
import parsers.ruct_catalog as _mod

globals().update({k: v for k, v in _mod.__dict__.items() if not (k.startswith("__") and k.endswith("__"))})
sys.modules[__name__] = _mod
