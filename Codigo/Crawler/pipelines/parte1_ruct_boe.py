import os
import sys
import re
import json
import time
import queue
import signal
import logging
import traceback
import argparse
import multiprocessing as mp
from datetime import datetime
import concurrent.futures
from bs4 import BeautifulSoup

try:
    mp.set_start_method('spawn', force=True)
except RuntimeError:
    pass

logger = logging.getLogger("fase1_parte1_ruct_boe")

from core.config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    ERRORES_JSON,
    CHECKPOINT_JSON,
    ESTADISTICAS_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    HTTP_TIMEOUT,
    URL_UNIVERSIDADES_LIST,
    URL_ESTUDIOS_UNIV_TEMPLATE,
    URL_DETALLE_ESTUDIO_TEMPLATE,
    URL_VERIFICACION_ESTADO_TEMPLATE,
    CPU_WORKERS_COUNT,
    ASYNC_PREFETCH_WORKERS,
    TASK_QUEUE_MAXSIZE,
    TASK_QUEUE_GET_TIMEOUT,
    WORKER_JOIN_TIMEOUT,
    WORKER_RESULT_COLLECTION_TIMEOUT,
    WORKER_RESULT_QUEUE_TIMEOUT,
    WORKER_STOP_QUEUE_TIMEOUT,
    WORKER_TERMINATE_JOIN_TIMEOUT,
    WORKER_TASK_PUT_TIMEOUT,
    MAX_BOE_CANDIDATES_PER_DEGREE,
    BOE_SEARCH_DISCOVERY_ENABLED,
    BOE_SEARCH_DISCOVERY_MAX_QUERIES,
    BOE_SEARCH_DISCOVERY_MAX_RESULTS,
    BOE_SEARCH_DISCOVERY_MAX_DOCUMENTS,
    BOE_SEARCH_DISCOVERY_DELAY,
    BOE_SUMMARY_DISCOVERY_ENABLED,
    BOE_SUMMARY_DISCOVERY_MAX_DATES,
    BOE_SUMMARY_DISCOVERY_MAX_ITEMS,
    BOE_SUMMARY_DISCOVERY_DELAY,
    FULL_REVALIDATION,
    REDISCOVER_URLS_EVERY_RUN,
    TARGET_UNIVERSITY_CODES,
    MAX_IN_MEMORY_PDF_BYTES,
    ENABLE_RUCT_ASYNC_PREFETCH,
    RUCT_PREFETCH_LOOKAHEAD,
    get_plan_filepath,
    find_plan_filepath
)
from core.downloader import (
    RUCTDownloader,
    RobotsDeniedException,
    SkipUniversityException,
    normalize_url
)
from parsers import (
    parse_universities_xls,
    parse_degrees_xls,
    parse_degree_detail_html,
    parse_boe_pdf,
    is_curriculum_complete,
    get_curriculum_completeness_status,
    merge_chronological_boe_curricula
)
from core.checkpoint import (
    CheckpointManager,
    atomic_json_dump,
    load_json_safe
)
from core.error_logger import ErrorLogger
from core.metrics import MetricsTracker
from utils.degree_persistence import save_degree_payload
from core.progress import ProgressEmitter
from pipelines.common import cleanup_temporary_files, format_ruct_url
from core.cancellation import raise_if_shutdown_requested
from core.crawl_ledger import CrawlLedger
from extractors.boe_discovery import (
    needs_boe_curriculum_search,
    discover_boe_candidates,
    discover_boe_candidates_from_summary,
    rebuild_persisted_boe_candidates,
)


def _university_has_pending_curricula(university_code: str, catalog: dict) -> bool:
    """Indica si el checkpoint de una universidad no debe bloquear su revisión.

    El checkpoint registra que una ejecución terminó, pero no demuestra que
    cada titulación tenga un plan curricular completo y verificado. La función
    consulta únicamente el catálogo y los planes locales ya persistidos; no
    contiene excepciones por institución ni por titulación.
    """
    code = str(university_code or "").zfill(3)
    entry = catalog.get(code) if isinstance(catalog, dict) else None
    degrees = entry.get("titulaciones_vigentes", []) if isinstance(entry, dict) else []
    if not isinstance(degrees, list) or not degrees:
        return True
    for degree in degrees:
        if not isinstance(degree, dict):
            continue
        degree_code = str(degree.get("codigo_estudio") or "").strip()
        if not degree_code:
            continue
        record = load_json_safe(find_plan_filepath(code, degree_code), default={})
        plan = record.get("plan_estudios") if isinstance(record, dict) else None
        verified = str(record.get("estado_fuente") or "").strip().lower() == "verificada" if isinstance(record, dict) else False
        complete = bool(
            isinstance(plan, dict)
            and is_curriculum_complete({
                "nivel_academico": degree.get("nivel_academico", ""),
                "titulo": degree.get("titulo", ""),
                "plan_estudios": plan,
            })
        )
        if not (complete and verified):
            return True
    return False


def _ensure_active_degree_records(universities: list, catalog: dict) -> int:
    """Garantiza un registro identificable para cada titulación vigente.

    La ausencia de BOE o de una fuente curricular no justifica perder la
    identidad RUCT del registro. Se crean o reparan únicamente metadatos; no
    se genera ningún plan ni ninguna asignatura.
    """
    repaired = 0
    for university in universities or []:
        if not isinstance(university, dict):
            continue
        u_code = str(university.get("codigo") or "").zfill(3)
        u_name = str(university.get("nombre") or "").strip()
        univ_data = catalog.get(u_code, {}) if isinstance(catalog, dict) else {}
        active_degrees = (
            univ_data.get("titulaciones_vigentes", [])
            if isinstance(univ_data, dict)
            else []
        )
        for degree in active_degrees:
            if not isinstance(degree, dict):
                continue
            d_code = str(degree.get("codigo_estudio") or "").strip()
            if not re.fullmatch(r"[A-Z0-9_-]{4,32}", d_code):
                continue
            plan_file = find_plan_filepath(u_code, d_code)
            existing = load_json_safe(plan_file, default=None)
            if isinstance(existing, dict) and all(
                str(existing.get(key) or "").strip()
                for key in (
                    "codigo_estudio",
                    "titulo",
                    "nivel_academico",
                    "universidad_codigo",
                    "universidad_nombre",
                )
            ):
                continue

            existing = existing if isinstance(existing, dict) else {}
            current_plan = existing.get("plan_estudios")
            if not isinstance(current_plan, dict):
                current_plan = None
            save_degree_payload(
                plan_file=plan_file,
                d_code=d_code,
                d_title=str(degree.get("titulo") or "").strip(),
                u_code=u_code,
                u_name=u_name,
                nivel_academico=str(degree.get("nivel_academico") or "").strip(),
                boe_url=existing.get("boe_url"),
                boe_fecha=existing.get("boe_fecha"),
                plan_estudios=current_plan,
                all_boe_urls=existing.get("all_boe_urls"),
                origen_fuente=existing.get("origen_fuente"),
                existing_data=existing,
                source_status=existing.get("estado_fuente") or "sin_plan_actual_sin_dato",
                source_checked_at=datetime.now().isoformat(),
            )
            repaired += 1
    return repaired


