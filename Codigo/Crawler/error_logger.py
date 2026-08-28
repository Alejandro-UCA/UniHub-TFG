import json
import logging
import os
import threading
import time
import contextlib
from datetime import datetime
from config import ERRORES_JSON
from checkpoint import atomic_json_dump

logger = logging.getLogger("crawler_error_logger")

class ErrorLogger:
    _lock = threading.Lock()

    def __init__(self, filepath=None):
        import config
        self.filepath = filepath or config.ERRORES_JSON
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
                logger.warning("No se pudo leer el registro de errores %s: %s", self.filepath, e)
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
        with ErrorLogger._lock, self._interprocess_lock():
            # Sincronizar si hubo cambios externos por mtime
            if os.path.exists(self.filepath):
                try:
                    curr_mtime = os.path.getmtime(self.filepath)
                    if curr_mtime != self._last_mtime:
                        fresh = self._load_errors()
                        if fresh:
                            self.errors = fresh
                except Exception as sync_error:
                    logger.debug("No se pudo resincronizar el registro de errores: %s", sync_error, exc_info=True)
            self.errors.append(entry)
            self._save_errors()

    @contextlib.contextmanager
    def _interprocess_lock(self, timeout: float = 15.0):
        """Bloqueo por archivo para que varios procesos no pierdan errores."""
        lock_path = self.filepath + ".lock"
        deadline = time.monotonic() + timeout
        acquired = False
        while time.monotonic() < deadline:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.05)
        if not acquired:
            raise TimeoutError(f"No se pudo adquirir bloqueo de errores: {lock_path}")
        try:
            yield
        finally:
            try:
                os.remove(lock_path)
            except OSError as cleanup_error:
                logger.debug("No se pudo eliminar el lock de errores %s: %s", lock_path, cleanup_error)

    def _save_errors(self):
        atomic_json_dump(self.errors, self.filepath)
        try:
            if os.path.exists(self.filepath):
                self._last_mtime = os.path.getmtime(self.filepath)
        except OSError as stat_error:
            logger.debug("No se pudo actualizar el mtime del registro de errores: %s", stat_error)
