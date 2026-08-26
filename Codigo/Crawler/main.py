import os
import sys
import re
import json
import time
import signal
import logging
import requests
import traceback
import argparse
import concurrent.futures
import multiprocessing as mp
from datetime import datetime

# Docker / multiprocessing: usar 'spawn' para compatibilidad con contenedores Linux
try:
    mp.set_start_method('spawn', force=True)
except RuntimeError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(processName)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from bs4 import BeautifulSoup

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
    URL_DETALLE_ESTUDIO_TEMPLATE,
    URL_VERIFICACION_ESTADO_TEMPLATE,
    CPU_WORKERS_COUNT,
    ASYNC_PREFETCH_WORKERS,
    WEB_CRAWLER_WORKERS,
    TASK_QUEUE_MAXSIZE,
    TASK_QUEUE_GET_TIMEOUT,
    MAX_BOE_CANDIDATES_PER_DEGREE
)
from downloader import RUCTDownloader, SkipUniversityException
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump
from metrics import PerformanceTracker
from parsers import (
    parse_universities_xls,
    parse_degrees_xls,
    parse_degree_detail_html,
    parse_boe_pdf,
    is_curriculum_complete,
    get_curriculum_completeness_status,
    is_doctorate_program
)
from univ_web_crawler import run_phase1_part2
from precios_crawler import run_phase1_part3
from asignaturas_crawler import run_phase1_part4

# Ensure Windows terminal stdout handles unicode characters safely
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def save_degree_payload(plan_file: str, d_code: str, d_title: str, u_code: str, u_name: str, 
                        nivel_academico: str, boe_url: str = None, boe_fecha: str = None, 
                        plan_estudios: dict = None, all_boe_urls: list = None, 
                        origen_fuente: str = None, checkpoint_mgr=None, existing_data: dict = None):
    """
    Guarda atómicamente el payload JSON del plan de estudios y actualiza el checkpoint del sistema.
    """
    payload = existing_data if existing_data is not None else {}
    now_iso = datetime.now().isoformat()
    payload.update({
        "codigo_estudio": d_code,
        "titulo": d_title,
        "nivel_academico": nivel_academico,
        "universidad_codigo": u_code,
        "universidad_nombre": u_name,
        "fecha_procesado": now_iso,
        "boe_url": boe_url,
        "boe_fecha": boe_fecha
    })
    if plan_estudios is not None:
        payload["plan_estudios"] = plan_estudios
    elif "plan_estudios" not in payload:
        payload["plan_estudios"] = None
        
    if all_boe_urls:
        payload["all_boe_urls"] = all_boe_urls
    if origen_fuente:
        payload["origen_fuente"] = origen_fuente

    atomic_json_dump(payload, plan_file)
    if checkpoint_mgr:
        checkpoint_mgr.update_degree_record(d_code, boe_url, boe_fecha, now_iso)


