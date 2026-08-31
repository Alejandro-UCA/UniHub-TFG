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

    def __init__(self, filepath=None):
        import config
        self.filepath = filepath or config.ESTADISTICAS_JSON
        self.latest_filepath = None
        self.run_id = ""
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
        self.incidencias_controladas = 0

        # Advanced & Green IT metrics
        self.total_bytes_pdf_downloaded = 0
        self.total_bytes_json_written = 0
        self.cache_hits = 0
        self.request_memo_hits = 0
        self.domain_latencies = {}
        self.phase_durations = {}
        self.operation_counts_by_part = {}

    def set_run_context(self, run_id: str = "", filepath=None, latest_filepath=None):
        """Asocia el tracker a una ejecución y, opcionalmente, a dos salidas.

        ``filepath`` permite conservar estadísticas inmutables por ejecución;
        ``latest_filepath`` mantiene la ruta histórica de compatibilidad.
        """
        with PerformanceTracker._lock:
            self.run_id = str(run_id or "")
            if filepath:
                self.filepath = filepath
            self.latest_filepath = latest_filepath

    def record_part_result(self, part: int, result: dict | None, duration_seconds: float = 0.0):
        """Registra el trabajo real de una parte, aunque no use el tracker antiguo.

        Partes 2 y 4 ejecutan gran parte de su trabajo en workers y antes solo
        devolvían esos contadores al manifiesto; por eso el JSON de rendimiento
        quedaba con operaciones a cero. La consolidación es idempotente por
        parte para evitar doble conteo si el orquestador reintenta guardar.
        """
        result = result if isinstance(result, dict) else {}
        part_key = f"parte{int(part)}"
        with PerformanceTracker._lock:
            if part_key in self.operation_counts_by_part:
                return
            codes = result.get("university_codes_processed") or []
            universities = len(codes) if isinstance(codes, (list, tuple, set)) else int(result.get("universities_processed", 0) or 0)
            if int(part) == 4:
                inspected = int(result.get("plans_inspected", 0) or 0)
                updated = int(result.get("enriched_degrees", 0) or 0)
                current = int(result.get("cached_hits", 0) or 0)
            elif int(part) == 2:
                inspected = int(result.get("missing_degrees", 0) or 0) + int(result.get("resolved_degrees", 0) or 0)
                updated = int(result.get("resolved_degrees", 0) or 0) + int(result.get("propagated_degrees", 0) or 0)
                current = 0
            else:
                # Parte 1 ya alimenta los contadores históricos en tiempo real.
                inspected = int(result.get("total_enqueued", 0) or 0)
                updated = 0
                current = 0

            controlled = int(result.get("incidencias_controladas", 0) or 0)
            if int(part) == 2:
                controlled += int(result.get("robots_denied", 0) or 0)
            if int(part) == 4:
                controlled += sum(int(result.get(key, 0) or 0) for key in (
                    "guide_robots_denied", "guide_identity_rejected",
                    "guide_soft404_detected", "guide_soft404_route_skips",
                ))
            errors = int(result.get("errors", 0) or 0)
            counts = {
                "universidades": universities,
                "titulaciones_inspeccionadas": inspected,
                "titulaciones_actualizadas": updated,
                "titulaciones_al_dia": current,
                "errores": errors,
                "incidencias_controladas": controlled,
            }
            if int(part) == 4:
                counts.update({
                    key: int(result.get(key, 0) or 0)
                    for key in (
                        "guide_subjects_considered", "guide_candidate_urls_generated",
                        "guide_candidate_urls_requested", "guide_candidate_urls_pruned",
                        "guide_http_200", "guide_http_404", "guide_request_errors",
                    )
                })
            self.operation_counts_by_part[part_key] = counts
            self.phase_durations[part_key] = round(max(0.0, float(duration_seconds or 0.0)), 2)

            # Solo Partes 2 y 4 carecían de consolidación en tiempo real.
            if int(part) != 1:
                self.universidades_inspeccionadas += universities
                self.titulaciones_inspeccionadas += inspected
                self.titulaciones_descargadas_actualizadas += updated
                self.titulaciones_al_dia += current
                self.errores_detectados += errors
                self.incidencias_controladas += controlled

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

    def inc_incidencias_controladas(self, delta: int = 1):
        """Cuenta incidencias conocidas que no invalidan la ejecución.

        Ejemplo: una URL omitida porque una regla explícita de robots.txt
        prohíbe rastrearla. No se mezcla con los errores del pipeline.
        """
        with PerformanceTracker._lock:
            self.incidencias_controladas += delta

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

    def record_request_memo_hit(self):
        """Registra una petición HTTP evitada por deduplicación en memoria."""
        with PerformanceTracker._lock:
            self.request_memo_hits += 1

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

    def record_pdf_parse_aggregate(self, parsed_count: int = 0, seconds: float = 0.0):
        """Consolida parseos realizados dentro de workers sin contar actualizaciones."""
        with PerformanceTracker._lock:
            self.pdfs_parseados += max(0, int(parsed_count or 0))
            self.total_pdf_parsing_time += max(0.0, float(seconds or 0.0))
            self._update_peak_memory()

    def merge_worker_stats(self, parsed_count: int = 0, updated_count: int = 0, parse_time: float = 0.0):
        """Consolida de forma atómica las métricas devueltas por procesos CPU."""
        with PerformanceTracker._lock:
            self.pdfs_parseados += max(0, int(parsed_count or 0))
            self.titulaciones_descargadas_actualizadas += max(0, int(updated_count or 0))
            self.total_pdf_parsing_time += max(0.0, float(parse_time or 0.0))
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
                "run_id": self.run_id,
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
                    "errores_registrados": self.errores_detectados,
                    "incidencias_controladas": self.incidencias_controladas,
                },
                "operaciones_por_parte": self.operation_counts_by_part,
                "duracion_por_parte_seg": self.phase_durations,
                "metricas_avanzadas": {
                    "hit_ratio_cache_porcentaje": hit_ratio_pct,
                    "peticiones_http_duplicadas_evitadas": self.request_memo_hits,
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
        if self.latest_filepath and os.path.abspath(self.latest_filepath) != os.path.abspath(self.filepath):
            atomic_json_dump(report, self.latest_filepath)
        return report


# Nombre usado durante la migración. Se conserva como alias para que los nuevos
# módulos y cualquier integración externa no dependan de un cambio de clase.
MetricsTracker = PerformanceTracker
