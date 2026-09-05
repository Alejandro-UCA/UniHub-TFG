"""Fachada de compatibilidad hacia atrás para extractors.subject_guides."""

from __future__ import annotations

import sys
import extractors.subject_guides as _mod

globals().update({k: v for k, v in _mod.__dict__.items() if not (k.startswith("__") and k.endswith("__"))})
sys.modules[__name__] = _mod
