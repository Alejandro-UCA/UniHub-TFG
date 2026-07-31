import os
import sys
import json
import argparse
from datetime import datetime

from config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    ERRORES_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    URL_UNIVERSIDADES_LIST,
    URL_ESTUDIOS_UNIV_TEMPLATE,
    URL_DETALLE_ESTUDIO_TEMPLATE
)
from downloader import RUCTDownloader
from error_logger import ErrorLogger
from checkpoint import CheckpointManager
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
    print("=" * 70)
    
    downloader = RUCTDownloader()
    logger = ErrorLogger()
    checkpoint = CheckpointManager()
    
    # -------------------------------------------------------------------------
    # PASO 1: Descargar y procesar la lista de universidades
    # -------------------------------------------------------------------------
    universities = []
    if not checkpoint.state.get("universities_downloaded") or not os.path.exists(UNIVERSIDADES_JSON):
        print("\n[Paso 1] Descargando listado oficial de universidades desde RUCT...")
        try:
            temp_univ_xls = os.path.join(TEMP_PDF_DIR, "universidades_list.xls")
            downloader.download_file(URL_UNIVERSIDADES_LIST, temp_univ_xls)
            universities = parse_universities_xls(temp_univ_xls)
            
            # Save to universidades.json
            with open(UNIVERSIDADES_JSON, "w", encoding="utf-8") as f:
                json.dump(universities, f, ensure_ascii=False, indent=2)
                
            if os.path.exists(temp_univ_xls):
                os.remove(temp_univ_xls)
                
            checkpoint.mark_universities_downloaded()
            print(f" -> Se han encontrado y guardado {len(universities)} universidades en '{UNIVERSIDADES_JSON}'.")
        except Exception as e:
            err_msg = f"Error al descargar o procesar la lista de universidades: {e}"
            print(f" [ERROR] {err_msg}")
            logger.log_error("paso_1_universidades", "TODAS", URL_UNIVERSIDADES_LIST, "Fallo descarga lista universidades", str(e))
            return
    else:
        print(f"\n[Paso 1] Cargando universidades guardadas previamente en '{UNIVERSIDADES_JSON}'...")
        with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
            universities = json.load(f)
        print(f" -> {len(universities)} universidades cargadas.")

    if limit_univ:
        universities = universities[:limit_univ]
        print(f" [INFO] Modo de prueba activado: limitado a {limit_univ} universidades.")

    # Load existing titulaciones dict if available
    titulaciones_por_universidad = {}
    if os.path.exists(TITULACIONES_JSON):
        try:
            with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
                titulaciones_por_universidad = json.load(f)
        except Exception:
            titulaciones_por_universidad = {}

    # -------------------------------------------------------------------------
    # PASO 2 y 3: Recorrer universidades y descargar titulaciones vigentes + BOEs
    # -------------------------------------------------------------------------
    print("\n[Paso 2 y 3] Extrayendo titulaciones vigentes y planes de estudio BOE por universidad...")
    total_univ = len(universities)
    
    for u_idx, univ in enumerate(universities, 1):
        u_code = univ["codigo"]
        u_name = univ["nombre"]
        print(f"\n({u_idx}/{total_univ}) Procesando Universidad [{u_code}]: {u_name}")
        
        # Download degree list for this university if not already saved
        active_degrees = []
        if u_code in titulaciones_por_universidad and checkpoint.is_university_processed(u_code):
            active_degrees = titulaciones_por_universidad[u_code].get("titulaciones_vigentes", [])
            print(f" -> Universidad ya procesada previamente ({len(active_degrees)} titulaciones vigentes).")
        else:
            degrees_url = URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo=u_code)
            temp_degrees_xls = os.path.join(TEMP_PDF_DIR, f"degrees_{u_code}.xls")
            try:
                downloader.download_file(degrees_url, temp_degrees_xls)
                active_degrees = parse_degrees_xls(temp_degrees_xls)
                
                # Save into structure
                titulaciones_por_universidad[u_code] = {
                    "universidad_codigo": u_code,
                    "universidad_nombre": u_name,
                    "universidad_tipo": univ.get("tipo", ""),
                    "comunidad_autonoma": univ.get("comunidad_autonoma", ""),
                    "total_titulaciones_vigentes": len(active_degrees),
                    "titulaciones_vigentes": active_degrees
                }
                
                with open(TITULACIONES_JSON, "w", encoding="utf-8") as f:
                    json.dump(titulaciones_por_universidad, f, ensure_ascii=False, indent=2)
                    
                if os.path.exists(temp_degrees_xls):
                    os.remove(temp_degrees_xls)
                    
                print(f" -> Encontradas {len(active_degrees)} titulaciones VIGENTES (excluidas no vigentes).")
            except Exception as e:
                err_msg = f"Error al obtener titulaciones de la universidad {u_code}"
                print(f" [ERROR] {err_msg}: {e}")
                logger.log_error("paso_2_titulaciones", u_code, degrees_url, err_msg, str(e))
                continue

        # Filter limit if testing
        degrees_to_process = active_degrees
        if limit_degrees:
            degrees_to_process = degrees_to_process[:limit_degrees]

        # Process each degree: detail HTML -> latest BOE PDF -> extract curriculum
        for d_idx, deg in enumerate(degrees_to_process, 1):
            d_code = deg["codigo_estudio"]
            d_title = deg["titulo"]
            print(f"   [{d_idx}/{len(degrees_to_process)}] Titulación [{d_code}]: {d_title[:60]}...")
            
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
            if checkpoint.is_degree_processed(d_code) and os.path.exists(plan_file):
                print(f"     -> Ya procesada previamente ({d_code}.json). Omite descarga.")
                continue

            detail_url = URL_DETALLE_ESTUDIO_TEMPLATE.format(codigo_estudio=d_code)
            try:
                html_content = downloader.fetch_text(detail_url)
                boe_info = parse_degree_detail_html(html_content)
                
                latest_boe_url = boe_info.get("latest_boe_url")
                if not latest_boe_url:
                    print(f"     -> [AVISO] No se encontró enlace a BOE en la página de detalle.")
                    logger.log_error("paso_3_boe_link", d_code, detail_url, "Sin enlace a BOE", "No PDF links found in HTML")
                    # Still save basic degree info JSON without curriculum
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
                    checkpoint.mark_degree_processed(d_code)
                    continue

                # Download latest BOE PDF
                pdf_path = os.path.join(TEMP_PDF_DIR, f"{d_code}_latest.pdf")
                print(f"     -> Descargando BOE más reciente ({boe_info.get('boe_date') or 'fecha desconocida'})...")
                downloader.download_file(latest_boe_url, pdf_path)

                # Parse BOE PDF
                curriculum_data = parse_boe_pdf(pdf_path)

                # Save degree JSON output
                degree_data = {
                    "codigo_estudio": d_code,
                    "titulo": d_title,
                    "nivel_academico": deg.get("nivel_academico", ""),
                    "universidad_codigo": u_code,
                    "universidad_nombre": u_name,
                    "fecha_procesado": datetime.now().isoformat(),
                    "boe_url": latest_boe_url,
                    "boe_fecha": boe_info.get("boe_date"),
                    "plan_estudios": curriculum_data
                }

                with open(plan_file, "w", encoding="utf-8") as f:
                    json.dump(degree_data, f, ensure_ascii=False, indent=2)

                # CLEAN UP downloaded PDF immediately as required!
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)

                checkpoint.mark_degree_processed(d_code)
                print(f"     -> Extraídas {curriculum_data.get('total_asignaturas', 0)} asignaturas. Guardado en '{d_code}.json'. PDF borrado.")

            except Exception as e:
                err_msg = f"Error al procesar titulación {d_code}"
                print(f"     -> [ERROR] {err_msg}: {e}")
                logger.log_error("paso_3_boe_parsing", d_code, detail_url, err_msg, str(e))
                # Clean up PDF if left over
                pdf_path = os.path.join(TEMP_PDF_DIR, f"{d_code}_latest.pdf")
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)

        checkpoint.mark_university_processed(u_code)

    print("\n" + "=" * 70)
    print("      CRAWLER COMPLETADO CON ÉXITO")
    print(f" Universidades guardadas: {UNIVERSIDADES_JSON}")
    print(f" Titulaciones por universidad: {TITULACIONES_JSON}")
    print(f" Planes de estudio guardados en: {PLANES_DIR}")
    print(f" Registro de errores en: {ERRORES_JSON}")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawler RUCT de Universidades y Titulaciones de España")
    parser.add_argument("--limit-univ", type=int, default=None, help="Número máximo de universidades a procesar (para pruebas)")
    parser.add_argument("--limit-degrees", type=int, default=None, help="Número máximo de titulaciones por universidad a procesar (para pruebas)")
    
    args = parser.parse_args()
    run_crawler(limit_univ=args.limit_univ, limit_degrees=args.limit_degrees)