def pdf_parser_consumer(task_queue: mp.Queue, result_queue: mp.Queue = None):
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
            task = task_queue.get(timeout=TASK_QUEUE_GET_TIMEOUT)
            if task is None or (isinstance(task, dict) and task.get("type") == "STOP"):
                if result_queue is not None:
                    try:
                        result_queue.put({
                            "parsed_count": parsed_count,
                            "updated_degrees_count": updated_degrees_count,
                            "total_parse_time": total_parse_time
                        })
                    except Exception:
                        pass
                break
        except Exception:
            # Timeout para permitir chequeo de terminación y evitar bloqueo eterno
            continue

        try:
            task_type = task.get("type")
            d_code = task.get("d_code", "")
            d_title = task.get("d_title", "")
            u_code = task.get("u_code", "")
            u_name = task.get("u_name", "")
            nivel_academico = task.get("nivel_academico", "")
            latest_boe_url = task.get("latest_boe_url")
            latest_boe_fecha = task.get("latest_boe_fecha")
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
            existing_degree_data = {}
            if os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        existing_degree_data = json.load(f)
                except Exception:
                    pass

            is_doctorado = is_doctorate_program(nivel_academico, d_title)

            if task_type == "DEGREE_NO_BOE":
                print(f"     [Proceso Parser] -> [AVISO] Sin enlaces a BOE para [{d_code}]. Guardando metadatos base.")
                plan_doc = None
                if is_doctorado:
                    plan_doc = {
                        "tipo_estructura": "programa_doctorado_investigacion",
                        "normativa": "Real Decreto 99/2011",
                        "descripcion_plan": "Programa Oficial de Doctorado centrado en la investigación avanzada, elaboración y defensa de Tesis Doctoral conforme al Real Decreto 99/2011.",
                        "actividades_formativas": "Seminarios de investigación, estancias internacionales, publicaciones científicas y tutela académica anual.",
                        "resumen_creditos": {"Tutela Académica Anual": "60 ECTS Equiv."},
                        "total_elementos": 0,
                        "elementos_curriculares": []
                    }
                save_degree_payload(
                    plan_file=plan_file,
                    d_code=d_code,
                    d_title=d_title,
                    u_code=u_code,
                    u_name=u_name,
                    nivel_academico=nivel_academico,
                    boe_url=None,
                    boe_fecha=None,
                    plan_estudios=plan_doc,
                    checkpoint_mgr=checkpoint,
                    existing_data=existing_degree_data
                )

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
                    pdf_path = item.get("pdf_path")
                    pdf_bytes = item.get("pdf_bytes")

                    try:
                        t_start = time.perf_counter()
                        # OPT-04: Prefer in-memory bytes if available, fallback to file path
                        pdf_input = pdf_bytes if pdf_bytes else pdf_path
                        if not pdf_input:
                            continue

                        curriculum_data = parse_boe_pdf(pdf_input, target_title=d_title, univ_name=u_name)
                        t_elapsed = time.perf_counter() - t_start
                        total_parse_time += t_elapsed
                        parsed_count += 1

                        pdf_sha256 = curriculum_data.get("pdf_sha256")
                        if pdf_sha256 and checkpoint.is_non_study_plan_hash(pdf_sha256):
                            print(f"     [Proceso Parser] -> [OPT-06 CACHÉ HASH] PDF #{cand_idx} de [{d_code}] previamente marcado como NO plan de estudios por Hash SHA256. Omitiendo.")
                            continue

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

                            # Indicación 1: Fusión Inteligente Multi-BOE
                            # 1. El BOE más reciente (cand_idx == 1) define la estructura vigente con máxima prioridad.
                            # 2. Los BOEs anteriores (cand_idx > 1) solo aportan asignaturas de cursos o módulos que no fueron
                            #    publicados en el BOE de modificación parcial, descartando materias obsoletas, renombradas o desdobladas.
                            is_latest = (cand_idx == 1)
                            new_elements = curriculum_data.get("elementos_curriculares", [])

                            if is_latest:
                                for elem in new_elements:
                                    raw_name = elem.get("nombre_elemento", "").strip()
                                    norm_name = re.sub(r"\s*\(.*?\)", "", raw_name).strip().lower()
                                    if norm_name and norm_name not in seen_subject_names:
                                        seen_subject_names.add(norm_name)
                                        combined_elementos.append(elem)
                            else:
                                # Calcular créditos por curso ya cubiertos en el plan vigente
                                covered_courses = {}
                                for ex_elem in combined_elementos:
                                    c_tag = str(ex_elem.get("curso") or "").strip()
                                    try:
                                        c_ects = float(str(ex_elem.get("creditos_ects") or 6).replace(",", "."))
                                    except ValueError:
                                        c_ects = 6.0
                                    covered_courses[c_tag] = covered_courses.get(c_tag, 0.0) + c_ects

                                for elem in new_elements:
                                    raw_name = elem.get("nombre_elemento", "").strip()
                                    norm_name = re.sub(r"\s*\(.*?\)", "", raw_name).strip().lower()
                                    c_tag = str(elem.get("curso") or "").strip()

                                    # Si el curso ya tiene sus créditos completos en el plan vigente, omitir asignaturas viejas
                                    if c_tag and covered_courses.get(c_tag, 0) >= 55.0:
                                        continue

                                    # Si el nombre ya existe en el plan vigente, omitir
                                    if not norm_name or norm_name in seen_subject_names:
                                        continue

                                    # Detección de colisión léxica con asignaturas renombradas o desdobladas
                                    tokens_new = set(re.findall(r"\w{4,}", norm_name))
                                    has_collision = False
                                    if tokens_new:
                                        for ex_name in seen_subject_names:
                                            tokens_ex = set(re.findall(r"\w{4,}", ex_name))
                                            if tokens_new and tokens_ex and len(tokens_new & tokens_ex) >= max(2, len(tokens_new) - 1):
                                                has_collision = True
                                                break
                                    if has_collision:
                                        continue

                                    seen_subject_names.add(norm_name)
                                    combined_elementos.append(elem)

                            # Si el plan ya está 100% completo, no es necesario procesar BOEs históricos más antiguos
                            test_deg_probe = {
                                "nivel_academico": nivel_academico,
                                "titulo": d_title,
                                "plan_estudios": {
                                    "resumen_creditos": combined_resumen_creditos,
                                    "elementos_curriculares": combined_elementos
                                }
                            }
                            if is_curriculum_complete(test_deg_probe):
                                break
                        else:
                            print(f"     [Proceso Parser] -> PDF #{cand_idx} de [{d_code}] no contenía tabla de asignaturas. Registrando como NO plan de estudios.")
                            checkpoint.mark_non_study_plan_pdf(cand_url, pdf_sha256)

                    except Exception as pdf_err:
                        print(f"     [Proceso Parser] -> Error al procesar PDF candidate #{cand_idx} de [{d_code}]: {pdf_err}")
                        logger.log_error("paso_3_parse_pdf", d_code, cand_url, f"Error en parser PDF #{cand_idx}", str(pdf_err))
                    finally:
                        if pdf_path and os.path.exists(pdf_path):
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
                    test_deg_final = {
                        "nivel_academico": nivel_academico,
                        "titulo": d_title,
                        "plan_estudios": curriculum_combined
                    }
                    comp_status = get_curriculum_completeness_status(test_deg_final)
                    curriculum_combined["plan_completo"] = comp_status["is_complete"]
                    curriculum_combined["ects_totales_detectados"] = comp_status["total_ects_obtained"]
                    curriculum_combined["ects_exigidos"] = comp_status["required_ects"]

                    save_degree_payload(
                        plan_file=plan_file,
                        d_code=d_code,
                        d_title=d_title,
                        u_code=u_code,
                        u_name=u_name,
                        nivel_academico=nivel_academico,
                        boe_url=latest_boe_url,
                        boe_fecha=latest_boe_fecha,
                        plan_estudios=curriculum_combined,
                        all_boe_urls=task.get("all_boe_urls", processed_boe_urls),
                        origen_fuente="boe",
                        checkpoint_mgr=checkpoint,
                        existing_data=existing_degree_data
                    )
                else:
                    print(f"     [Proceso Parser] -> [AVISO] Ningún PDF de [{d_code}] contenía asignaturas desglosadas. Guardando metadatos base.")
                    save_degree_payload(
                        plan_file=plan_file,
                        d_code=d_code,
                        d_title=d_title,
                        u_code=u_code,
                        u_name=u_name,
                        nivel_academico=nivel_academico,
                        boe_url=latest_boe_url,
                        boe_fecha=latest_boe_fecha,
                        plan_estudios=existing_degree_data.get("plan_estudios"),
                        checkpoint_mgr=checkpoint,
                        existing_data=existing_degree_data
                    )

        except Exception as consumer_err:
            print(f"     [Proceso Parser ERROR] Excepción inesperada en consumidor: {consumer_err}")


