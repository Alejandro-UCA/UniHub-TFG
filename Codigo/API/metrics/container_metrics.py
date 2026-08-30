import os
import json
import logging
import psutil
import shutil
from datetime import datetime

try:
    from API.config import settings
except (ImportError, AttributeError):
    from config import settings

logger = logging.getLogger("unihub_container_metrics")

def get_dir_size_bytes(path: str) -> int:
    """Calcula el espacio total en disco utilizado por un directorio en bytes."""
    total = 0
    if not os.path.exists(path):
        return 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if not os.path.islink(fp) and os.path.exists(fp):
                    total += os.path.getsize(fp)
    except OSError as error:
        logger.warning("No se pudo completar el cálculo de tamaño de %s: %s", path, error)
    return total

def get_crawler_status_and_metrics(datos_dir: str) -> dict:
    """
    Lee checkpoint.json y estadisticas_rendimiento.json para extraer el estado y progreso de la Fase 1.
    """
    checkpoint_file = os.path.join(datos_dir, "checkpoint.json")
    stats_file = os.path.join(datos_dir, "estadisticas_rendimiento.json")

    processed_univs = []
    processed_degrees = {}
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
                processed_univs = ckpt.get("processed_universities", [])
                processed_degrees = ckpt.get("processed_degrees", {})
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("No se pudo leer el checkpoint del crawler %s: %s", checkpoint_file, error)

    crawler_stats = {}
    if os.path.exists(stats_file):
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                crawler_stats = json.load(f)
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("No se pudieron leer las métricas del crawler %s: %s", stats_file, error)

    crawler_operations = crawler_stats.get("operaciones_crawler", {}) if isinstance(crawler_stats, dict) else {}

    # Desde el contenedor API no se puede afirmar que otro contenedor esté
    # activo: solo se inspecciona el proceso visible en este namespace.
    is_crawler_active = False
    try:
        for p in psutil.process_iter(['name', 'cmdline']):
            cmd = " ".join(p.info['cmdline'] or [])
            if "main.py" in cmd or "run_crawler" in cmd:
                is_crawler_active = True
                break
    except (psutil.Error, TypeError) as error:
        logger.debug("No se pudo inspeccionar el estado de procesos del crawler: %s", error, exc_info=True)

    return {
        "is_active": is_crawler_active,
        "estado_proceso": "Activo / Rastreando" if is_crawler_active else "Inactivo / Esperando Regla Cron (02:00 1º de mes)",
        "universidades_rastreadas_count": len(processed_univs),
        "universidades_rastreadas_list": processed_univs,
        "titulaciones_rastreadas_count": len(processed_degrees),
        "titulaciones_inspeccionadas": crawler_operations.get("titulaciones_inspeccionadas", 0),
        "titulaciones_al_dia": crawler_operations.get("titulaciones_al_dia_sin_cambios", 0),
        "titulaciones_actualizadas": crawler_operations.get("titulaciones_nuevas_o_actualizadas", 0),
        "pdfs_parseados": crawler_operations.get("pdfs_boe_descargados_y_parseados", 0),
        "errores_registrados": crawler_operations.get("errores_registrados", 0),
        "incidencias_controladas": crawler_operations.get("incidencias_controladas", 0)
    }

