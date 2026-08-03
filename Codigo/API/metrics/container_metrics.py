import os
import psutil
import shutil
from datetime import datetime

def get_dir_size_bytes(path: str) -> int:
    """Calculates total disk space used by a directory in bytes."""
    total = 0
    if not os.path.exists(path):
        return 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if not os.path.islink(fp) and os.path.exists(fp):
                    total += os.path.getsize(fp)
    except Exception:
        pass
    return total

def collect_container_physical_stats() -> dict:
    """
    Collects physical system resource statistics for Docker containers:
    Memory (RAM RSS MB, Peak RAM, System Memory %), Disk Space (MB/GB), CPU & Threads.
    """
    process = psutil.Process(os.getpid())
    system_mem = psutil.virtual_memory()

    # Memory RAM metrics
    mem_info = process.memory_info()
    current_rss_mb = round(mem_info.rss / (1024 * 1024), 2)
    current_vsz_mb = round(mem_info.vms / (1024 * 1024), 2)

    # Disk Space metrics
    datos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Crawler", "Datos"))
    if not os.path.exists(datos_dir):
        datos_dir = "/app/Datos"

    disk_used_bytes = get_dir_size_bytes(datos_dir)
    disk_used_mb = round(disk_used_bytes / (1024 * 1024), 2)
    disk_used_gb = round(disk_used_bytes / (1024 * 1024 * 1024), 3)

    # Host/Volume Drive Partition Usage
    try:
        disk_usage = shutil.disk_usage(datos_dir)
        total_drive_gb = round(disk_usage.total / (1024 * 1024 * 1024), 2)
        free_drive_gb = round(disk_usage.free / (1024 * 1024 * 1024), 2)
        drive_percent_used = round((disk_usage.used / disk_usage.total) * 100, 1)
    except Exception:
        total_drive_gb = 0
        free_drive_gb = 0
        drive_percent_used = 0

    # CPU metrics
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_times = process.cpu_times()
    total_cpu_seconds = round(cpu_times.user + cpu_times.system, 2)
    num_threads = process.num_threads()

    return {
        "timestamp": datetime.now().isoformat(),
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
