import os
import sys
import json
import time
import traceback
import argparse
import multiprocessing as mp
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
from downloader import RUCTDownloader, SkipUniversityException
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump
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


def pdf_parser_consumer(task_queue: mp.Queue, result_queue: mp.Queue):
    """
    PROCESO 2 (CONSUMIDOR / ANÁLISIS DE DATOS CPU):
    Recibe tareas de la cola task_queue con PDFs ya descargados en disco.
    Analiza la estructura de los PDFs (materias, asignaturas, módulos, créditos ECTS),
    fusiona la información actualizada de múltiples BOEs y guarda la titulación en disco.
    """
    logger = ErrorLogger()
    checkpoint = CheckpointManager()

    parsed_count = 0
    updated_degrees_count = 0
    total_parse_time = 0.0

    while True:
        try:
            task = task_queue.get()
            if task is None or (isinstance(task, dict) and task.get("type") == "STOP"):
                break

            task_type = task.get("type")
            d_code = task.get("d_code", "")
            d_title = task.get("d_title", "")
            u_code = task.get("u_code", "")
            u_name = task.get("u_name", "")
            nivel_academico = task.get("nivel_academico", "")
            latest_boe_url = task.get("latest_boe_url")
            latest_boe_fecha = task.get("latest_boe_fecha")
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")

            if task_type == "DEGREE_NO_BOE":
                print(f"     [Proceso Parser] -> [AVISO] Sin enlaces a BOE para [{d_code}]. Guardando metadatos base.")
                degree_data = {
                    "codigo_estudio": d_code,
                    "titulo": d_title,
                    "nivel_academico": nivel_academico,
                    "universidad_codigo": u_code,
                    "universidad_nombre": u_name,
                    "fecha_procesado": datetime.now().isoformat(),
                    "boe_url": None,
                    "plan_estudios": None
                }
                atomic_json_dump(degree_data, plan_file)
                checkpoint.update_degree_record(d_code, None, None, datetime.now().isoformat())

            elif task_type == "PARSE_DEGREE_PDFS":
                pdf_items = task.get("pdf_items", [])
                combined_resumen_creditos = {}
                combined_elementos = []
                seen_subject_names = set()
                processed_boe_urls = []
                valid_curriculum_found = False

                for cand_idx, item in enumerate(pdf_items, 1):
                    cand_url = item["cand_url"]
                    cand_date = item["cand_date"]
                    pdf_path = item["pdf_path"]

                    try:
                        if not os.path.exists(pdf_path):
                            continue

                        t_start = time.perf_counter()
                        curriculum_data = parse_boe_pdf(pdf_path)
                        t_elapsed = time.perf_counter() - t_start
                        total_parse_time += t_elapsed
                        parsed_count += 1

                        total_elems = curriculum_data.get("total_elementos", 0)
                        resumen = curriculum_data.get("resumen_creditos", {})
                        resumen_count = len(resumen)

                        if total_elems > 0 or resumen_count > 0:
                            print(f"     [Proceso Parser] -> [ÉXITO] Parsed PDF #{cand_idx} para [{d_code}] en {t_elapsed:.2f}s ({total_elems} elementos).")
                            valid_curriculum_found = True
                            processed_boe_urls.append(cand_url)

                            for k, v in resumen.items():
                                if k not in combined_resumen_creditos:
                                    combined_resumen_creditos[k] = v

                            for elem in curriculum_data.get("elementos_curriculares", []):
                                norm_name = elem.get("nombre_elemento", "").strip().lower()
                                if norm_name and norm_name not in seen_subject_names:
                                    seen_subject_names.add(norm_name)
                                    combined_elementos.append(elem)
                        else:
                            print(f"     [Proceso Parser] -> PDF #{cand_idx} de [{d_code}] no contenía tabla de asignaturas.")

                    except Exception as pdf_err:
                        print(f"     [Proceso Parser] -> Error al procesar PDF candidate #{cand_idx} de [{d_code}]: {pdf_err}")
                        logger.log_error("paso_3_parse_pdf", d_code, cand_url, f"Error en parser PDF #{cand_idx}", str(pdf_err))
                    finally:
                        if os.path.exists(pdf_path):
                            try:
                                os.remove(pdf_path)
                            except Exception:
                                pass

                if valid_curriculum_found:
                    updated_degrees_count += 1
                    curriculum_combined = {
                        "resumen_creditos": combined_resumen_creditos,
                        "total_elementos": len(combined_elementos),
                        "elementos_curriculares": combined_elementos
                    }
                    degree_data = {
                        "codigo_estudio": d_code,
                        "titulo": d_title,
                        "nivel_academico": nivel_academico,
                        "universidad_codigo": u_code,
                        "universidad_nombre": u_name,
                        "fecha_procesado": datetime.now().isoformat(),
                        "boe_url": latest_boe_url,
                        "boe_fecha": latest_boe_fecha,
                        "all_boe_urls": processed_boe_urls,
                        "plan_estudios": curriculum_combined
                    }
                    atomic_json_dump(degree_data, plan_file)
                    checkpoint.update_degree_record(d_code, latest_boe_url, latest_boe_fecha, datetime.now().isoformat())
                else:
                    print(f"     [Proceso Parser] -> [AVISO] Ningún PDF de [{d_code}] contenía asignaturas desglosadas. Guardando metadatos base.")
                    degree_data = {
                        "codigo_estudio": d_code,
                        "titulo": d_title,
                        "nivel_academico": nivel_academico,
                        "universidad_codigo": u_code,
                        "universidad_nombre": u_name,
                        "fecha_procesado": datetime.now().isoformat(),
                        "boe_url": latest_boe_url,
                        "boe_fecha": latest_boe_fecha,
                        "plan_estudios": None
                    }
                    atomic_json_dump(degree_data, plan_file)
                    checkpoint.update_degree_record(d_code, latest_boe_url, latest_boe_fecha, datetime.now().isoformat())

        except Exception as consumer_err:
            print(f"     [Proceso Parser ERROR] Excepción inesperada en consumidor: {consumer_err}")

    result_queue.put({
        "parsed_count": parsed_count,
        "updated_degrees_count": updated_degrees_count,
        "total_parse_time": total_parse_time
    })


