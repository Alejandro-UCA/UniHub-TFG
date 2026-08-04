import os
import json
import time
import threading
import psutil
from datetime import datetime
from config import ESTADISTICAS_JSON
from checkpoint import atomic_json_dump

class PerformanceTracker:
    """
    Tracks execution metrics: memory usage (RSS, Peak), computation time (CPU user+system),
    I/O & network wait time, request counts, and PDF parsing metrics.
    Saves results atomically to estadisticas_rendimiento.json.
    """
    _lock = threading.Lock()

    def __init__(self, filepath=ESTADISTICAS_JSON):
        self.filepath = filepath
        self.process = psutil.Process(os.getpid())
        
        # Timing start points
        self.start_wall_time = time.perf_counter()
        self.start_cpu_time = time.process_time()
        
        # Memory metrics
        self.peak_memory_bytes = self._get_current_memory_bytes()
        
        # Accumulated time counters
        self.total_io_network_time = 0.0
        self.total_pdf_parsing_time = 0.0
        
        # Counter metrics
        self.universidades_inspeccionadas = 0
        self.titulaciones_inspeccionadas = 0
        self.titulaciones_al_dia = 0
        self.titulaciones_descargadas_actualizadas = 0
        self.pdfs_parseados = 0
        self.errores_detectados = 0

    def _get_current_memory_bytes(self) -> int:
        try:
            return self.process.memory_info().rss
        except Exception:
            return 0

    def _update_peak_memory(self):
        current_mem = self._get_current_memory_bytes()
        if current_mem > self.peak_memory_bytes:
            self.peak_memory_bytes = current_mem

    def record_io_time(self, seconds: float):
        """Records time spent on network HTTP requests or disk I/O."""
        with PerformanceTracker._lock:
            self.total_io_network_time += seconds
            self._update_peak_memory()

    def record_pdf_parse_time(self, seconds: float):
        """Records time spent parsing PDF curricula."""
        with PerformanceTracker._lock:
            self.total_pdf_parsing_time += seconds
            self.pdfs_parseados += 1
            self._update_peak_memory()

    def generate_report(self) -> dict:
        """Generates a complete metrics report dictionary."""
        self._update_peak_memory()
        
        current_wall_time = time.perf_counter() - self.start_wall_time
        current_cpu_time = time.process_time() - self.start_cpu_time
        
        io_wait_time = max(0.0, current_wall_time - current_cpu_time)
        
        current_mem_mb = round(self._get_current_memory_bytes() / (1024 * 1024), 2)
        peak_mem_mb = round(self.peak_memory_bytes / (1024 * 1024), 2)
        
        avg_io_latency = (
            round(self.total_io_network_time / self.titulaciones_inspeccionadas, 3)
            if self.titulaciones_inspeccionadas > 0 else 0.0
        )
        avg_pdf_parse_latency = (
            round(self.total_pdf_parsing_time / self.pdfs_parseados, 3)
            if self.pdfs_parseados > 0 else 0.0
        )

        return {
            "timestamp_reporte": datetime.now().isoformat(),
            "rendimiento_memoria": {
                "uso_memoria_actual_mb": current_mem_mb,
                "pico_maximo_memoria_mb": peak_mem_mb,
                "porcentaje_uso_memoria_sistema": round(self.process.memory_percent(), 2)
            },
            "rendimiento_tiempo": {
                "tiempo_total_ejecucion_seg": round(current_wall_time, 2),
                "tiempo_procesamiento_cpu_seg": round(current_cpu_time, 2),
                "tiempo_espera_io_red_seg": round(io_wait_time, 2),
                "tiempo_especifico_descargas_http_seg": round(self.total_io_network_time, 2),
                "tiempo_especifico_parseo_pdf_seg": round(self.total_pdf_parsing_time, 2)
            },
            "operaciones_crawler": {
                "universidades_inspeccionadas": self.universidades_inspeccionadas,
                "titulaciones_inspeccionadas": self.titulaciones_inspeccionadas,
                "titulaciones_al_dia_sin_cambios": self.titulaciones_al_dia,
                "titulaciones_nuevas_o_actualizadas": self.titulaciones_descargadas_actualizadas,
                "pdfs_boe_descargados_y_parseados": self.pdfs_parseados,
                "errores_registrados": self.errores_detectados
            },
            "promedios_rendimiento": {
                "promedio_tiempo_io_por_titulacion_seg": avg_io_latency,
                "promedio_tiempo_parseo_por_pdf_seg": avg_pdf_parse_latency
            }
        }

    def save(self):
        """Saves current metrics report atomically to estadisticas_rendimiento.json."""
        with PerformanceTracker._lock:
            report = self.generate_report()
            atomic_json_dump(report, self.filepath)
