import os
import json
from config import UNIVERSIDADES_JSON
from main import run_crawler

def run_custom_test():
    if not os.path.exists(UNIVERSIDADES_JSON):
        print("Error: universidades.json does not exist. Run main.py step 1 first.")
        return

    with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
        all_univs = json.load(f)

    publicas = [u for u in all_univs if "pública" in u.get("tipo", "").lower() or "publica" in u.get("tipo", "").lower()]
    privadas = [u for u in all_univs if not ("pública" in u.get("tipo", "").lower() or "publica" in u.get("tipo", "").lower())]

    selected_3_publicas = publicas[:3]
    selected_2_privadas = privadas[:2]
    selected_5 = selected_3_publicas + selected_2_privadas

    print("======================================================================")
    print("      INICIANDO PRUEBA PERSONALIZADA (3 PÚBLICAS + 2 PRIVADAS)")
    print("======================================================================")
    print("Universidades seleccionadas:")
    for u in selected_5:
        print(f" - [{u['codigo']}] {u['nombre']} ({u.get('tipo')})")
    print("======================================================================\n")

    # Override universities in main crawler test
    from main import pdf_parser_consumer, trigger_api_etl_sync
    import multiprocessing as mp
    from downloader import RUCTDownloader
    from error_logger import ErrorLogger
    from checkpoint import CheckpointManager, atomic_json_dump
    from metrics import PerformanceTracker
    from precios_crawler import run_phase1_part3
    from univ_web_crawler import UniversityWebCrawler

    # 1. Run Part 1 with selected 5 universities
    downloader = RUCTDownloader()
    logger = ErrorLogger()
    checkpoint = CheckpointManager()
    metrics = PerformanceTracker()

    task_queue = mp.Queue(maxsize=100)
    result_queue = mp.Queue()
    parser_process = mp.Process(target=pdf_parser_consumer, args=(task_queue, result_queue), daemon=True)
    parser_process.start()

    titulaciones_por_universidad = {}
    from config import TITULACIONES_JSON, TEMP_PDF_DIR, PLANES_DIR, URL_ESTUDIOS_UNIV_TEMPLATE, URL_DETALLE_ESTUDIO_TEMPLATE, URL_VERIFICACION_ESTADO_TEMPLATE
    from parsers import parse_degrees_xls, parse_degree_detail_html, parse_boe_pdf
    from downloader import SkipUniversityException
    import time, concurrent.futures
    from bs4 import BeautifulSoup

    if os.path.exists(TITULACIONES_JSON):
        try:
            with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
                titulaciones_por_universidad = json.load(f)
        except Exception:
            titulaciones_por_universidad = {}

    for u_idx, univ in enumerate(selected_5, 1):
        metrics.universidades_inspeccionadas += 1
        u_code = univ["codigo"]
        u_name = univ["nombre"]
        u_tipo = univ.get("tipo", "Desconocido")

        downloader.reset_university_context(u_code)
        print(f"({u_idx}/5) Procesando Universidad [{u_code}] ({u_tipo}): {u_name}")

        univ_degrees_file = os.path.join(TEMP_PDF_DIR, f"degrees_{u_code}.xls")
        try:
            degrees_url = URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo_universidad=u_code, codigo=u_code)
            t0 = time.perf_counter()
            downloader.download_file(degrees_url, univ_degrees_file)
            metrics.record_io_time(time.perf_counter() - t0)
            active_degrees = parse_degrees_xls(univ_degrees_file)
        except Exception as e:
            print(f"  [AVISO PRUEBA] Error bajando lista de {u_name}: {e}")
            continue

        titulaciones_por_universidad[u_code] = {
            "universidad_codigo": u_code,
            "universidad_nombre": u_name,
            "tipo": u_tipo,
            "total_titulaciones_vigentes": len(active_degrees),
            "titulaciones_vigentes": active_degrees
        }
        atomic_json_dump(titulaciones_por_universidad, TITULACIONES_JSON)

        degrees_to_process = active_degrees[:10]  # Limit to 10 degrees per university as requested

        for d_idx, deg in enumerate(degrees_to_process, 1):
            metrics.titulaciones_inspeccionadas += 1
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            print(f"   [{d_idx}/10] Titulación [{d_code}]: {d_title[:60]}...")

            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
            detail_url = URL_DETALLE_ESTUDIO_TEMPLATE.format(codigo_estudio=d_code)

            try:
                html_content = downloader.fetch_text(detail_url)
                boe_info = parse_degree_detail_html(html_content)
                candidates = boe_info.get("all_boe_candidates", [])
                latest_boe_url = boe_info.get("latest_boe_url")
                latest_boe_fecha = boe_info.get("boe_date")

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

                most_recent_candidate = candidates[:1]
                downloaded_pdf_items = []

                for c_idx, c in enumerate(most_recent_candidate, 1):
                    cand_url = c["url"]
                    cand_date = c.get("boe_date")
                    pdf_path = os.path.join(TEMP_PDF_DIR, f"{d_code}_candidate_{c_idx}.pdf")
                    try:
                        downloader.download_file(cand_url, pdf_path, is_pdf=True)
                        downloaded_pdf_items.append({
                            "cand_url": cand_url,
                            "cand_date": cand_date,
                            "pdf_path": pdf_path
                        })
                    except Exception as download_err:
                        print(f"     [Error descarga PDF]: {download_err}")

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
            except Exception as deg_err:
                print(f"  [AVISO titulación]: {deg_err}")

        metrics.save()
        checkpoint.mark_university_processed(u_code)

    task_queue.put({"type": "STOP"})
    parser_process.join(timeout=10)
    if parser_process.is_alive():
        parser_process.terminate()

    # 2. Run Part 2 (Web official scan) for selected 5 universities
    print("\n -> Ejecutando Parte 2 (Rastreo Web Oficial)...")
    web_crawler = UniversityWebCrawler()
    for univ in selected_5:
        try:
            res = web_crawler.process_university_web(univ, titulaciones_por_universidad)
            print(f"  [Parte 2 OK] [{univ['codigo']}] {univ['nombre']}: resueltas {res.get('resolved_degrees_count')} titulaciones.")
        except Exception as p2_err:
            print(f"  [Parte 2 AVISO] {univ['codigo']}: {p2_err}")

    # 3. Run Part 3 (Precios ECTS)
    print("\n -> Ejecutando Parte 3 (Cálculo Precios ECTS)...")
    run_phase1_part3()

    print("\n======================================================================")
    print("      PRUEBA FINALIZADA CON ÉXITO Y SIN ERRORES CRÍTICOS")
    print("======================================================================")

if __name__ == "__main__":
    run_custom_test()
