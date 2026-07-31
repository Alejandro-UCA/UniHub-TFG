import os
import sys
import json
import time
import traceback
import argparse
from datetime import datetime

from config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    ERRORES_JSON,
    CHECKPOINT_JSON,
    ESTADISTICAS_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    URL_UNIVERSIDADES_LIST,
    URL_ESTUDIOS_UNIV_TEMPLATE,
    URL_DETALLE_ESTUDIO_TEMPLATE
)
from downloader import RUCTDownloader
from error_logger import ErrorLogger
from checkpoint import CheckpointManager
from metrics import PerformanceTracker
from parsers import (
    parse_universities_xls,
    parse_degrees_xls,
    parse_degree_detail_html,
    parse_boe_pdf
)

# Ensure Windows terminal stdout handles unicode characters safely
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def run_crawler(limit_univ: int = None, limit_degrees: int = None):
    print("=" * 70)
    print("      INICIANDO CRAWLER RUCT - UNIVERSIDADES Y TITULACIONES DE ESPAÑA")
    print("======================================================================")
    
    metrics = PerformanceTracker()
    downloader = RUCTDownloader(metrics_tracker=metrics)
    logger = ErrorLogger()
    checkpoint = CheckpointManager()
    
    # -------------------------------------------------------------------------
    # PASO 1: Descargar listado oficial actualizado de universidades
    # -------------------------------------------------------------------------
    print("\n[Paso 1] Obteniendo listado de universidades desde RUCT...")
    universities = []
    try:
        temp_univ_xls = os.path.join(TEMP_PDF_DIR, "universidades_list.xls")
        downloader.download_file(URL_UNIVERSIDADES_LIST, temp_univ_xls)
        universities = parse_universities_xls(temp_univ_xls)
        
        with open(UNIVERSIDADES_JSON, "w", encoding="utf-8") as f:
            json.dump(universities, f, ensure_ascii=False, indent=2)
            
        if os.path.exists(temp_univ_xls):
            os.remove(temp_univ_xls)
            
        checkpoint.mark_universities_downloaded()
        print(f" -> {len(universities)} universidades comprobadas y actualizadas en '{UNIVERSIDADES_JSON}'.")
    except Exception as e:
        err_msg = f"Error al descargar lista de universidades: {e}"
        print(f" [ERROR NO BLOQUEANTE] {err_msg}")
        logger.log_error("paso_1_universidades", "TODAS", URL_UNIVERSIDADES_LIST, err_msg, traceback.format_exc())
        metrics.errores_detectados += 1
        if os.path.exists(UNIVERSIDADES_JSON):
            with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
                universities = json.load(f)

    if limit_univ:
        universities = universities[:limit_univ]
        print(f" [INFO] Modo de prueba activado: limitado a {limit_univ} universidades.")

    metrics.universidades_inspeccionadas = len(universities)

    # Structure for titulaciones_universidad.json
    titulaciones_por_universidad = {}
    if os.path.exists(TITULACIONES_JSON):
        try:
            with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
                titulaciones_por_universidad = json.load(f)
        except Exception:
            titulaciones_por_universidad = {}

    # -------------------------------------------------------------------------
    # PASO 2 y 3: Recorrer TODAS las universidades y verificar titulaciones / BOE
    # -------------------------------------------------------------------------
    print("\n[Paso 2 y 3] Inspeccionando titulaciones vigentes y verificando novedades de BOE...")
    total_univ = len(universities)
    
    for u_idx, univ in enumerate(universities, 1):
        u_code = univ.get("codigo", "")
        u_name = univ.get("nombre", "")
        print(f"\n({u_idx}/{total_univ}) Procesando Universidad [{u_code}]: {u_name}")
        
        active_degrees = []
        try:
            degrees_url = URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo=u_code)
            temp_degrees_xls = os.path.join(TEMP_PDF_DIR, f"degrees_{u_code}.xls")
            
            downloader.download_file(degrees_url, temp_degrees_xls)
            active_degrees = parse_degrees_xls(temp_degrees_xls)
            
            titulaciones_por_universidad[u_code] = {
                "universidad_codigo": u_code,
                "universidad_nombre": u_name,
                "universidad_tipo": univ.get("tipo", ""),
                "comunidad_autonoma": univ.get("comunidad_autonoma", ""),
                "total_titulaciones_vigentes_renovadas": len(active_degrees),
                "titulaciones_vigentes": active_degrees
            }
            
            with open(TITULACIONES_JSON, "w", encoding="utf-8") as f:
                json.dump(titulaciones_por_universidad, f, ensure_ascii=False, indent=2)
                
            if os.path.exists(temp_degrees_xls):
                os.remove(temp_degrees_xls)
                
            print(f"     -> {len(active_degrees)} titulaciones VIGENTES/RENOVADAS identificadas.")

        except Exception as e:
            err_msg = f"Error al obtener listado de titulaciones para la universidad {u_code}"
            print(f"     -> [ERROR NO BLOQUEANTE] {err_msg}: {e}")
            logger.log_error("paso_2_titulaciones_xls", u_code, URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo=u_code), err_msg, traceback.format_exc())
            metrics.errores_detectados += 1
            continue

        degrees_to_process = active_degrees
        if limit_degrees:
            degrees_to_process = degrees_to_process[:limit_degrees]

        # Inspect each degree for latest BOE and update incrementally if new
        for d_idx, deg in enumerate(degrees_to_process, 1):
            metrics.titulaciones_inspeccionadas += 1
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            print(f"   [{d_idx}/{len(degrees_to_process)}] Titulación [{d_code}]: {d_title[:65]}...")
            
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
            detail_url = URL_DETALLE_ESTUDIO_TEMPLATE.format(codigo_estudio=d_code)
            
            try:
                html_content = downloader.fetch_text(detail_url)
                boe_info = parse_degree_detail_html(html_content)
                
                latest_boe_url = boe_info.get("latest_boe_url")
                latest_boe_fecha = boe_info.get("boe_date")
                
                # Check if degree is already up to date
                if os.path.exists(plan_file) and checkpoint.is_degree_up_to_date(d_code, latest_boe_url, latest_boe_fecha):
                    metrics.titulaciones_al_dia += 1
                    print(f"     -> Información al día (BOE {latest_boe_fecha or 'coincide'}). Sin cambios necesarios.")
                    continue

                if not latest_boe_url:
                    print(f"     -> [AVISO] No se encontró enlace a BOE en la página de detalle.")
                    logger.log_error("paso_3_enlace_boe", d_code, detail_url, "Sin enlace a BOE en detalle HTML", "No PDF links in HTML")
                    metrics.errores_detectados += 1
                    degree_data = {
                        "codigo_estudio": d_code,
                        "titulo": d_title,
                        "nivel_academico": deg.get("nivel_academico", ""),
                        "universidad_codigo": u_code,
                        "universidad_nombre": u_name,
                        "fecha_procesado": datetime.now().isoformat(),
                        "boe_url": None,
                        "plan_estudios": None
                    }
                    with open(plan_file, "w", encoding="utf-8") as f:
                        json.dump(degree_data, f, ensure_ascii=False, indent=2)
                    checkpoint.update_degree_record(d_code, None, None, datetime.now().isoformat())
                    continue

                # Download new / updated BOE PDF
                pdf_path = os.path.join(TEMP_PDF_DIR, f"{d_code}_latest.pdf")
                print(f"     -> DESCARGANDO NUEVO/ACTUALIZADO BOE ({latest_boe_fecha or 'fecha desconocida'})...")
                downloader.download_file(latest_boe_url, pdf_path)

                # Measure PDF parsing duration
                t_parse_start = time.perf_counter()
                curriculum_data = parse_boe_pdf(pdf_path)
                t_parse_elapsed = time.perf_counter() - t_parse_start
                metrics.record_pdf_parse_time(t_parse_elapsed)
                metrics.titulaciones_descargadas_actualizadas += 1

                # Save / update degree JSON file
                degree_data = {
                    "codigo_estudio": d_code,
                    "titulo": d_title,
                    "nivel_academico": deg.get("nivel_academico", ""),
                    "universidad_codigo": u_code,
                    "universidad_nombre": u_name,
                    "fecha_procesado": datetime.now().isoformat(),
                    "boe_url": latest_boe_url,
                    "boe_fecha": latest_boe_fecha,
                    "plan_estudios": curriculum_data
                }

                with open(plan_file, "w", encoding="utf-8") as f:
                    json.dump(degree_data, f, ensure_ascii=False, indent=2)

                if os.path.exists(pdf_path):
                    os.remove(pdf_path)

                checkpoint.update_degree_record(d_code, latest_boe_url, latest_boe_fecha, datetime.now().isoformat())
                num_elem = curriculum_data.get("total_elementos", 0)
                print(f"     -> Guardados {num_elem} elementos curriculares en '{d_code}.json'. PDF borrado.")

            except Exception as e:
                err_msg = f"Error al procesar titulación {d_code}"
                print(f"     -> [ERROR NO BLOQUEANTE] {err_msg}: {e}")
                logger.log_error("paso_3_procesamiento_titulacion", d_code, detail_url, err_msg, traceback.format_exc())
                metrics.errores_detectados += 1
                pdf_path = os.path.join(TEMP_PDF_DIR, f"{d_code}_latest.pdf")
                if os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass

        checkpoint.mark_university_processed(u_code)
        metrics.save()

    # Save final performance report
    metrics.save()
    rep = metrics.generate_report()

    print("\n======================================================================")
    print("      CRAWLER COMPLETADO CON ÉXITO")
    print("======================================================================")
    print(" ESTADÍSTICAS DE RENDIMIENTO GUARDADAS EN:", ESTADISTICAS_JSON)
    print(f"  - Memoria actual usada:      {rep['rendimiento_memoria']['uso_memoria_actual_mb']} MB")
    print(f"  - Pico máximo de memoria:    {rep['rendimiento_memoria']['pico_maximo_memoria_mb']} MB")
    print(f"  - Tiempo total reloj:        {rep['rendimiento_tiempo']['tiempo_total_ejecucion_seg']} s")
    print(f"  - Tiempo computación CPU:    {rep['rendimiento_tiempo']['tiempo_procesamiento_cpu_seg']} s")
    print(f"  - Tiempo espera E/S y Red:   {rep['rendimiento_tiempo']['tiempo_espera_io_red_seg']} s")
    print(f"  - Titulaciones procesadas:   {rep['operaciones_crawler']['titulaciones_inspeccionadas']} (Al día: {rep['operaciones_crawler']['titulaciones_al_dia_sin_cambios']}, Nuevas/Actualizadas: {rep['operaciones_crawler']['titulaciones_nuevas_o_actualizadas']})")
    print("======================================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawler RUCT de Universidades y Titulaciones de España")
    parser.add_argument("--limit-univ", type=int, default=None, help="Número máximo de universidades a procesar (para pruebas)")
    parser.add_argument("--limit-degrees", type=int, default=None, help="Número máximo de titulaciones por universidad a procesar (para pruebas)")
    
    args = parser.parse_args()
    run_crawler(limit_univ=args.limit_univ, limit_degrees=args.limit_degrees)