def trigger_api_etl_sync():
    """Notifies Phase 2 (FastAPI REST API) to run ETL synchronization automatically."""
    try:
        import requests
        api_sync_url = os.getenv("API_SYNC_URL", "http://api:8000/api/v1/etl/sync")
        print(f"\n[Fase 1 -> Fase 2] Notificando a la API REST ({api_sync_url}) para sincronización en PostgreSQL...")
        resp = requests.post(api_sync_url, timeout=10)
        if resp.ok:
            print(" -> Sincronización ETL iniciada en la Base de Datos PostgreSQL de la Fase 2.")
        else:
            print(f" -> Solicitud enviada. Código HTTP: {resp.status_code}")
    except Exception as e:
        print(f" -> Notificación previa no enviada (se sincronizará en el siguiente ciclo o manualmente): {e}")


def run_crawler(limit_univ: int = None, limit_degrees: int = None):
    print("=" * 70)
    print("      INICIANDO CRAWLER UNIHUB (COMPUTACIÓN PARALELA: RED + PARSER)")
    print("======================================================================")
    
    metrics = PerformanceTracker()
    downloader = RUCTDownloader(metrics_tracker=metrics)
    logger = ErrorLogger()
    checkpoint = CheckpointManager()

    # -------------------------------------------------------------------------
    # INICIALIZACIÓN DE COMPUTACIÓN PARALELA (PROCESO 1: RED | PROCESO 2: PARSER)
    # -------------------------------------------------------------------------
    task_queue = mp.Queue(maxsize=100)
    result_queue = mp.Queue()

    parser_process = mp.Process(
        target=pdf_parser_consumer,
        args=(task_queue, result_queue),
        daemon=True
    )
    parser_process.start()
    print(" -> Proceso 2 (Parser CPU & Escritura en Disco) arrancado y listo en segundo plano.")
    
    # -------------------------------------------------------------------------
    # PASO 1: Descargar listado oficial actualizado de universidades (PROCESO 1)
    # -------------------------------------------------------------------------
    print("\n[Paso 1] Obteniendo listado oficial de universidades...")
    universities = []
    try:
        temp_univ_xls = os.path.join(TEMP_PDF_DIR, "universidades_list.xls")
        downloader.download_file(URL_UNIVERSIDADES_LIST, temp_univ_xls)
        universities = parse_universities_xls(temp_univ_xls)
        
        atomic_json_dump(universities, UNIVERSIDADES_JSON)
            
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
    # PASO 2 y 3: Recorrer TODAS las universidades (PROCESO 1: RED I/O)
    # -------------------------------------------------------------------------
    print("\n[Paso 2 y 3] Inspeccionando titulaciones vigentes y descargando PDFs candidatos...")
    total_univ = len(universities)
    
    for u_idx, univ in enumerate(universities, 1):
        u_code = univ.get("codigo", "")
        u_name = univ.get("nombre", "")
        print(f"\n({u_idx}/{total_univ}) Procesando Universidad [{u_code}]: {u_name}")
        
        downloader.reset_university_context(u_code)

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
            
            atomic_json_dump(titulaciones_por_universidad, TITULACIONES_JSON)
                
            if os.path.exists(temp_degrees_xls):
                os.remove(temp_degrees_xls)
                
            print(f"     -> {len(active_degrees)} titulaciones VIGENTES/RENOVADAS identificadas.")

        except SkipUniversityException as conn_exc:
            err_msg = f"Problemas de conexion continuados en la universidad [{u_code}] {u_name}"
            print(f"     -> [CORTOCIRCUITO] {err_msg}")
            logger.log_error("paso_2_conexion_fallida", u_code, degrees_url, "Problemas de conexion continuados", str(conn_exc))
            metrics.errores_detectados += 1
            continue
        except Exception as e:
            err_msg = f"Error al obtener listado de titulaciones para la universidad {u_code}"
            print(f"     -> [ERROR NO BLOQUEANTE] {err_msg}: {e}")
            logger.log_error("paso_2_titulaciones_xls", u_code, URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo=u_code), err_msg, traceback.format_exc())
            metrics.errores_detectados += 1
            continue

        degrees_to_process = active_degrees
        if limit_degrees:
            degrees_to_process = degrees_to_process[:limit_degrees]

        # Inspect each degree for latest BOE and download PDF candidates in Process 1
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
                candidates = boe_info.get("all_boe_candidates", [])
                
                latest_boe_url = boe_info.get("latest_boe_url")
                latest_boe_fecha = boe_info.get("boe_date")
                
                # Check if degree is already up to date
                if os.path.exists(plan_file) and checkpoint.is_degree_up_to_date(d_code, latest_boe_url, latest_boe_fecha):
                    metrics.titulaciones_al_dia += 1
                    print(f"     -> Información al día (BOE {latest_boe_fecha or 'coincide'}). Sin cambios necesarios.")
                    continue

                if not candidates:
                    task_queue.put({
                        "type": "DEGREE_NO_BOE",
                        "d_code": d_code,
                        "d_title": d_title,
                        "u_code": u_code,
                        "u_name": u_name,
                        "nivel_academico": deg.get("nivel_academico", "")
                    })
                    continue

                # Download all PDF candidates in Process 1 and queue them for Process 2
                downloaded_pdf_items = []
                for cand_idx, cand in enumerate(candidates, 1):
                    cand_url = cand["url"]
                    cand_date = cand.get("boe_date")
                    pdf_path = os.path.join(TEMP_PDF_DIR, f"{d_code}_candidate_{cand_idx}.pdf")
                    
                    try:
                        print(f"     [Proceso Red] -> Descargando PDF #{cand_idx}/{len(candidates)} ({cand_date or 'fecha n/a'})...")
                        downloader.download_file(cand_url, pdf_path)
                        downloaded_pdf_items.append({
                            "cand_url": cand_url,
                            "cand_date": cand_date,
                            "pdf_path": pdf_path
                        })
                    except SkipUniversityException:
                        raise
                    except Exception as download_err:
                        print(f"     [Proceso Red] -> Error al descargar PDF candidate #{cand_idx}: {download_err}")

                # Send task item to Producer-Consumer queue for Process 2 parsing
                task_queue.put({
                    "type": "PARSE_DEGREE_PDFS",
                    "d_code": d_code,
                    "d_title": d_title,
                    "u_code": u_code,
                    "u_name": u_name,
                    "nivel_academico": deg.get("nivel_academico", ""),
                    "latest_boe_url": latest_boe_url,
                    "latest_boe_fecha": latest_boe_fecha,
                    "pdf_items": downloaded_pdf_items
                })

            except SkipUniversityException as conn_exc:
                err_msg = f"Problemas de conexion continuados en la universidad [{u_code}] {u_name}"
                print(f"     -> [CORTOCIRCUITO] {err_msg}")
                logger.log_error("paso_3_conexion_fallida", u_code, detail_url, "Problemas de conexion continuados", str(conn_exc))
                metrics.errores_detectados += 1
                break
            except Exception as e:
                err_msg = f"Error al procesar la titulación [{d_code}]"
                print(f"     -> [ERROR NO BLOQUEANTE] {err_msg}: {e}")
                logger.log_error("paso_3_boe_pdf", d_code, detail_url, err_msg, traceback.format_exc())
                metrics.errores_detectados += 1
                continue

        metrics.save()
        checkpoint.mark_university_processed(u_code)

    # -------------------------------------------------------------------------
    # FINALIZACIÓN DE PROCESOS PARALELOS
    # -------------------------------------------------------------------------
    print("\n[Finalizando Red] Enviando señal de parada al Proceso 2 (Parser CPU)...")
    task_queue.put({"type": "STOP"})
    
    # Receive metrics summary from Process 2
    consumer_results = result_queue.get()
    parser_process.join()

    metrics.pdfs_parseados = consumer_results.get("parsed_count", 0)
    metrics.titulaciones_descargadas_actualizadas = consumer_results.get("updated_degrees_count", 0)
    metrics.save()

    print("\n" + "=" * 70)
    print("      CRAWLER UNIHUB PARALELO FINALIZADO CON ÉXITO Y DE FORMA RESILIENTE")
    print("======================================================================")
    print(f" -> Universidades inspeccionadas: {metrics.universidades_inspeccionadas}")
    print(f" -> Titulaciones inspeccionadas:  {metrics.titulaciones_inspeccionadas}")
    print(f" -> Titulaciones al día:          {metrics.titulaciones_al_dia}")
    print(f" -> Titulaciones actualizadas:    {metrics.titulaciones_descargadas_actualizadas}")
    print(f" -> PDFs parseados del BOE:       {metrics.pdfs_parseados}")
    print(f" -> Errores (registrados en log): {metrics.errores_detectados}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawler UniHub para scraping de RUCT y BOE.")
    parser.add_argument("--limit-univ", type=int, default=None, help="Limitar número de universidades a procesar.")
    parser.add_argument("--limit-degrees", type=int, default=None, help="Limitar número de titulaciones por universidad.")
    args = parser.parse_args()

    run_crawler(limit_univ=args.limit_univ, limit_degrees=args.limit_degrees)
    
    # Notify REST API ETL process automatically upon completion
    trigger_api_etl_sync()
    print(f" -> Métricas guardadas en:        '{ESTADISTICAS_JSON}'")
    print("======================================================================")

    # Automatic notification to Phase 2 API REST to trigger PostgreSQL ETL sync
    trigger_api_etl_sync()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawler para UniHub (Universidades y Titulaciones de España)")
    parser.add_argument("--limit-univ", type=int, default=None, help="Limitar número de universidades a procesar (para pruebas)")
    parser.add_argument("--limit-degrees", type=int, default=None, help="Limitar número de titulaciones por universidad (para pruebas)")
    args = parser.parse_args()

    run_crawler(limit_univ=args.limit_univ, limit_degrees=args.limit_degrees)
