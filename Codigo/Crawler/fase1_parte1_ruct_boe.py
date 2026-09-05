"""Fachada de compatibilidad hacia atrás para pipelines.parte1_ruct_boe."""

from __future__ import annotations

import sys
import pipelines.parte1_ruct_boe as _mod

globals().update({k: v for k, v in _mod.__dict__.items() if not (k.startswith("__") and k.endswith("__"))})
sys.modules[__name__] = _mod

if __name__ == "__main__":
    if hasattr(_mod, "main"):
        _mod.main()