def collect_container_physical_stats() -> dict:
    """Recoge recursos reales del proceso API y del volumen visible.

    La API no tiene acceso garantizado al namespace de procesos ni a las
    métricas cgroup de los otros contenedores; esos valores se devuelven como
    no disponibles en lugar de estimarlos como si fueran mediciones físicas.
    """
    process = psutil.Process(os.getpid())
    system_mem = psutil.virtual_memory()

    # Memory RAM metrics
    mem_info = process.memory_info()
    current_rss_mb = round(mem_info.rss / (1024 * 1024), 2)
    current_vsz_mb = round(mem_info.vms / (1024 * 1024), 2)

    # Disk Space metrics
    datos_dir = settings.CRAWLER_DATA_DIR

    disk_used_bytes = get_dir_size_bytes(datos_dir)
    disk_used_mb = round(disk_used_bytes / (1024 * 1024), 2)
    disk_used_gb = round(disk_used_bytes / (1024 * 1024 * 1024), 3)

    # Host/Volume Drive Partition Usage
    try:
        disk_usage = shutil.disk_usage(datos_dir)
        total_drive_gb = round(disk_usage.total / (1024 * 1024 * 1024), 2)
        free_drive_gb = round(disk_usage.free / (1024 * 1024 * 1024), 2)
        drive_percent_used = round((disk_usage.used / disk_usage.total) * 100, 1)
    except (OSError, ZeroDivisionError) as error:
        logger.warning("No se pudo obtener el uso de disco para %s: %s", datos_dir, error)
        total_drive_gb = 0
        free_drive_gb = 0
        drive_percent_used = 0

    # CPU metrics
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_times = process.cpu_times()
    total_cpu_seconds = round(cpu_times.user + cpu_times.system, 2)
    num_threads = process.num_threads()

    crawler_info = get_crawler_status_and_metrics(datos_dir)

    # Estimación de Huella de Carbono Green IT (gCO2e)
    # Factor aproximado: ~0.0003 kWh por segundo de CPU a 50W TDP + 250 gCO2/kWh (red eléctrica europea/española)
    g_co2_estimated = round(total_cpu_seconds * 0.0003 * 250, 4)

    # Solo el proceso API actual tiene medición física en este endpoint.
    contenedores = [
        {
            "nombre": "unihub_crawler",
            "fase": "Fase 1 - Rastreador BOE",
            "imagen": "python:3.12-slim",
            "estado": "Visible solo por checkpoint; salud física no disponible",
            "memoria_mb": None,
            "cpu_porcentaje": None,
            "medicion_disponible": False,
            "detalles_especificos": crawler_info
        },
        {
            "nombre": "unihub_api",
            "fase": "Fase 2 - API REST FastAPI",
            "imagen": "python:3.12-slim",
            "estado": "UP (proceso API actual)",
            "memoria_mb": current_rss_mb,
            "cpu_porcentaje": cpu_percent,
            "medicion_disponible": True
        },
        {
            "nombre": "unihub_db",
            "fase": "Fase 2 - Base de Datos PostgreSQL",
            "imagen": "postgres:15-alpine",
            "estado": "No disponible desde el contenedor API",
            "memoria_mb": None,
            "cpu_porcentaje": None,
            "medicion_disponible": False
        },
        {
            "nombre": "unihub_www",
            "fase": "Fase 3 - Aplicación Web UniHub",
            "imagen": "nginx:1.25-alpine",
            "estado": "No disponible desde el contenedor API",
            "memoria_mb": None,
            "cpu_porcentaje": None,
            "medicion_disponible": False
        }
    ]

    return {
        "timestamp": datetime.now().isoformat(),
        "contenedores_individuales": contenedores,
        "fase_1_crawler_detalle": crawler_info,
        "green_it_metrics": {
            "medicion_disponible": False,
            "huella_carbono_medida_gco2": None,
            "huella_carbono_estimada_gco2": g_co2_estimated,
            "eficiencia_energetica": "Estimación no certificada basada en CPU del proceso API",
            "factor_emision_red": "0.25 kg CO2/kWh (supuesto de cálculo)"
        },
        "memoria_fisica": {
            "rss_actual_mb": current_rss_mb,
            "vsz_virtual_mb": current_vsz_mb,
            "memoria_sistema_total_mb": round(system_mem.total / (1024 * 1024), 2),
            "memoria_sistema_usada_porcentaje": system_mem.percent
        },
        "almacenamiento_disco": {
            "datos_json_y_pdf_mb": disk_used_mb,
            "datos_json_y_pdf_gb": disk_used_gb,
            "disco_total_sistema_gb": total_drive_gb,
            "disco_libre_sistema_gb": free_drive_gb,
            "porcentaje_disco_usado": drive_percent_used
        },
        "procesador_cpu": {
            "porcentaje_cpu_actual": cpu_percent,
            "tiempo_cpu_acumulado_seg": total_cpu_seconds,
            "num_hilos_activos": num_threads,
            "num_cpus_sistema": os.cpu_count() or 1
        }
    }
