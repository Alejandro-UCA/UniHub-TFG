import json
import os
from datetime import datetime
from config import ERRORES_JSON
from checkpoint import atomic_json_dump

class ErrorLogger:
    def __init__(self, filepath=ERRORES_JSON):
        self.filepath = filepath
        self.errors = self._load_errors()

    def _load_errors(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
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
        self.errors.append(entry)
        self._save_errors()

    def _save_errors(self):
        atomic_json_dump(self.errors, self.filepath)