def trigger_api_etl_sync():
    """Notifica a la API REST de la Fase 2 para iniciar la sincronización ETL relacional automáticamente."""
    target_urls = [
        os.getenv("API_SYNC_URL", "http://api:8000/api/v1/admin/sync-etl"),
        "http://unihub_api:8000/api/v1/admin/sync-etl",
        "http://localhost:8000/api/v1/admin/sync-etl"
    ]
    print("\n[Fase 1 Completa -> Fase 2] Notificando a la API REST para sincronización ETL en PostgreSQL...")
    
    # Se requiere la API Key para autorizar la sincronización ETL
    api_key = os.getenv("ADMIN_API_KEY", "unihub_super_secret_admin_key_2026")
    headers = {"X-API-Key": api_key}
    
    for sync_url in target_urls:
        try:
            resp = requests.post(sync_url, headers=headers, timeout=5)
            if resp.ok:
                print(f" -> Sincronización ETL iniciada con éxito en la API REST ({sync_url}).")
                return
        except Exception:
            continue
    print(" -> Nota: La Fase 1 ha finalizado. La Fase 2 se sincronizará cuando el servicio API esté disponible o se ejecute el ETL.")


_GLOBAL_CHECKPOINT = None
_GLOBAL_METRICS = None

def run_crawler(limit_univ: int = None, limit_degrees: int = None, run_parts: list = None, force: bool = False):
    global _GLOBAL_CHECKPOINT, _GLOBAL_METRICS
    if run_parts is None:
        run_parts = [1, 2, 3]

    print("=" * 70)
    print("      INICIANDO FASE 1 UNIHUB (PARTES SELECCIONADAS: " + ", ".join(f"Parte {p}" for p in run_parts) + ")")
    print("======================================================================")

    metrics = PerformanceTracker()
    _GLOBAL_METRICS = metrics
    downloader = RUCTDownloader(metrics_tracker=metrics)
    logger = ErrorLogger()
    checkpoint = CheckpointManager()
    _GLOBAL_CHECKPOINT = checkpoint

    # Ajuste Docker: limitar workers al número de CPUs disponibles en el contenedor
    cpu_count = os.cpu_count() or 1
    def _cap_workers(desired):
        # No superar CPUs disponibles y respetar config mínima
        return max(1, min(desired, cpu_count))

    # -------------------------------------------------------------------------
    # PARTE 1 DE LA FASE 1: SCRAPING RUCT Y PARSER DE BOE
    # -------------------------------------------------------------------------
    if 1 in run_parts:
        # Limpieza preventiva de archivos temporales huérfanos de ejecuciones anteriores
        if os.path.exists(TEMP_PDF_DIR):
            for f_name in os.listdir(TEMP_PDF_DIR):
                if f_name.endswith(('.tmp', '.pdf', '.xls', '.download')):
                    try:
                        os.remove(os.path.join(TEMP_PDF_DIR, f_name))
                    except Exception:
                        pass

        # OPT-01: Lanzar Pool Multiprocesador de Consumidores (Parser CPU & Escritura en Disco)
        num_parser_workers = _cap_workers(CPU_WORKERS_COUNT)
        task_queue = mp.Queue(maxsize=TASK_QUEUE_MAXSIZE)
        result_queue = mp.Queue()
        parser_processes = []
        for w_idx in range(num_parser_workers):
            p = mp.Process(target=pdf_parser_consumer, args=(task_queue, result_queue), daemon=True)
            p.start()
            parser_processes.append(p)
        print(f" -> Proceso 2 (Pool de {num_parser_workers} trabajadores Parser CPU) arrancado y listo en segundo plano.\n")

        # -------------------------------------------------------------------------
        # PASO 1: Descargar / Inspeccionar listado de universidades (Públicas prioritarias)
        # -------------------------------------------------------------------------
        print("[Paso 1] Obteniendo listado oficial de universidades (Públicas prioritarias)...")
        univ_file = os.path.join(TEMP_PDF_DIR, "universidades_list.xls")
        
        try:
            t0 = time.perf_counter()
            downloader.download_file(URL_UNIVERSIDADES_LIST, univ_file)
            metrics.record_io_time(time.perf_counter() - t0)
            universities = parse_universities_xls(univ_file)
            
            # MERGE: Preservar las URLs que han sido rescatadas/corregidas por Wikidata en ejecuciones anteriores
            if os.path.exists(UNIVERSIDADES_JSON):
                try:
                    with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
                        old_univs = json.load(f)
                        old_map = {u["codigo"]: u for u in old_univs}
                        for new_u in universities:
                            old_u = old_map.get(new_u["codigo"])
                            if old_u and old_u.get("web_corregida_por_wikidata"):
                                new_u["web"] = old_u["web"]
                                new_u["web_corregida_por_wikidata"] = True
                except Exception:
                    pass

            atomic_json_dump(universities, UNIVERSIDADES_JSON)
            checkpoint.mark_universities_downloaded()
            print(f" -> {len(universities)} universidades comprobadas y actualizadas en '{UNIVERSIDADES_JSON}'.")
        except Exception as e:
            err_msg = "Error crítico al descargar el catálogo general de universidades"
            print(f" [ERROR CRÍTICO] {err_msg}: {e}")
            logger.log_error("paso_1_universidades", "ALL", URL_UNIVERSIDADES_LIST, err_msg, str(e))
            metrics.errores_detectados += 1
            for p in parser_processes:
                if p.is_alive():
                    try:
                        task_queue.put({"type": "STOP"}, timeout=2)
                    except Exception:
                        pass
                    p.join(timeout=2)
                    if p.is_alive():
                        p.terminate()
            return

        if limit_univ:
            universities = universities[:limit_univ]

        # -------------------------------------------------------------------------
        # PASOS 2 Y 3: Inspeccionar titulaciones por universidad y descargar PDFs candidatos
        # -------------------------------------------------------------------------
        print("\n[Paso 2 y 3] Inspeccionando titulaciones vigentes y descargando PDFs candidatos...\n")
        titulaciones_por_universidad = {}
        if os.path.exists(TITULACIONES_JSON):
            try:
                with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
                    titulaciones_por_universidad = json.load(f)
            except Exception:
                titulaciones_por_universidad = {}

        for u_idx, univ in enumerate(universities, 1):
            metrics.universidades_inspeccionadas += 1
            u_code = univ["codigo"]
            u_name = univ["nombre"]
            u_tipo = univ.get("tipo", "Desconocido")

            downloader.reset_university_context(u_code)
            print(f"({u_idx}/{len(universities)}) Procesando Universidad [{u_code}] ({u_tipo}): {u_name}")

            univ_degrees_file = os.path.join(TEMP_PDF_DIR, f"degrees_{u_code}.xls")
            try:
                degrees_url = URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo_universidad=u_code, codigo=u_code)
            except KeyError:
                degrees_url = URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo=u_code)

            try:
                t0 = time.perf_counter()
                downloader.download_file(degrees_url, univ_degrees_file)
                metrics.record_io_time(time.perf_counter() - t0)
                active_degrees = parse_degrees_xls(univ_degrees_file)
            except SkipUniversityException as conn_exc:
                err_msg = f"Problemas de conexion continuados en la universidad [{u_code}] {u_name}"
                print(f"     -> [CORTOCIRCUITO] {err_msg}")
                logger.log_error("paso_2_titulaciones_univ", u_code, degrees_url, "Problemas de conexion continuados", str(conn_exc))
                metrics.errores_detectados += 1
                continue
            except Exception as e:
                err_msg = f"Error al procesar la lista de titulaciones de la universidad [{u_code}]"
                print(f"     -> [ERROR NO BLOQUEANTE] {err_msg}: {e}")
                logger.log_error("paso_2_titulaciones_univ", u_code, degrees_url, err_msg, str(e))
                metrics.errores_detectados += 1
                continue

            print(f"     -> {len(active_degrees)} titulaciones VIGENTES/RENOVADAS identificadas.")

            titulaciones_por_universidad[u_code] = {
                "universidad_codigo": u_code,
                "universidad_nombre": u_name,
                "tipo": u_tipo,
                "total_titulaciones_vigentes": len(active_degrees),
                "titulaciones_vigentes": active_degrees
            }
            if u_idx % 5 == 0 or u_idx == len(universities):
                atomic_json_dump(titulaciones_por_universidad, TITULACIONES_JSON)

            # REQUERIMIENTO: Procesar titulaciones en orden inverso (última primero)
            degrees_to_process = active_degrees[::-1]
            if limit_degrees:
                degrees_to_process = degrees_to_process[:limit_degrees]

            # Inspect each degree for latest BOE and download PDF candidates in Process 1
            for d_idx, deg in enumerate(degrees_to_process, 1):
                metrics.titulaciones_inspeccionadas += 1
                d_code = deg.get("codigo_estudio", "")
                d_title = deg.get("titulo", "")
                print(f"   [{d_idx}/{len(degrees_to_process)}] Titulación [{d_code}]: {d_title[:65]}...")
                
                if checkpoint.is_extinct_degree(d_code):
                    print(f"     -> [DESECHADO] Titulación [{d_code}] ya registrada como INACTIVA/EXTINGUIDA en checkpoint. Omitiendo en 0ms.")
                    continue

                plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
                detail_url = URL_DETALLE_ESTUDIO_TEMPLATE.format(codigo_estudio=d_code)
            
                try:
                    html_content = downloader.fetch_text(detail_url)
                    boe_info = parse_degree_detail_html(html_content)

                    is_extinct = boe_info.get("is_extinct", False)
                    st_text = boe_info.get("status_text", "")
                    candidates = boe_info.get("all_boe_candidates", [])

                    # Si no hay candidatos BOE y no se detectó extinción en la ficha de detalle, consultar listaestudios
                    if not candidates and not is_extinct:
                        status_url = URL_VERIFICACION_ESTADO_TEMPLATE.format(codigo_estudio=d_code)
                        try:
                            st_html = downloader.fetch_text(status_url)
                            st_soup = BeautifulSoup(st_html, "html.parser")
                            full_st_text = st_soup.get_text()
                            if "(TITULACIÓN EXTINGUIDA)" in full_st_text or "EXTINGUID" in full_st_text.upper() or "SIN DOCENCIA" in full_st_text.upper():
                                is_extinct = True
                                st_text = "TITULACIÓN EXTINGUIDA"
                        except Exception:
                            pass

                    if is_extinct:
                        print(f"     -> [DESECHADO] Titulación [{d_code}] confirmada como INACTIVA/EXTINGUIDA en RUCT ({st_text or 'Extinguida'}). Omitiendo.")
                        checkpoint.mark_extinct_degree(d_code, st_text or "Extinguida")
                        continue
                
                    latest_boe_url = boe_info.get("latest_boe_url")
                    latest_boe_fecha = boe_info.get("boe_date")
                
                    # Check if degree is already up to date (bypassed if --force is active)
                    if not force and os.path.exists(plan_file) and checkpoint.is_degree_up_to_date(d_code, latest_boe_url, latest_boe_fecha):
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

                    # Seleccionar todos los PDFs pertenecientes a los fieldsets de Plan de Estudios y Correcciones (prioridad >= 90)
                    # Si no existen fieldsets específicos (fallback), tomar los primeros candidatos ordenados por fecha
                    high_priority_candidates = [c for c in candidates if c.get("priority", 0) >= 90]
                    if high_priority_candidates:
                        target_candidates = high_priority_candidates[:MAX_BOE_CANDIDATES_PER_DEGREE]
                        if len(high_priority_candidates) > len(target_candidates):
                            print(f"     -> Procesando los {len(target_candidates)} BOEs del plan de estudios más relevantes (acotados por límite de seguridad).")
                    else:
                        target_candidates = [c for c in candidates if c.get("priority", 0) > 0][:MAX_BOE_CANDIDATES_PER_DEGREE]

                    # OPT-04: Fetch candidate PDF in-memory (bytes) to avoid disk temporary file IOPS
                    downloaded_pdf_items = []

                    def fetch_single_candidate(cand_tuple):
                        cand_idx, cand = cand_tuple
                        cand_url = cand["url"]
                        cand_date = cand.get("boe_date")

                        cand_label = "PDF más reciente" if cand_idx == 1 else f"PDF candidato #{cand_idx}"
                        if checkpoint.is_non_study_plan_pdf(cand_url):
                            print(f"     [Proceso Red] -> {cand_label} previamente descartado (NO es plan de estudios). Omitiendo descarga.")
                            return None

                        if checkpoint.is_unreachable_url(cand_url):
                            print(f"     [Proceso Red] -> {cand_label} previamente registrado como inalcanzable (servidor inactivo). Omitiendo descarga.")
                            return None

                        try:
                            print(f"     [Proceso Red] -> Obteniendo {cand_label} del BOE ({cand_date or 'fecha n/a'})...")
                            # OPT-04: Fetch in-memory bytes
                            pdf_bytes = downloader.fetch_content(cand_url)
                            return {
                                "cand_url": cand_url,
                                "cand_date": cand_date,
                                "pdf_bytes": pdf_bytes
                            }
                        except SkipUniversityException:
                            raise
                        except Exception as download_err:
                            print(f"     [Proceso Red] -> Error al descargar PDF del BOE: {download_err}")
                            checkpoint.record_pdf_download_failure(cand_url, d_code, str(download_err))
                            return None

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        futures = [executor.submit(fetch_single_candidate, (c_idx, c)) for c_idx, c in enumerate(target_candidates, 1)]
                        for future in concurrent.futures.as_completed(futures):
                            try:
                                item_res = future.result()
                        except Exception as e:
                            logger.log_error("paso_3_descarga_pdf", d_code, cand_url, "Fallo al descargar PDF candidato", str(e))
                            return None

                    # Limitar concurrencia de descarga
                    cands_to_fetch = candidates[:MAX_BOE_CANDIDATES_PER_DEGREE]
                    for c_cand in cands_to_fetch:
                        res_item = fetch_single_candidate(c_cand)
                        if res_item:
                            downloaded_pdf_items.append(res_item)

                    if not downloaded_pdf_items:
                        continue

                    # Encolar la titulación hacia el Pool de Procesos 2 (Consumidores de CPU)
                    task_queue.put({
                        "type": "PARSE_DEGREE_PDFS",
                        "d_code": d_code,
                        "d_title": d_title,
                        "u_code": u_code,
                        "u_name": u_name,
                        "nivel_academico": deg.get("nivel_academico", ""),
                        "latest_boe_url": latest_boe_url,
                        "latest_boe_fecha": latest_boe_fecha,
                        "all_boe_urls": [c["url"] for c in candidates],
                        "pdf_items": downloaded_pdf_items
                    })

                except SkipUniversityException as conn_exc:
                    err_msg = f"Problemas de conexion continuados en la universidad [{u_code}] {u_name}"
                    print(f"     -> [CORTOCIRCUITO] {err_msg}")
                    logger.log_error("paso_3_conexion_fallida", u_code, detail_url, "Problemas de conexion continuados", str(conn_exc))
                    metrics.errores_detectados += 1
                    univ_completed_cleanly = False
                    break
                except Exception as e:
                    err_msg = f"Error al procesar la titulación [{d_code}]"
                    print(f"     -> [ERROR NO BLOQUEANTE] {err_msg}: {e}")
                    logger.log_error("paso_3_boe_pdf", d_code, detail_url, err_msg, traceback.format_exc())
                    metrics.errores_detectados += 1
                    continue

            metrics.save()
            if univ_completed_cleanly:
                checkpoint.mark_university_processed(u_code)
            else:
                print(f" ⚠️ [AVISO] Universidad [{u_code}] no completada por problemas de conexión. Se mantiene pendiente en checkpoint.")

        # Finalización segura del Pool de Procesos 2 (Parser CPU)
        print("\n[Finalizando Red] Enviando señal de parada al Pool de Procesos Parser CPU...")
        for _ in range(num_parser_workers):
            try:
                task_queue.put({"type": "STOP"}, timeout=3)
            except Exception:
                pass
        
        # Receive metrics summary from Process 2 pool
        total_parsed = 0
        total_updated = 0
        total_parse_time = 0.0
        for _ in range(num_parser_workers):
            try:
                consumer_results = result_queue.get(timeout=5)
                total_parsed += consumer_results.get("parsed_count", 0)
                total_updated += consumer_results.get("updated_degrees_count", 0)
                total_parse_time += consumer_results.get("total_parse_time", 0.0)
            except Exception:
                pass
        
        metrics.pdfs_parseados = total_parsed
        metrics.titulaciones_descargadas_actualizadas = total_updated
        metrics.total_pdf_parsing_time = round(total_parse_time, 2)

        for p in parser_processes:
            p.join(timeout=5)
            if p.is_alive():
                print(" [AVISO] Forzando terminación de subproceso parser colgado.")
                p.terminate()
        
        metrics.save()

        print("\n" + "=" * 70)
        print("      CRAWLER UNIHUB PARTE 1 FINALIZADO CON ÉXITO")
        print("======================================================================")
        print(f" -> Universidades inspeccionadas: {metrics.universidades_inspeccionadas}")
        print(f" -> Titulaciones inspeccionadas:  {metrics.titulaciones_inspeccionadas}")
        print(f" -> Titulaciones al día:          {metrics.titulaciones_al_dia}")
        print(f" -> Titulaciones actualizadas:    {metrics.titulaciones_descargadas_actualizadas}")
        print(f" -> PDFs parseados del BOE:       {metrics.pdfs_parseados}")
        print(f" -> Errores (registrados en log): {metrics.errores_detectados}")

    # -------------------------------------------------------------------------
    # PARTE 2 DE LA FASE 1: ESCANEO PARALELO DE LAS WEBS OFICIALES DE UNIVERSIDADES
    # -------------------------------------------------------------------------
    if 2 in run_parts:
        print("\n -> Inicializando Fase 1 - Parte 2 (Rastreo paralelo de webs oficiales de universidades)...")
        run_phase1_part2(max_workers=WEB_CRAWLER_WORKERS, metrics_tracker=metrics)

    # -------------------------------------------------------------------------
    # PARTE 3 DE LA FASE 1: CÁLCULO DE PRECIOS ECTS Y MATRÍCULAS DE UNIVERSIDADES PÚBLICAS
    # -------------------------------------------------------------------------
    if 3 in run_parts:
        run_phase1_part3()

    # -------------------------------------------------------------------------
    # PARTE 4 DE LA FASE 1: GUÍAS DOCENTES Y TEMARIOS DETALLADOS (EEES / BOLONIA)
    # -------------------------------------------------------------------------
    if 4 in run_parts:
        run_phase1_part4(limit_univ=limit_univ, limit_degrees=limit_degrees, force=force)

    # -------------------------------------------------------------------------
    # PERSISTENCIA FINAL DE MÉTRICAS Y CHECKPOINTS
    # -------------------------------------------------------------------------
    metrics.save()
    checkpoint.flush()

    # -------------------------------------------------------------------------
    # NOTIFICACIÓN A FASE 2: AL FINALIZAR LAS PARTES SOLICITADAS
    # -------------------------------------------------------------------------
    trigger_api_etl_sync()
    print(f" -> Métricas guardadas en:        '{ESTADISTICAS_JSON}'")
    print("======================================================================")


