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

        # Advanced & Green IT metrics
        self.total_bytes_pdf_downloaded = 0
        self.total_bytes_json_written = 0
        self.cache_hits = 0
        self.domain_latencies = {}

    def _get_current_memory_bytes(self) -> int:
        try:
            return self.process.memory_info().rss
        except Exception:
            return 0

    def _update_peak_memory(self):
        current_mem = self._get_current_memory_bytes()
        if current_mem > self.peak_memory_bytes:
            self.peak_memory_bytes = current_mem

    def inc_universidades(self, delta: int = 1):
        with PerformanceTracker._lock:
            self.universidades_inspeccionadas += delta

    def inc_titulaciones(self, delta: int = 1):
        with PerformanceTracker._lock:
            self.titulaciones_inspeccionadas += delta

    def inc_titulaciones_al_dia(self, delta: int = 1):
        with PerformanceTracker._lock:
            self.titulaciones_al_dia += delta

    def inc_titulaciones_descargadas(self, delta: int = 1):
        with PerformanceTracker._lock:
            self.titulaciones_descargadas_actualizadas += delta

    def inc_errores(self, delta: int = 1):
        with PerformanceTracker._lock:
            self.errores_detectados += delta

    def record_io_time(self, seconds: float, domain: str = "educacion.gob.es", bytes_transferred: int = 0):
        """Registra el tiempo de I/O de red, volumen transferido y latencia por dominio."""
        with PerformanceTracker._lock:
            self.total_io_network_time += seconds
            self.total_bytes_pdf_downloaded += bytes_transferred
            if domain not in self.domain_latencies:
                self.domain_latencies[domain] = {"total_sec": 0.0, "count": 0}
            self.domain_latencies[domain]["total_sec"] += seconds
            self.domain_latencies[domain]["count"] += 1
            self._update_peak_memory()

    def record_cache_hit(self):
        """Registra una lectura resuelta por caché mtime."""
        with PerformanceTracker._lock:
            self.cache_hits += 1

    def record_json_written(self, bytes_count: int):
        """Registra bytes escritos en el disco para JSONs de planes de estudio."""
        with PerformanceTracker._lock:
            self.total_bytes_json_written += bytes_count

    def record_pdf_parse_time(self, seconds: float):
        """Registra el tiempo consumido procesando el plan de estudios PDF."""
        with PerformanceTracker._lock:
            self.total_pdf_parsing_time += seconds
            self.pdfs_parseados += 1
            self._update_peak_memory()

    def generate_report(self) -> dict:
        """Genera un informe completo de métricas de rendimiento y sostenibilidad."""
        with PerformanceTracker._lock:
            self._update_peak_memory()
            
            current_wall_time = time.perf_counter() - self.start_wall_time
            current_cpu_time = time.process_time() - self.start_cpu_time
            
            io_wait_time = round(self.total_io_network_time, 2)
            
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

            hit_ratio_pct = (
                round((self.cache_hits / self.titulaciones_inspeccionadas) * 100, 2)
                if self.titulaciones_inspeccionadas > 0 else 0.0
            )

            compression_ratio = (
                round(self.total_bytes_pdf_downloaded / self.total_bytes_json_written, 2)
                if self.total_bytes_json_written > 0 else 1.0
            )

            # Estimación Huella de Carbono Green IT (~0.05 gCO2 / MB procesado)
            mb_total_processed = (self.total_bytes_pdf_downloaded + self.total_bytes_json_written) / (1024 * 1024)
            estimated_gco2 = round(mb_total_processed * 0.05, 3)

            domain_summary = {}
            for dom, ddata in self.domain_latencies.items():
                if ddata["count"] > 0:
                    domain_summary[dom] = round(ddata["total_sec"] / ddata["count"], 3)

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
                    "tiempo_espera_io_red_seg": io_wait_time,
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
                "metricas_avanzadas": {
                    "hit_ratio_cache_porcentaje": hit_ratio_pct,
                    "tasa_compresion_pdf_vs_json": compression_ratio,
                    "huella_carbono_estimada_gco2": estimated_gco2,
                    "latencias_medias_por_dominio_seg": domain_summary
                },
                "promedios_rendimiento": {
                    "promedio_tiempo_io_por_titulacion_seg": avg_io_latency,
                    "promedio_tiempo_parseo_por_pdf_seg": avg_pdf_parse_latency
                }
            }

    def save(self):
        """Saves current metrics report atomically to estadisticas_rendimiento.json."""
        report = self.generate_report()
        atomic_json_dump(report, self.filepath)