def pdf_parser_consumer(task_queue: mp.Queue, result_queue: mp.Queue = None, shutdown_event: mp.Event = None):
    """
    CONSUMIDOR MULTIPROCESO CPU:
    Recibe tareas de la cola task_queue con flujos de PDFs en memoria RAM o disco.
    Analiza la estructura (asignaturas, materias, ECTS, idioma), fusiona versiones
    actualizadas de BOEs y guarda la titulación en disco de forma atómica.
    """
    err_logger = ErrorLogger()
    checkpoint = CheckpointManager()

    parsed_count = 0
    updated_degrees_count = 0
    total_parse_time = 0.0

    while not (shutdown_event and shutdown_event.is_set()):
        try:
            task = task_queue.get(timeout=TASK_QUEUE_GET_TIMEOUT)
            if task is None or (isinstance(task, dict) and task.get("type") == "STOP"):
                break
        except queue.Empty:
            continue
        except Exception as q_err:
            err_logger.log_error("pdf_parser_queue", "ALL", "task_queue", "Error al extraer tarea de la cola", str(q_err))
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

            if not re.fullmatch(r"[A-Z0-9_-]{4,32}", str(d_code)):
                continue

            plan_file = find_plan_filepath(u_code, d_code)
            existing_degree_data = {}
            if os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        existing_degree_data = json.load(f)
                    if not isinstance(existing_degree_data, dict):
                        existing_degree_data = {}
                except Exception as e:
                    pass

            if task_type == "DEGREE_NO_BOE":
                plan_doc = None
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
                    existing_data=existing_degree_data,
                    source_status=("sin_resolucion_boe_conservando_anterior" if existing_degree_data.get("plan_estudios") else "sin_resolucion_boe_sin_dato"),
                    source_checked_at=datetime.now().isoformat(),
                )

            elif task_type == "PARSE_DEGREE_PDFS":
                pdf_items = task.get("pdf_items", [])
                combined_resumen_creditos = {}
                combined_elementos = []
                seen_subject_names = set()
                processed_boe_urls = []
                pdf_parse_diagnostics = []
                valid_curriculum_found = False
                parsed_candidates_list = []

                try:
                    for cand_idx, item in enumerate(pdf_items, 1):
                        cand_url = item["cand_url"]
                        cand_date = item["cand_date"]
                        pdf_path = item.get("pdf_path")
                        pdf_bytes = item.get("pdf_bytes")

                        try:
                            t_start = time.perf_counter()
                            pdf_input = pdf_bytes if pdf_bytes else pdf_path
                            if not pdf_input:
                                continue

                            curriculum_data = parse_boe_pdf(pdf_input, target_title=d_title, univ_name=u_name)
                            pdf_parse_diagnostics.append(curriculum_data)
                            t_elapsed = time.perf_counter() - t_start
                            total_parse_time += t_elapsed
                            parsed_count += 1

                            pdf_sha256 = curriculum_data.get("pdf_sha256")
                            # Un hash marcado como no curricular puede ser un falso negativo
                            # histórico: las capacidades del parser pueden haber mejorado desde
                            # la primera lectura. Las titulaciones aún incompletas deben poder
                            # revalidar esos documentos; las completas y verificadas conservan
                            # el cortocircuito para no repetir trabajo innecesario.
                            if (
                                pdf_sha256
                                and checkpoint.is_non_study_plan_hash(pdf_sha256)
                                and not task.get("pending_curriculum_revalidation", False)
                            ):
                                continue

                            total_elems = curriculum_data.get("total_elementos", 0)
                            resumen = curriculum_data.get("resumen_creditos", {})

                            if total_elems == 0 and len(resumen) == 0:
                                # Solo se marca el hash del PDF como no curricular si el documento
                                # carece de cualquier tabla/indicio curricular para toda titulación.
                                if not curriculum_data.get("document_has_any_curriculum", False):
                                    checkpoint.mark_non_study_plan_pdf(cand_url, pdf_sha256)
                                else:
                                    checkpoint.mark_non_study_plan_pdf(cand_url)
                                continue

                            valid_curriculum_found = True
                            processed_boe_urls.append(cand_url)
                            parsed_candidates_list.append({
                                "cand_url": cand_url,
                                "cand_date": cand_date,
                                "elementos_curriculares": list(curriculum_data.get("elementos_curriculares", [])),
                                "resumen_creditos": dict(curriculum_data.get("resumen_creditos", {})),
                            })

                            for key, value in resumen.items():
                                combined_resumen_creditos.setdefault(key, value)

                            new_elements = curriculum_data.get("elementos_curriculares", [])
                            if cand_idx == 1:
                                for elem in new_elements:
                                    raw_name = elem.get("nombre_elemento", "").strip()
                                    norm_name = re.sub(r"\s*\(.*?\)", "", raw_name).strip().lower()
                                    if norm_name and norm_name not in seen_subject_names:
                                        seen_subject_names.add(norm_name)
                                        combined_elementos.append(elem)
                            else:
                                covered_courses = {}
                                for existing in combined_elementos:
                                    course = str(existing.get("curso") or "").strip()
                                    try:
                                        raw_ects = existing.get("creditos_ects")
                                        if raw_ects is None:
                                            raw_ects = existing.get("creditos")
                                        ects = float(str(raw_ects).replace(",", ".")) if raw_ects not in (None, "") else 0.0
                                    except (TypeError, ValueError):
                                        ects = 0.0
                                    covered_courses[course] = covered_courses.get(course, 0.0) + ects

                                for elem in new_elements:
                                    raw_name = elem.get("nombre_elemento", "").strip()
                                    norm_name = re.sub(r"\s*\(.*?\)", "", raw_name).strip().lower()
                                    course = str(elem.get("curso") or "").strip()
                                    if course and covered_courses.get(course, 0.0) >= 55.0:
                                        continue
                                    if not norm_name or norm_name in seen_subject_names:
                                        continue
                                    tokens = set(re.findall(r"\w{4,}", norm_name))
                                    collision = any(
                                        len(tokens & set(re.findall(r"\w{4,}", known))) >= max(2, len(tokens) - 1)
                                        for known in seen_subject_names
                                        if tokens
                                    )
                                    if collision:
                                        continue
                                    seen_subject_names.add(norm_name)
                                    combined_elementos.append(elem)

                            # Parada temprana si el plan ya está 100% completo
                            test_plan = {
                                "resumen_creditos": combined_resumen_creditos,
                                "total_elementos": len(combined_elementos),
                                "elementos_curriculares": combined_elementos
                            }
                            if is_curriculum_complete({"nivel_academico": nivel_academico, "titulo": d_title, "plan_estudios": test_plan}):
                                break
                        except Exception as pdf_err:
                            err_logger.log_error("pdf_parser_worker", u_code, cand_url, f"Error al parsear PDF [{d_code}]", str(pdf_err))
                        finally:
                            if pdf_path and os.path.exists(pdf_path):
                                try:
                                    os.remove(pdf_path)
                                except OSError as cleanup_error:
                                    logger.warning("No se pudo eliminar PDF temporal %s: %s", pdf_path, cleanup_error)
                finally:
                    # Limpieza garantizada de cualquier PDF temporal restante no procesado por parada temprana
                    for rem_item in pdf_items:
                        rem_path = rem_item.get("pdf_path")
                        if rem_path and os.path.exists(rem_path):
                            try:
                                os.remove(rem_path)
                            except OSError as cleanup_error:
                                logger.warning("No se pudo eliminar PDF temporal restante %s: %s", rem_path, cleanup_error)

                final_plan_doc = None
                if valid_curriculum_found:
                    if len(parsed_candidates_list) > 1:
                        merged_chrono = merge_chronological_boe_curricula(parsed_candidates_list)
                        if len(merged_chrono.get("elementos_curriculares", [])) >= len(combined_elementos):
                            combined_elementos = merged_chrono["elementos_curriculares"]
                            combined_resumen_creditos = merged_chrono["resumen_creditos"]
                            for u in merged_chrono["boe_urls_procesados"]:
                                if u not in processed_boe_urls:
                                    processed_boe_urls.append(u)

                    summary_only_markers = (
                        "formacion basica", "formación básica", "obligatorias", "optativas",
                        "practicas externas", "prácticas externas", "trabajo fin de grado",
                        "trabajo fin de master", "trabajo fin de máster", "total creditos",
                        "total créditos", "distribucion de creditos", "distribución de créditos",
                    )
                    detail_elements = []
                    for element in combined_elementos:
                        element_name = str(element.get("nombre_elemento") or "").strip().lower()
                        if element_name and not any(marker in element_name for marker in summary_only_markers):
                            detail_elements.append(element)
                    extraction_diagnostic = {
                        "elementos_extraidos": len(combined_elementos),
                        "elementos_curriculares_detallados": len(detail_elements),
                        "resumen_creditos_presente": bool(combined_resumen_creditos),
                        "documento_con_indicios_curriculares": bool(
                            any(item.get("document_has_any_curriculum") for item in pdf_parse_diagnostics)
                        ),
                    }
                    extraction_diagnostic["detalle_curricular_suficiente"] = bool(
                        detail_elements or not combined_resumen_creditos
                    )
                    final_plan_doc = {
                        "resumen_creditos": combined_resumen_creditos,
                        "total_elementos": len(combined_elementos),
                        "elementos_curriculares": combined_elementos,
                        "boe_urls_procesados": processed_boe_urls,
                        "diagnostico_extraccion": extraction_diagnostic,
                        "requiere_revision_parser": not extraction_diagnostic["detalle_curricular_suficiente"],
                    }
                    completeness = get_curriculum_completeness_status({
                        "nivel_academico": nivel_academico,
                        "titulo": d_title,
                        "plan_estudios": final_plan_doc,
                    })
                    final_plan_doc["plan_completo"] = completeness["is_complete"]
                    final_plan_doc["ects_totales_detectados"] = completeness["total_ects_obtained"]
                    final_plan_doc["ects_exigidos"] = completeness["required_ects"]
                save_degree_payload(
                    plan_file=plan_file,
                    d_code=d_code,
                    d_title=d_title,
                    u_code=u_code,
                    u_name=u_name,
                    nivel_academico=nivel_academico,
                    boe_url=latest_boe_url if valid_curriculum_found else None,
                    boe_fecha=latest_boe_fecha if valid_curriculum_found else None,
                    plan_estudios=final_plan_doc,
                    all_boe_urls=task.get("all_boe_urls", processed_boe_urls),
                    origen_fuente="boe" if valid_curriculum_found else None,
                    checkpoint_mgr=checkpoint,
                    existing_data=existing_degree_data,
                    source_status=("verificada" if valid_curriculum_found else ("fuente_no_disponible_conservando_anterior" if existing_degree_data.get("plan_estudios") else "fuente_no_disponible_sin_dato")),
                    source_checked_at=datetime.now().isoformat(),
                )
                if valid_curriculum_found:
                    updated_degrees_count += 1

        except Exception as task_err:
            err_logger.log_error("pdf_parser_task", task.get("u_code", "ALL"), task.get("d_code", "ALL"), "Error al procesar tarea en consumidor", str(task_err))

    if result_queue is not None:
        try:
            result_queue.put({
                "parsed_count": parsed_count,
                "updated_degrees_count": updated_degrees_count,
                "total_parse_time": total_parse_time
            }, timeout=WORKER_RESULT_QUEUE_TIMEOUT)
        except Exception as res_err:
            err_logger.log_error("pdf_parser_result_queue", "ALL", "result_queue", "Error al enviar métricas finales", str(res_err))
    # Cada worker mantiene una conexión SQLite propia. Cerrarla antes de
    # salir libera el descriptor y evita que un proceso terminado deje
    # bloqueados los ficheros WAL/SHM para la siguiente campaña.
    checkpoint.close()