def _handle_sigterm(signum, frame):
    print("\n[SIGNAL] Señal de terminación recibida. Vaciando checkpoints y métricas a disco...")
    global _GLOBAL_CHECKPOINT, _GLOBAL_METRICS
    if _GLOBAL_CHECKPOINT:
        try:
            _GLOBAL_CHECKPOINT.flush()
        except Exception:
            pass
    if _GLOBAL_METRICS:
        try:
            _GLOBAL_METRICS.save()
        except Exception:
            pass
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    parser = argparse.ArgumentParser(description="Crawler UniHub para scraping de RUCT, BOE y webs oficiales de universidades.")
    parser.add_argument("--limit-univ", type=int, default=None, help="Limitar número de universidades a procesar.")
    parser.add_argument("--limit-degrees", type=int, default=None, help="Limitar número de titulaciones por universidad.")
    parser.add_argument("--only-part", type=int, choices=[1, 2, 3, 4], default=None, help="Ejecutar únicamente la parte seleccionada de la Fase 1 (1: RUCT/BOE, 2: Web Crawler, 3: Precios ECTS, 4: Guías Docentes y Temarios).")
    parser.add_argument("--parts", type=int, nargs="+", choices=[1, 2, 3, 4], default=None, help="Seleccionar partes específicas a ejecutar (ej. --parts 1 2 4). Por defecto ejecuta 1, 2 y 3 juntas.")
    parser.add_argument("--force", action="store_true", default=False, help="Forzar re-descarga y re-procesamiento de todas las titulaciones ignorando la comprobación de fecha BOE de la caché.")
    args = parser.parse_args()

    # Determinar partes a ejecutar
    if args.only_part:
        selected_parts = [args.only_part]
    elif args.parts:
        selected_parts = args.parts
    else:
        selected_parts = [1, 2, 3] # Comportamiento normal por defecto: las 3 partes estándar (o 1, 2, 3, 4 con --parts)

    run_crawler(limit_univ=args.limit_univ, limit_degrees=args.limit_degrees, run_parts=selected_parts, force=args.force)
