import json
import os
import threading
from datetime import datetime
from config import ERRORES_JSON
from checkpoint import atomic_json_dump

class ErrorLogger:
    _lock = threading.Lock()

    def __init__(self, filepath=ERRORES_JSON):
        self.filepath = filepath
        self._last_mtime = 0.0
        self.errors = self._load_errors()

    def _load_errors(self):
        if os.path.exists(self.filepath):
            try:
                mtime = os.path.getmtime(self.filepath)
                if hasattr(self, "errors") and self.errors and mtime == self._last_mtime:
                    return self.errors
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._last_mtime = mtime
                        return data
            except Exception as e:
                # Si falla la lectura transitoria, preservar los errores que ya tenemos en memoria
                if hasattr(self, "errors") and isinstance(self.errors, list) and self.errors:
                    return self.errors
                return []
        return []

    def log_error(self, phase: str, entity_id: str, url: str, reason: str, exception_details: str = None):
        """
        Logs a detailed error entry to the errors JSON file atomically.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "fase": phase,
            "id_entidad": entity_id,
            "url": url,
            "motivo_fallo": reason,
            "detalles_excepcion": exception_details or ""
        }
        with ErrorLogger._lock:
            # Sincronizar si hubo cambios externos por mtime
            if os.path.exists(self.filepath):
                try:
                    curr_mtime = os.path.getmtime(self.filepath)
                    if curr_mtime != self._last_mtime:
                        fresh = self._load_errors()
                        if fresh:
                            self.errors = fresh
                except Exception:
                    pass
            self.errors.append(entry)
            self._save_errors()

    def _save_errors(self):
        atomic_json_dump(self.errors, self.filepath)
        try:
            if os.path.exists(self.filepath):
                self._last_mtime = os.path.getmtime(self.filepath)
        except Exception:
            pass
