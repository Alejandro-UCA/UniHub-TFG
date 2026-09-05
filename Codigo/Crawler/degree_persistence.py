"""Fachada de compatibilidad hacia atrás para utils.degree_persistence."""

from __future__ import annotations

import sys
import utils.degree_persistence as _mod

globals().update({k: v for k, v in _mod.__dict__.items() if not (k.startswith("__") and k.endswith("__"))})
sys.modules[__name__] = _mod
