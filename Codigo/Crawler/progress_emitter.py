import time
import logging
import requests
import threading
import queue
from datetime import datetime
from config import (
    ADMIN_API_KEY,
    API_PROGRESS_URL,
    PROGRESS_JSON,
    PROGRESS_POST_TIMEOUT_SECONDS,
)
from checkpoint import atomic_json_dump

logger = logging.getLogger('ProgressEmitter')

PROGRESS_JSON_PATH = PROGRESS_JSON


class ProgressEmitter:
    """
    Emisor de eventos y estado en tiempo real del Crawler (Fase 1).
    Persiste atómicamente el estado en 'progreso_en_vivo.json' y notifica
    de forma no bloqueante a los endpoints de administración de la API REST.
    """
    _lock = threading.RLock()

    def __init__(self, output_path: str = PROGRESS_JSON_PATH, api_sync_urls: list = None):
        self.output_path = output_path
        if api_sync_urls is None:
            self.api_sync_urls = [API_PROGRESS_URL] if API_PROGRESS_URL else []
        else:
            self.api_sync_urls = list(api_sync_urls)
        self.state = {
            'timestamp': datetime.now().isoformat(),
            'estado': 'INICIANDO',
            'fase': 'Fase 1 - Crawler UniHub',
            'parte_activa': 1,
            'parte_descripcion': 'Inicializando rastreador...',
            'universidad': {
                'codigo': '',
                'nombre': '',
                'indice': 0,
                'total': 0
            },
            'titulacion': {
                'codigo': '',
                'titulo': '',
                'indice': 0,
                'total': 0,
                'estado': ''
            },
            'porcentaje_global': 0.0,
            'metricas': {
                'universidades_completadas': 0,
                'titulaciones_inspeccionadas': 0,
                'titulaciones_actualizadas': 0,
                'pdfs_parseados': 0,
                'errores': 0,
                'incidencias_controladas': 0
            },
            'mensaje': 'Listo para iniciar.'
        }
        self._last_emit_time = 0.0
        self._emit_interval = 0.3

        self._queue = queue.Queue(maxsize=16)
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _worker_loop(self):
        while True:
            payload = self._queue.get()
            if payload is None:
                break
            
            api_key = ADMIN_API_KEY
            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['X-API-Key'] = api_key
            for target_url in self.api_sync_urls:
                try:
                    resp = requests.post(
                        target_url,
                        json=payload,
                        headers=headers,
                        timeout=PROGRESS_POST_TIMEOUT_SECONDS,
                    )
                    if resp.ok:
                        break
                except Exception as error:
                    logger.debug("No se pudo publicar el progreso en la API: %s", error, exc_info=True)

    def close(self):
        try:
            self._queue.put(None)
            self._worker_thread.join(timeout=2.0)
        except Exception as e:
            logger.debug(f"Error al cerrar worker de progress emitter: {e}")

    def update_part(self, part_num: int, description: str):
        with self._lock:
            self.state['parte_activa'] = part_num
            self.state['parte_descripcion'] = description
            self.state['estado'] = 'EJECUTANDO'
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=True)

    def update_university(self, u_idx: int, total_univ: int, u_code: str, u_name: str, u_tipo: str = '', force: bool = True):
        with self._lock:
            self.state['universidad'] = {
                'codigo': u_code,
                'nombre': u_name,
                'tipo': u_tipo,
                'indice': u_idx,
                'total': total_univ
            }
            if total_univ > 0:
                self.state['porcentaje_global'] = round((u_idx / total_univ) * 100.0, 1)
            self.state['mensaje'] = f'Procesando ({u_idx}/{total_univ}): [{u_code}] {u_name}'
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=force)

    def update_degree(self, d_idx: int, total_deg: int, d_code: str, d_title: str, status_msg: str = '', force: bool = False):
        with self._lock:
            self.state['titulacion'] = {
                'codigo': d_code,
                'titulo': d_title,
                'indice': d_idx,
                'total': total_deg,
                'estado': status_msg
            }
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=force)

    def flush_now(self):
        self._flush(force=True)

    def update_metrics(self, univ_done: int = None, deg_inspected: int = None, deg_updated: int = None, pdfs_parsed: int = None, errors: int = None, controlled_incidents: int = None):
        with self._lock:
            m = self.state['metricas']
            if univ_done is not None:
                m['universidades_completadas'] = univ_done
            if deg_inspected is not None:
                m['titulaciones_inspeccionadas'] = deg_inspected
            if deg_updated is not None:
                m['titulaciones_actualizadas'] = deg_updated
            if pdfs_parsed is not None:
                m['pdfs_parseados'] = pdfs_parsed
            if errors is not None:
                m['errores'] = errors
            if controlled_incidents is not None:
                m['incidencias_controladas'] = controlled_incidents
        self._flush()

    def set_finished(self, summary_msg: str = 'Rastreo finalizado con éxito.'):
        with self._lock:
            self.state['estado'] = 'FINALIZADO'
            self.state['porcentaje_global'] = 100.0
            self.state['mensaje'] = summary_msg
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=True)

    def set_failed(self, summary_msg: str = 'Rastreo finalizado con errores.'):
        with self._lock:
            self.state['estado'] = 'ERROR'
            self.state['mensaje'] = summary_msg
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=True)

    def set_cancelled(self, summary_msg: str = 'Rastreo cancelado; el progreso se puede reanudar.'):
        with self._lock:
            self.state['estado'] = 'CANCELADO'
            self.state['mensaje'] = summary_msg
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=True)

    def emit(self, **event):
        """Compatibilidad con el emisor empleado antes de modularizar la Fase 1."""
        with self._lock:
            if event.get('parte') is not None:
                self.state['parte_activa'] = event['parte']
            self.state['estado'] = event.get('estado', 'EJECUTANDO')
            total_univ = int(event.get('total_universidades') or 0)
            completed = int(event.get('universidades_completadas') or 0)
            self.state['universidad'].update({
                'codigo': event.get('universidad_actual_codigo', ''),
                'nombre': event.get('universidad_actual_nombre', ''),
                'indice': completed,
                'total': total_univ,
            })
            if total_univ:
                self.state['porcentaje_global'] = round((completed / total_univ) * 100.0, 1)
            self.state['timestamp'] = datetime.now().isoformat()
        self._flush(force=True)

    def _flush(self, force: bool = False):
        now = time.time()
        if not force and (now - self._last_emit_time) < self._emit_interval:
            return
        self._last_emit_time = now

        with self._lock:
            snapshot = dict(self.state)
            snapshot['timestamp'] = datetime.now().isoformat()

        # 1. Escritura atómica en archivo local para monitorización rápida
        try:
            atomic_json_dump(snapshot, self.output_path)
        except Exception as e:
            logger.debug(f'Error al persistir progreso en vivo: {e}')

        # 2. Notificación HTTP no bloqueante opcional a la API REST
        if self.api_sync_urls:
            try:
                self._queue.put_nowait(snapshot)
            except queue.Full:
                pass
