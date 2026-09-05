"""
Test de Ejecución Real y Recolector de Telemetría para la Fase 1 - Parte 1 (RUCT y BOE).

Este módulo ejecuta el pipeline REAL de la Fase 1 Parte 1 conectándose directamente
a los servidores oficiales del Ministerio de Educación (RUCT) y del BOE,
ejecutando los workers multiproceso reales y recolectando información detallada.
"""

import argparse
import json
import os
import sys
import time
import unittest
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRAWLER_DIR = os.path.join(BASE_DIR, "Crawler")
if CRAWLER_DIR not in sys.path:
    sys.path.insert(0, CRAWLER_DIR)

from core.config import (
    PLANES_DIR,
    TEMP_PDF_DIR,
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    CHECKPOINT_JSON,
    ESTADISTICAS_JSON,
    ERRORES_JSON,
    find_plan_filepath,
)
from pipelines.parte1_ruct_boe import run_phase1_part1, cleanup_temporary_files
from core.metrics import PerformanceTracker
from parsers import get_curriculum_completeness_status
from core.progress import ProgressEmitter


def execute_real_phase1_part1(limit_universities=2, limit_degrees=3, max_workers=2, force=True):
    """
    Ejecuta la Fase 1 Parte 1 contra los servidores oficiales reales y recolecta métricas detalladas.
    """
    cleanup_temporary_files(TEMP_PDF_DIR, max_age_seconds=0)
    print("\n" + "=" * 80)
    print("      INICIANDO TEST DE EJECUCIÓN REAL - FASE 1 PARTE 1 (RUCT / BOE)")
    print("=" * 80)
    print(f" [*] Configuración: Universidades máx: {limit_universities or 'TODAS (109)'} | "
          f"Titulaciones/Univ máx: {limit_degrees or 'TODAS'} | Workers: {max_workers} | Force: {force}")
    print(" [*] Conectando a endpoints oficiales del Ministerio de Educación...")

    tracker = PerformanceTracker()
    emitter = ProgressEmitter()

    start_time = time.time()
    
    # Ejecutar pipeline real de Fase 1 Parte 1
    result = run_phase1_part1(
        limit_universities=limit_universities,
        limit_degrees=limit_degrees,
        force=force,
        max_workers=max_workers,
        metrics_tracker=tracker,
        progress_emitter=emitter,
    )
    
    elapsed_time = round(time.time() - start_time, 2)

    # =========================================================================
    # RECOLECCIÓN Y ANÁLISIS DE DATOS REALES GENERADOS
    # =========================================================================
    universities_data = []
    if os.path.exists(UNIVERSIDADES_JSON):
        try:
            with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
                universities_data = json.load(f)
        except Exception:
            pass

    catalog_data = {}
    if os.path.exists(TITULACIONES_JSON):
        try:
            with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
                catalog_data = json.load(f)
        except Exception:
            pass

    # Inspeccionar planes de estudio generados en disco
    plan_files_found = []
    plan_details = []
    completeness_summary = {
        "completo": 0,
        "incompleto_parcial": 0,
        "sin_elementos": 0,
        "no_resuelto_boe": 0,
    }

    for u_code, u_info in catalog_data.items():
        u_name = u_info.get("universidad_nombre", "")
        degrees_list = u_info.get("titulaciones_vigentes", [])
        if limit_degrees:
            degrees_list = degrees_list[:limit_degrees]

        for deg in degrees_list:
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            d_level = deg.get("nivel_academico", "")
            p_file = find_plan_filepath(u_code, d_code)

            detail_info = {
                "universidad_codigo": u_code,
                "universidad_nombre": u_name,
                "codigo_estudio": d_code,
                "titulo": d_title,
                "nivel": d_level,
                "plan_encontrado": os.path.exists(p_file),
                "total_asignaturas": 0,
                "creditos_totales": 0.0,
                "estado_curriculo": "no_resuelto_boe",
                "boe_url": None,
            }

            if os.path.exists(p_file):
                plan_files_found.append(p_file)
                try:
                    with open(p_file, "r", encoding="utf-8") as pf:
                        plan_payload = json.load(pf)
                    p_est = plan_payload.get("plan_estudios", {})
                    detail_info["total_asignaturas"] = p_est.get("total_elementos", 0)
                    detail_info["creditos_totales"] = p_est.get("resumen_creditos", {}).get("Créditos Totales", 0.0)
                    detail_info["boe_url"] = plan_payload.get("boe_url")

                    comp_status = get_curriculum_completeness_status(plan_payload)
                    c_st = comp_status.get("status", "sin_elementos")
                    detail_info["estado_curriculo"] = c_st
                    if c_st in completeness_summary:
                        completeness_summary[c_st] += 1
                    else:
                        completeness_summary["incompleto_parcial"] += 1
                except Exception:
                    pass
            else:
                completeness_summary["no_resuelto_boe"] += 1

            plan_details.append(detail_info)

    # Verificar fugas de archivos temporales de la Fase 1 Parte 1
    temp_pdfs_leaked = 0
    if os.path.exists(TEMP_PDF_DIR):
        temp_pdfs_leaked = len([
            f for f in os.listdir(TEMP_PDF_DIR) 
            if (f.startswith("boe_") or f.startswith("degrees_") or f.startswith("universidades_temp")) 
            and (f.endswith(".pdf") or f.endswith(".xls"))
        ])

    # Compilar telemetría final estructurada
    telemetry = {
        "timestamp": datetime.now().isoformat(),
        "execution_summary": {
            "status": result.get("status"),
            "duration_seconds": elapsed_time,
            "universities_requested_limit": limit_universities,
            "degrees_per_university_limit": limit_degrees,
            "universities_processed": result.get("universities_processed", 0),
            "total_tasks_enqueued": result.get("total_enqueued", 0),
            "error": result.get("error"),
        },
        "performance_metrics": {
            "universidades_inspeccionadas": tracker.universidades_inspeccionadas,
            "titulaciones_inspeccionadas": tracker.titulaciones_inspeccionadas,
            "titulaciones_actualizadas": tracker.titulaciones_descargadas_actualizadas,
            "titulaciones_al_dia": tracker.titulaciones_al_dia,
            "pdfs_parseados": tracker.pdfs_parseados,
            "errores_detectados": tracker.errores_detectados,
            "tiempo_io_red_segundos": round(tracker.total_io_network_time, 2),
            "tiempo_parseo_pdf_segundos": round(tracker.total_pdf_parsing_time, 2),
            "memoria_pico_mb": round(tracker.peak_memory_bytes / (1024 * 1024), 2),
        },
        "catalog_results": {
            "total_universidades_oficiales_espana": len(universities_data),
            "universidades_en_catalogo": len(catalog_data),
            "titulaciones_evaluadas": len(plan_details),
            "planes_guardados_en_disco": len(plan_files_found),
            "resumen_completitud_curriculo": completeness_summary,
            "archivos_temporales_huerfanos": temp_pdfs_leaked,
        },
        "sampled_plan_details": plan_details[:10],
    }

    # Guardar reporte JSON en disco
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reporte_ejecucion_real_parte1.json")
    try:
        with open(report_file, "w", encoding="utf-8") as rf:
            json.dump(telemetry, rf, indent=2, ensure_ascii=False)
        print(f"\n [+] Reporte JSON guardado en: {report_file}")
    except Exception as err:
        print(f" [!] No se pudo guardar reporte JSON: {err}")

    # =========================================================================
    # REPORTE EN CONSOLA CONSOLIDADO
    # =========================================================================
    print("\n" + "=" * 80)
    print("                 REPORTE DE EJECUCIÓN REAL - FASE 1 PARTE 1")
    print("=" * 80)
    print(f" Estado de ejecución:                  {str(telemetry['execution_summary']['status']).upper()}")
    print(f" Duración total de red y parseo:       {telemetry['execution_summary']['duration_seconds']} s")
    print(f" Catálogo oficial España detectado:    {telemetry['catalog_results']['total_universidades_oficiales_espana']} universidades")
    print(f" Universidades procesadas en el run:   {telemetry['execution_summary']['universities_processed']}")
    print(f" Titulaciones oficiales inspeccionadas: {telemetry['performance_metrics']['titulaciones_inspeccionadas']}")
    print(f" Tareas encoladas en workers:          {telemetry['execution_summary']['total_tasks_enqueued']}")
    print(f" Resoluciones BOE descargadas/parseadas:{telemetry['performance_metrics']['pdfs_parseados']}")
    print(f" Planes curriculares escritos en disco:{telemetry['catalog_results']['planes_guardados_en_disco']}")
    print(f" Desglose de completitud curricular:   {telemetry['catalog_results']['resumen_completitud_curriculo']}")
    print(f" Memoria RAM máxima utilizada:         {telemetry['performance_metrics']['memoria_pico_mb']} MB")
    print(f" Fugas de archivos temporales:         {telemetry['catalog_results']['archivos_temporales_huerfanos']} (0 esperado)")
    print("=" * 80)

    if plan_details:
        print("\n [Muestra de Titulaciones Procesadas en Vivo]:")
        for idx, item in enumerate(plan_details[:6], 1):
            boe_tag = f"BOE: {item['boe_url']}" if item.get('boe_url') else "Sin BOE publicado (pendiente Parte 2)"
            print(f"  {idx}. [{item['universidad_codigo']}] {item['universidad_nombre'][:28]} | "
                  f"[{item['codigo_estudio']}] {item['titulo'][:32]} | Asigs: {item['total_asignaturas']} | "
                  f"Estado: {item['estado_curriculo']} | {boe_tag}")
        print("=" * 80 + "\n")

    return telemetry