def run_phase1_part1(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
    degree_title_filter: str | None = None,
    target_universities: list[str] | set[str] | None = None,
) -> dict:
    """Descarga el catálogo RUCT y resuelve los planes publicados en BOE."""
    full_revalidation = bool(FULL_REVALIDATION or force)
    rediscover_urls = bool(REDISCOVER_URLS_EVERY_RUN or full_revalidation)
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 1: CATÁLOGOS RUCT Y RESOLUCIONES BOE")
    print("======================================================================")

    error_logger = ErrorLogger()
    checkpoint = CheckpointManager()
    metrics = metrics_tracker or MetricsTracker()
    progress = progress_emitter or ProgressEmitter()
    progress.update_part(1, "Catálogos RUCT y resoluciones BOE")

    os.makedirs(PLANES_DIR, exist_ok=True)
    os.makedirs(TEMP_PDF_DIR, exist_ok=True)
    cleanup_temporary_files(TEMP_PDF_DIR, max_age_seconds=0)

    worker_count = CPU_WORKERS_COUNT if max_workers is None else max_workers
    worker_count = max(1, min(int(worker_count), os.cpu_count() or 1))
    task_queue = mp.Queue(maxsize=TASK_QUEUE_MAXSIZE)
    result_queue = mp.Queue()
    shutdown_event = mp.Event()
    consumer_pool = []
    for index in range(worker_count):
        process = mp.Process(
            target=pdf_parser_consumer,
            args=(task_queue, result_queue, shutdown_event),
            name=f"PDFParserWorker-{index + 1}",
            daemon=True,
        )
        process.start()
        consumer_pool.append(process)

    ledger = CrawlLedger()
    downloader = RUCTDownloader(metrics_tracker=metrics, ledger=ledger, phase="fase1_parte1")
    total_enqueued = 0
    total_degrees_discovered = 0
    processed_universities = 0
    processed_university_codes = set()
    controlled_incidents = 0
    phase_error = None
    worker_incomplete = False
    worker_result_count = 0
    prefetch_executor = None
    catalog = {}
    universities = []
    metadata_records_repaired = 0
    boe_search_queries = 0
    boe_search_documents = 0
    boe_search_candidates = 0
    boe_search_errors = 0
    boe_summary_dates = 0
    boe_summary_inspected = 0
    boe_summary_candidates = 0
    boe_summary_errors = 0
    persisted_boe_degrees = 0
    persisted_boe_candidates = 0

    try:
        print(" [Paso 1/3] Obteniendo lista oficial de universidades desde RUCT...")
        temp_univ_xls = os.path.join(TEMP_PDF_DIR, "universidades_temp.xls")
        try:
            try:
                with open(temp_univ_xls, "wb") as file_obj:
                    file_obj.write(downloader.fetch_content(URL_UNIVERSIDADES_LIST))
                universities = parse_universities_xls(temp_univ_xls)
            except Exception as ruct_err:
                logger.warning(
                    "No se pudo descargar la lista de universidades desde RUCT (%s). "
                    "Recurriendo al catálogo maestro local si está disponible.",
                    ruct_err,
                )
                universities = load_json_safe(UNIVERSIDADES_JSON, default=[])
                if not universities:
                    raise RuntimeError(
                        f"Fallo al descargar universidades de RUCT y no existe catálogo maestro en {UNIVERSIDADES_JSON}: {ruct_err}"
                    ) from ruct_err
                print(f" -> [RESPALDO] Utilizando catálogo maestro local de universidades ({len(universities)} instituciones).")
        finally:
            if os.path.exists(temp_univ_xls):
                try:
                    os.remove(temp_univ_xls)
                except OSError:
                    pass

        # Conservar URLs rescatadas por ejecuciones anteriores.
        old_universities = load_json_safe(UNIVERSIDADES_JSON, default=[])
        if isinstance(old_universities, list):
            old_map = {item.get("codigo"): item for item in old_universities if isinstance(item, dict)}
            for university in universities:
                previous = old_map.get(university.get("codigo"))
                if previous and previous.get("web_corregida_por_wikidata"):
                    university["web"] = previous.get("web", university.get("web", ""))
                    university["web_corregida_por_wikidata"] = True

        atomic_json_dump(universities, UNIVERSIDADES_JSON)

        effective_targets = target_universities or TARGET_UNIVERSITY_CODES
        if effective_targets:
            target_set = {str(c).zfill(3) for c in effective_targets}
            universities = [u for u in universities if str(u.get("codigo", "")).zfill(3) in target_set]
        if limit_universities is not None:
            universities = universities[:max(0, limit_universities)]
        print(f" -> {len(universities)} universidades seleccionadas.")

        catalog = load_json_safe(TITULACIONES_JSON, default={})
        if not isinstance(catalog, dict):
            catalog = {}

        if ENABLE_RUCT_ASYNC_PREFETCH and ASYNC_PREFETCH_WORKERS > 0:
            prefetch_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, int(ASYNC_PREFETCH_WORKERS)),
                thread_name_prefix="RUCTPrefetch"
            )

        print(" [Paso 2/3] Rastreo de titulaciones y resoluciones BOE por universidad...")
        for university_index, university in enumerate(universities, 1):
            raise_if_shutdown_requested()
            university_code = str(university.get("codigo", "")).zfill(3)
            university_name = university.get("nombre", "")
            university_type = university.get("tipo", "Desconocido")
            if (
                not full_revalidation
                and checkpoint.is_university_processed(university_code)
                and not _university_has_pending_curricula(university_code, catalog)
            ):
                logger.info(
                    "[checkpoint] Universidad %s ya procesada y sin planes pendientes; se omite por política no revalidante.",
                    university_code,
                )
                continue
            if not full_revalidation and checkpoint.is_university_processed(university_code):
                logger.info(
                    "[checkpoint] Universidad %s tiene planes ausentes o incompletos; se reabre su revisión oficial.",
                    university_code,
                )
            completed_cleanly = True
            metrics.inc_universidades()
            downloader.reset_university_context(university_code)
            progress.update_university(
                university_index,
                len(universities),
                university_code,
                university_name,
                university_type,
            )
            print(
                f"\n [{university_index}/{len(universities)}] "
                f"Universidad [{university_code}] ({university_type}): {university_name}"
            )

            degrees_url = format_ruct_url(URL_ESTUDIOS_UNIV_TEMPLATE, university_code)
            temp_degrees_xls = os.path.join(TEMP_PDF_DIR, f"degrees_{university_code}.xls")
            try:
                try:
                    with open(temp_degrees_xls, "wb") as file_obj:
                        file_obj.write(downloader.fetch_content(degrees_url))
                    active_degrees = parse_degrees_xls(temp_degrees_xls)
                except Exception as fetch_err:
                    logger.warning(
                        "No se pudo descargar el catálogo XLS de la universidad %s (%s). "
                        "Recurriendo al catálogo previo existente si está disponible.",
                        university_code,
                        fetch_err,
                    )
                    cached_data = catalog.get(university_code, {})
                    active_degrees = cached_data.get("titulaciones_vigentes", [])
                    if not active_degrees:
                        raise
                    print(f" -> [RESPALDO] Recuperadas {len(active_degrees)} titulaciones previas para [{university_code}].")
                finally:
                    if os.path.exists(temp_degrees_xls):
                        try:
                            os.remove(temp_degrees_xls)
                        except OSError:
                            pass

                catalog[university_code] = {
                    "universidad_codigo": university_code,
                    "universidad_nombre": university_name,
                    "tipo": university_type,
                    "total_titulaciones_vigentes": len(active_degrees),
                    "titulaciones_vigentes": active_degrees,
                }
                total_degrees_discovered += len(active_degrees)
                atomic_json_dump(catalog, TITULACIONES_JSON)

                degrees_to_process = list(reversed(active_degrees))
                if degree_title_filter:
                    from pipelines.common import matches_degree_title
                    degrees_to_process = [d for d in degrees_to_process if matches_degree_title(d.get("titulo"), degree_title_filter)]
                if limit_degrees is not None:
                    degrees_to_process = degrees_to_process[:max(0, limit_degrees)]

                prefetch_futures = {}

                def _fetch_degree_detail_worker(d_cod):
                    d_url = format_ruct_url(URL_DETALLE_ESTUDIO_TEMPLATE, d_cod, degree=True)
                    raw_html = downloader.fetch_text(d_url)
                    return parse_degree_detail_html(raw_html)

                try:
                    for degree_index, degree in enumerate(degrees_to_process, 1):
                        raise_if_shutdown_requested()
                        degree_code = str(degree.get("codigo_estudio", "")).strip()
                        degree_title = degree.get("titulo", "")
                        degree_level = degree.get("nivel_academico", "")
                        if not degree_code:
                            continue
                        metrics.inc_titulaciones()
                        downloader.set_degree_context(degree_code)
                        progress.update_degree(
                            degree_index,
                            len(degrees_to_process),
                            degree_code,
                            degree_title,
                            "Consultando RUCT",
                        )

                        if not full_revalidation and checkpoint.is_extinct_degree(degree_code):
                            continue

                        # Alimentar la ventana de precarga para las siguientes titulaciones
                        if prefetch_executor is not None:
                            for future_idx in range(degree_index, min(degree_index + RUCT_PREFETCH_LOOKAHEAD, len(degrees_to_process))):
                                fut_deg = degrees_to_process[future_idx]
                                fut_code = str(fut_deg.get("codigo_estudio", "")).strip()
                                if fut_code and fut_code not in prefetch_futures and (full_revalidation or not checkpoint.is_extinct_degree(fut_code)):
                                    prefetch_futures[fut_code] = prefetch_executor.submit(_fetch_degree_detail_worker, fut_code)

                        detail_url = format_ruct_url(URL_DETALLE_ESTUDIO_TEMPLATE, degree_code, degree=True)
                        try:
                            if degree_code in prefetch_futures:
                                try:
                                    detail = prefetch_futures.pop(degree_code).result(timeout=HTTP_TIMEOUT + 5)
                                except Exception:
                                    detail = _fetch_degree_detail_worker(degree_code)
                            else:
                                detail = _fetch_degree_detail_worker(degree_code)

                            is_extinct = detail.get("is_extinct", False)
                            status_text = detail.get("status_text", "")
                            lifecycle = detail.get("lifecycle")
                            if lifecycle:
                                degree["situacion_matriculacion"] = lifecycle
                            if status_text:
                                degree["estado_ruct_detalle"] = status_text
                            candidates = detail.get("all_boe_candidates", [])

                            if not candidates and not is_extinct:
                                status_url = format_ruct_url(URL_VERIFICACION_ESTADO_TEMPLATE, degree_code, degree=True)
                                try:
                                    status_text_full = BeautifulSoup(
                                        downloader.fetch_text(status_url), "html.parser"
                                    ).get_text().upper()
                                    if any(marker in status_text_full for marker in ("TITULACIÓN EXTINGUIDA", "TITULACION EXTINGUIDA", "TITULACIÓN EXTINTA", "TITULACION EXTINTA")):
                                        is_extinct = True
                                        status_text = "TITULACIÓN EXTINGUIDA"
                                except Exception as status_error:
                                    logger.debug("No se pudo consultar el estado RUCT de %s: %s", degree_code, status_error)

                            if is_extinct:
                                checkpoint.mark_extinct_degree(degree_code, status_text or "Extinguida")
                                continue

                            plan_file = find_plan_filepath(university_code, degree_code)
                            existing_record = load_json_safe(plan_file, default={})
                            if not isinstance(existing_record, dict):
                                existing_record = {}

                            # Una ficha viva puede dejar de mostrar referencias
                            # históricas que el proyecto ya había recolectado.
                            # Se reinyectan como candidatos genéricos y vuelven
                            # a pasar por el mismo circuito de descarga, identidad
                            # y compuerta curricular; nunca se publican por el
                            # mero hecho de estar persistidas.
                            persisted_candidates = rebuild_persisted_boe_candidates(
                                existing_record.get("all_boe_urls"),
                                existing_record.get("boe_fecha"),
                                limit=MAX_BOE_CANDIDATES_PER_DEGREE,
                            )
                            if persisted_candidates:
                                # Conservamos la preferencia por las
                                # referencias vivas, pero no perdemos la
                                # evidencia histórica cuando la ficha actual
                                # solo expone documentos administrativos.
                                merged_candidates = list(candidates or [])
                                known_urls = {
                                    str(item.get("url") or "").strip()
                                    for item in merged_candidates
                                    if isinstance(item, dict)
                                }
                                for persisted in persisted_candidates:
                                    if persisted["url"] not in known_urls:
                                        merged_candidates.append(persisted)
                                candidates = merged_candidates
                                persisted_boe_degrees += 1
                                persisted_boe_candidates += len(persisted_candidates)

                            # La ficha RUCT es la fuente preferente. Si solo
                            # conserva una fecha, el sumario oficial JSON es
                            # más preciso que un buscador externo; después se
                            # mantiene el buscador HTML como último fallback.
                            boe_summary_result = None
                            summary_dates = [
                                detail.get("boe_date"),
                                existing_record.get("boe_fecha"),
                            ] + [
                                item.get("boe_date")
                                for item in persisted_candidates
                                if isinstance(item, dict)
                            ]
                            # Una referencia histórica puede ser válida como
                            # evidencia de fecha aunque el PDF persistido sea
                            # administrativo, esté roto o no contenga el
                            # currículo completo. En expedientes sin plan se
                            # consulta el sumario de esa fecha y se fusionan
                            # sus candidatos con los enlaces existentes.
                            summary_probe_allowed = bool(
                                BOE_SUMMARY_DISCOVERY_ENABLED
                                and (
                                    not candidates
                                    or (
                                        persisted_candidates
                                        and not isinstance(existing_record.get("plan_estudios"), dict)
                                    )
                                )
                            )
                            if summary_probe_allowed:
                                boe_summary_result = discover_boe_candidates_from_summary(
                                    university_name,
                                    degree_title,
                                    degree_level,
                                    summary_dates,
                                    downloader.fetch_text,
                                    date_limit=BOE_SUMMARY_DISCOVERY_MAX_DATES,
                                    item_limit=BOE_SUMMARY_DISCOVERY_MAX_ITEMS,
                                    delay=BOE_SUMMARY_DISCOVERY_DELAY,
                                )
                                boe_summary_dates += len(boe_summary_result.get("dates", []))
                                boe_summary_inspected += int(
                                    boe_summary_result.get("summaries_inspected", 0) or 0
                                )
                                boe_summary_candidates += len(boe_summary_result.get("records", []))
                                boe_summary_errors += len(boe_summary_result.get("errors", []))
                                summary_candidates = boe_summary_result.get("records", [])
                                if summary_candidates:
                                    candidates = summary_candidates + [
                                        item for item in candidates
                                        if str(item.get("url") or "").strip() not in {
                                            str(candidate.get("url") or "").strip()
                                            for candidate in summary_candidates
                                            if isinstance(candidate, dict)
                                        }
                                    ]

                            # Cuando no conserva ninguna resolución, se
                            # consulta el buscador oficial del BOE con un
                            # presupuesto fijo. Los resultados no se aceptan
                            # automáticamente: discover_boe_candidates exige
                            # evidencia de título e institución y el PDF pasa
                            # por el mismo parser, identidad y compuerta.
                            # Los resultados no se aceptan automáticamente:
                            # discover_boe_candidates exige evidencia de título
                            # e institución y el PDF pasa por el mismo parser,
                            # identidad y compuerta curricular que un enlace RUCT.
                            boe_search_result = None
                            if BOE_SEARCH_DISCOVERY_ENABLED and needs_boe_curriculum_search(candidates, existing_record):
                                boe_search_result = discover_boe_candidates(
                                    university_name,
                                    degree_title,
                                    degree_level,
                                    downloader.fetch_text,
                                    query_limit=BOE_SEARCH_DISCOVERY_MAX_QUERIES,
                                    result_limit=BOE_SEARCH_DISCOVERY_MAX_RESULTS,
                                    document_limit=BOE_SEARCH_DISCOVERY_MAX_DOCUMENTS,
                                    delay=BOE_SEARCH_DISCOVERY_DELAY,
                                )
                                boe_search_queries += len(boe_search_result.get("queries", []))
                                boe_search_documents += int(boe_search_result.get("documents_inspected", 0) or 0)
                                boe_search_candidates += len(boe_search_result.get("records", []))
                                boe_search_errors += len(boe_search_result.get("errors", []))
                                # Dar prioridad a resoluciones curriculares
                                # localizadas por título. Una referencia RUCT
                                # administrativa previa no debe consumir todas
                                # las plazas de descarga ni impedir el rescate.
                                search_candidates = boe_search_result.get("records", [])
                                search_urls = {item.get("url") for item in search_candidates}
                                candidates = search_candidates + [
                                    item for item in candidates if item.get("url") not in search_urls
                                ]

                            latest_url = detail.get("latest_boe_url") or (
                                candidates[0].get("url") if candidates else None
                            )
                            latest_date = detail.get("boe_date") or (
                                candidates[0].get("boe_date") if candidates else None
                            )
                            existing_plan = (
                                existing_record.get("plan_estudios")
                                if isinstance(existing_record, dict)
                                else None
                            )
                            existing_complete = bool(
                                isinstance(existing_plan, dict)
                                and is_curriculum_complete({
                                    "nivel_academico": degree_level,
                                    "titulo": degree_title,
                                    "plan_estudios": existing_plan,
                                })
                            )
                            existing_verified = str(
                                existing_record.get("estado_fuente") or ""
                            ).strip().lower() == "verificada"
                            pending_curriculum_revalidation = not (
                                existing_complete and existing_verified
                            )
                            if (
                                not full_revalidation
                                and os.path.exists(plan_file)
                                and checkpoint.is_degree_up_to_date(degree_code, latest_url, latest_date)
                            ):
                                # El checkpoint solo debe evitar trabajo si
                                # ya existe un plan completo y verificado. En
                                # caso contrario, una marca de "al día" no
                                # puede congelar una titulación sin datos o
                                # con una extracción parcial frente a nuevas
                                # capacidades del parser.
                                if existing_complete and existing_verified:
                                    metrics.inc_titulaciones_al_dia()
                                    continue
                                logger.info(
                                    "[REPROCESO BOE] El checkpoint coincide, pero el plan almacenado no está completo y verificado; se vuelve a evaluar la evidencia oficial."
                                )

                            if not candidates:
                                payload = {
                                    "type": "DEGREE_NO_BOE",
                                    "d_code": degree_code,
                                    "d_title": degree_title,
                                    "u_code": university_code,
                                    "u_name": university_name,
                                    "nivel_academico": degree_level,
                                }
                                while True:
                                    try:
                                        task_queue.put(payload, timeout=WORKER_TASK_PUT_TIMEOUT)
                                        total_enqueued += 1
                                        break
                                    except queue.Full:
                                        if shutdown_event.is_set():
                                            raise
                                        logger.warning("Cola llena, reintentando encolar titulación %s...", degree_code)
                                continue

                            # Evaluamos los candidatos ordenados por prioridad y fecha decreciente
                            # para permitir que el consumidor inspeccione la resolución con plan completo
                            # si la modificación más reciente carece de tablas curriculares.
                            candidate_budget = MAX_BOE_CANDIDATES_PER_DEGREE + len(persisted_candidates)
                            target_candidates = sorted(
                                [item for item in candidates if item.get("priority", 0) > 0],
                                key=lambda c: (
                                    c.get("priority", 0),
                                    c.get("score", 0),
                                    c.get("date") or datetime(1970, 1, 1),
                                ),
                                reverse=True
                            )[:candidate_budget]
                            pdf_items = []
                            for candidate_index, candidate in enumerate(target_candidates, 1):
                                candidate_url = candidate.get("url", "")
                                if not candidate_url:
                                    continue
                                if (
                                    not rediscover_urls
                                    and not pending_curriculum_revalidation
                                    and (
                                        checkpoint.is_non_study_plan_pdf(candidate_url)
                                        or checkpoint.is_unreachable_url(candidate_url)
                                    )
                                ):
                                    continue
                                temp_pdf_path = None
                                try:
                                    content = downloader.fetch_content(candidate_url)
                                    if content and len(content) > 100:
                                        if len(content) <= MAX_IN_MEMORY_PDF_BYTES:
                                            # Estrategia 1: Transferencia directa en memoria RAM (para PDFs <= 5 MB)
                                            pdf_items.append({
                                                "cand_url": candidate_url,
                                                "cand_date": candidate.get("boe_date"),
                                                "pdf_bytes": content,
                                            })
                                        else:
                                            # Estrategia 2: Spill-to-Disk temporal para PDFs > 5 MB
                                            temp_pdf_path = os.path.join(TEMP_PDF_DIR, f"boe_{os.getpid()}_{university_code}_{degree_code}_{candidate_index}.pdf")
                                            try:
                                                with open(temp_pdf_path, "wb") as f_pdf:
                                                    f_pdf.write(content)
                                                pdf_items.append({
                                                    "cand_url": candidate_url,
                                                    "cand_date": candidate.get("boe_date"),
                                                    "pdf_path": temp_pdf_path,
                                                })
                                            except OSError as os_err:
                                                if os.path.exists(temp_pdf_path):
                                                    try:
                                                        os.remove(temp_pdf_path)
                                                    except OSError:
                                                        pass
                                                error_logger.log_error("pdf_write", university_code, candidate_url, "Error al escribir PDF temporal al disco", str(os_err))
                                                continue
                                except SkipUniversityException:
                                    raise
                                except RobotsDeniedException as download_error:
                                    controlled_incidents += 1
                                    checkpoint.record_pdf_download_failure(
                                        candidate_url, degree_code, str(download_error)
                                    )
                                    error_logger.log_error(
                                        "pdf_download",
                                        university_code,
                                        candidate_url,
                                        f"Incidencia controlada: robots.txt deniega el PDF de [{degree_code}]",
                                        str(download_error),
                                        classification="incidencia_controlada",
                                    )
                                    metrics.inc_incidencias_controladas()
                                    if temp_pdf_path and os.path.exists(temp_pdf_path):
                                        try:
                                            os.remove(temp_pdf_path)
                                        except OSError:
                                            pass
                                except Exception as download_error:
                                    checkpoint.record_pdf_download_failure(
                                        candidate_url, degree_code, str(download_error)
                                    )
                                    error_logger.log_error(
                                        "pdf_download",
                                        university_code,
                                        candidate_url,
                                        f"Error al descargar PDF de [{degree_code}]",
                                        str(download_error),
                                    )
                                    metrics.inc_errores()
                                    if temp_pdf_path and os.path.exists(temp_pdf_path):
                                        try:
                                            os.remove(temp_pdf_path)
                                        except OSError:
                                            pass

                            if pdf_items:
                                payload = {
                                    "type": "PARSE_DEGREE_PDFS",
                                    "d_code": degree_code,
                                    "d_title": degree_title,
                                    "u_code": university_code,
                                    "u_name": university_name,
                                    "nivel_academico": degree_level,
                                    "latest_boe_url": latest_url,
                                    "latest_boe_fecha": latest_date,
                                    "all_boe_urls": [item.get("url") for item in candidates if item.get("url")],
                                    "pdf_items": pdf_items,
                                    "pending_curriculum_revalidation": pending_curriculum_revalidation,
                                }
                                while True:
                                    try:
                                        task_queue.put(payload, timeout=WORKER_TASK_PUT_TIMEOUT)
                                        total_enqueued += 1
                                        break
                                    except queue.Full:
                                        if shutdown_event.is_set():
                                            raise
                                        logger.warning("Cola llena, reintentando encolar titulación %s...", degree_code)
                        except queue.Full as queue_error:
                            for itm in pdf_items:
                                p_clean = itm.get("pdf_path")
                                if p_clean and os.path.exists(p_clean):
                                    try:
                                        os.remove(p_clean)
                                    except OSError as cleanup_error:
                                        logger.warning("No se pudo limpiar PDF tras saturación de cola %s: %s", p_clean, cleanup_error)
                            completed_cleanly = False
                            worker_incomplete = True
                            error_logger.log_error("pdf_parser_queue", university_code, detail_url, "Cola de workers saturada; universidad incompleta", str(queue_error))
                            metrics.inc_errores()
                            break
                        except SkipUniversityException as connection_error:
                            for itm in pdf_items:
                                p_clean = itm.get("pdf_path")
                                if p_clean and os.path.exists(p_clean):
                                    try:
                                        os.remove(p_clean)
                                    except OSError as cleanup_error:
                                        logger.warning("No se pudo limpiar PDF tras circuito abierto %s: %s", p_clean, cleanup_error)
                            completed_cleanly = False
                            error_logger.log_error(
                                "university_circuit_breaker",
                                university_code,
                                detail_url,
                                "Problemas de conexión continuados",
                                str(connection_error),
                            )
                            metrics.inc_errores()
                            break
                        except Exception as degree_error:
                            for itm in pdf_items:
                                p_clean = itm.get("pdf_path")
                                if p_clean and os.path.exists(p_clean):
                                    try:
                                        os.remove(p_clean)
                                    except OSError as cleanup_error:
                                        logger.warning("No se pudo limpiar PDF tras error de titulación %s: %s", p_clean, cleanup_error)
                            error_logger.log_error(
                                "degree_processing",
                                degree_code,
                                detail_url,
                                f"Error al procesar titulación [{degree_code}]",
                                traceback.format_exc(),
                            )
                            metrics.inc_errores()
                            continue
                finally:
                    prefetch_futures.clear()

                if completed_cleanly:
                    # Persiste la clasificación de matrícula obtenida de la
                    # ficha RUCT, incluidos los títulos vigentes en extinción.
                    atomic_json_dump(catalog, TITULACIONES_JSON)
                    checkpoint.mark_university_processed(university_code)
                    processed_universities += 1
                    processed_university_codes.add(university_code)
            except SkipUniversityException as connection_error:
                error_logger.log_error(
                    "university_catalog",
                    university_code,
                    degrees_url,
                    "Problemas de conexión continuados",
                    str(connection_error),
                )
                metrics.inc_errores()
            except Exception as university_error:
                error_logger.log_error(
                    "university_catalog",
                    university_code,
                    degrees_url,
                    "Error al procesar la lista de titulaciones",
                    str(university_error),
                )
                metrics.inc_errores()

        atomic_json_dump(catalog, TITULACIONES_JSON)
    except Exception as error:
        phase_error = error
        metrics.inc_errores()
        error_logger.log_error(
            "phase1_part1",
            "ALL",
            URL_UNIVERSIDADES_LIST,
            "Error crítico en RUCT/BOE",
            traceback.format_exc(),
        )
    finally:
        if prefetch_executor is not None:
            prefetch_executor.shutdown(wait=False, cancel_futures=True)
        for _ in consumer_pool:
            try:
                task_queue.put({"type": "STOP"}, timeout=WORKER_STOP_QUEUE_TIMEOUT)
            except Exception:
                shutdown_event.set()

        result_deadline = time.monotonic() + WORKER_RESULT_COLLECTION_TIMEOUT
        for _ in consumer_pool:
            try:
                remaining = result_deadline - time.monotonic()
                if remaining <= 0:
                    break
                worker_result = result_queue.get(timeout=max(remaining, 0.1))
                worker_result_count += 1
                metrics.merge_worker_stats(
                    worker_result.get("parsed_count", 0),
                    worker_result.get("updated_degrees_count", 0),
                    worker_result.get("total_parse_time", 0.0),
                )
            except Exception as worker_error:
                logger.warning("No se pudo recoger el resultado de un worker PDF: %s", worker_error, exc_info=True)

        for process in consumer_pool:
            process.join(timeout=WORKER_JOIN_TIMEOUT)
            if process.is_alive():
                process.terminate()
                process.join(timeout=WORKER_TERMINATE_JOIN_TIMEOUT)

        if not phase_error and (worker_result_count < len(consumer_pool) or any(p.exitcode not in (0, None) for p in consumer_pool)):
            worker_incomplete = True

        if not phase_error and isinstance(catalog, dict):
            metadata_records_repaired = _ensure_active_degree_records(universities, catalog)
            if metadata_records_repaired:
                logger.info(
                    "Se repararon/crearon %s registros de identidad de titulaciones activas.",
                    metadata_records_repaired,
                )

        ledger.reconcile_processing(
            phase_prefix="fase1_parte1",
            reason="intento sin respuesta al cerrar la Parte 1",
        )
        downloader.close()
        ledger.close()
        checkpoint.close()
        metrics.save()
        progress.update_metrics(
            univ_done=processed_universities,
            deg_inspected=metrics.titulaciones_inspeccionadas,
            deg_updated=metrics.titulaciones_descargadas_actualizadas,
            pdfs_parsed=metrics.pdfs_parseados,
            errors=metrics.errores_detectados,
            controlled_incidents=metrics.incidencias_controladas,
        )

    status = "failed" if phase_error else ("partial" if worker_incomplete else "completed")
    print("\n" + "=" * 70)
    print(f"      FASE 1 - PARTE 1 FINALIZADA: {status.upper()}")
    print("======================================================================")
    return {
        "status": status,
        "total_enqueued": total_enqueued,
        "degrees_discovered": total_degrees_discovered,
        "universities_processed": processed_universities,
        "university_codes_processed": sorted(processed_university_codes),
        "incidencias_controladas": controlled_incidents,
        "metadata_records_repaired": metadata_records_repaired,
        "boe_search_discovery": {
            "enabled": bool(BOE_SEARCH_DISCOVERY_ENABLED),
            "queries": boe_search_queries,
            "documents_inspected": boe_search_documents,
            "candidates": boe_search_candidates,
            "errors": boe_search_errors,
        },
        "boe_summary_discovery": {
            "enabled": bool(BOE_SUMMARY_DISCOVERY_ENABLED),
            "dates": boe_summary_dates,
            "summaries_inspected": boe_summary_inspected,
            "candidates": boe_summary_candidates,
            "errors": boe_summary_errors,
        },
        "persisted_boe_revalidation": {
            "degrees": persisted_boe_degrees,
            "candidates": persisted_boe_candidates,
        },
        "persistence": {
            "checkpoint_sqlite": "degraded" if getattr(checkpoint, "_sqlite_disabled", False) else "ok",
            "crawl_ledger_sqlite": "degraded" if getattr(ledger, "_disabled", False) else "ok",
        },
        "error": str(phase_error) if phase_error else None,
    }


if __name__ == "__main__":
    run_phase1_part1()