class TestFase1Parte1RealExecution(unittest.TestCase):
    """Test unitario que ejecuta la Fase 1 Parte 1 real contra el RUCT oficial."""

    def test_real_network_execution_of_phase1_part1(self):
        """Ejecuta una pasada real controlada sobre múltiples universidades oficiales del RUCT."""
        telemetry = execute_real_phase1_part1(
            limit_universities=2,
            limit_degrees=2,
            max_workers=2,
            force=True
        )

        # Aserciones sobre la ejecución real
        self.assertIn(telemetry["execution_summary"]["status"], ["completed", "partial"])
        self.assertGreaterEqual(telemetry["catalog_results"]["total_universidades_oficiales_espana"], 80,
                                "El RUCT oficial debe listar al menos 80 universidades en España")
        self.assertGreaterEqual(telemetry["execution_summary"]["universities_processed"], 2,
                                "Debe haber procesado al menos 2 universidades reales")
        self.assertGreaterEqual(telemetry["performance_metrics"]["titulaciones_inspeccionadas"], 4,
                                "Debe haber inspeccionado al menos 4 titulaciones reales")
        self.assertEqual(telemetry["catalog_results"]["archivos_temporales_huerfanos"], 0,
                         "No debe haber archivos temporales huérfanos tras la ejecución")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lanzador de ejecución real de la Fase 1 Parte 1 (RUCT/BOE)")
    parser.add_argument("--univs", type=int, default=2, help="Límite de universidades (0 para todas)")
    parser.add_argument("--degrees", type=int, default=3, help="Límite de titulaciones por universidad (0 para todas)")
    parser.add_argument("--workers", type=int, default=2, help="Número de procesos worker para parseo PDF")
    parser.add_argument("--no-force", action="store_true", help="Respetar estado previo sin forzar revalidación")

    args, remaining = parser.parse_known_args()
    
    if len(sys.argv) > 1 and sys.argv[1] in ["-v", "-q", "-k", "TestFase1Parte1RealExecution"]:
        # Si se invoca como runner de unittest
        unittest.main(argv=[sys.argv[0]] + remaining)
    else:
        # Si se invoca directamente con argumentos CLI
        u_lim = None if args.univs == 0 else args.univs
        d_lim = None if args.degrees == 0 else args.degrees
        execute_real_phase1_part1(
            limit_universities=u_lim,
            limit_degrees=d_lim,
            max_workers=args.workers,
            force=not args.no_force
        )