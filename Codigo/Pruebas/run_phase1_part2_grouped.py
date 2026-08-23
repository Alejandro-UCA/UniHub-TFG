import os
import sys
import json
import time
from collections import defaultdict

sys.path.append('d:/Proyecto/Codigo/Crawler')
from univ_web_crawler import UniversityWebCrawler
from parsers import is_curriculum_complete, compute_curriculum_total_ects, get_required_degree_credits

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'
UNIVERSIDADES_JSON = 'd:/Proyecto/Codigo/Crawler/Datos/universidades.json'
REPORT_OUTPUT = 'd:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/progreso_fase1_parte2_por_universidad.json'
os.makedirs(os.path.dirname(REPORT_OUTPUT), exist_ok=True)

def main():
    print("=======================================================================")
    print("  FASE 1 PARTE 2: RESCATE WEB DE PLANES INCOMPLETOS / SIN PLAN")
    print("=======================================================================")

    # 1. Cargar metadatos de universidades
    with open(UNIVERSIDADES_JSON, 'r', encoding='utf-8') as f:
        univs_list = json.load(f)
    univ_by_code = {u.get("codigo"): u for u in univs_list}

    # 2. Agrupar titulaciones sin plan o incompletas por universidad
    files = [f for f in os.listdir(PLANES_DIR) if f.endswith('.json') and f.replace('.json', '').isdigit()]
    grouped_missing = defaultdict(list)
    total_missing = 0

    for fname in files:
        fpath = os.path.join(PLANES_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as fp:
                d = json.load(fp)
        except Exception:
            continue

        if not is_curriculum_complete(d):
            u_code = d.get("universidad_codigo")
            if u_code:
                grouped_missing[u_code].append(d)
                total_missing += 1

    print(f"Total de titulaciones incompletas / sin plan identificadas: {total_missing}")
    print(f"Total de universidades con titulaciones pendientes: {len(grouped_missing)}")
    print("=======================================================================\n")

    crawler = UniversityWebCrawler()
    results_summary = []

    # 3. Procesar universidad por universidad
    sorted_u_codes = sorted(grouped_missing.keys())

    for idx, u_code in enumerate(sorted_u_codes, 1):
        univ = univ_by_code.get(u_code)
        if not univ:
            univ = {
                "codigo": u_code,
                "nombre": grouped_missing[u_code][0].get("universidad_nombre", f"Universidad {u_code}"),
                "web": grouped_missing[u_code][0].get("web_fuente_directa_url") or f"https://www.{u_code}.es",
                "tipo": "Pública"
            }

        u_name = univ.get("nombre")
        missing_degs = grouped_missing[u_code]
        n_missing = len(missing_degs)

        print(f"\n=======================================================================")
        print(f" [{idx}/{len(sorted_u_codes)}] PROCESANDO UNIVERSIDAD [{u_code}]: {u_name}")
        print(f" -> Titulaciones pendientes a rastrear: {n_missing}")
        print(f" -> Web oficial: {univ.get('web')}")
        print(f"=======================================================================")

        # Estado inicial
        before_status = {d.get("codigo_estudio"): is_curriculum_complete(d) for d in missing_degs}

        # Ejecutar rastreo web oficial con Hub-and-Spoke
        start_t = time.time()
        try:
            crawler.process_university_web(univ, missing_degs)
        except Exception as e:
            print(f" [ERROR] Excepción al procesar universidad [{u_code}]: {e}")
        elapsed = round(time.time() - start_t, 2)

        # Estado posterior: comprobar qué titulaciones cambiaron
        rescued_degrees = []
        partial_improved_degrees = []
        still_unresolved = []

        for d in missing_degs:
            d_code = d.get("codigo_estudio")
            fpath = os.path.join(PLANES_DIR, f"{d_code}.json")
            try:
                with open(fpath, 'r', encoding='utf-8') as fp:
                    after_d = json.load(fp)
            except Exception:
                after_d = d

            was_comp = before_status.get(d_code, False)
            is_comp_now = is_curriculum_complete(after_d)

            plan = after_d.get("plan_estudios")
            elems = plan.get("elementos_curriculares", []) if plan else []
            total_ects = compute_curriculum_total_ects(elems)
            req_ects = get_required_degree_credits(after_d.get("nivel_academico", ""), after_d.get("titulo", ""))

            if is_comp_now and not was_comp:
                rescued_degrees.append({
                    "codigo": d_code,
                    "titulo": after_d.get("titulo"),
                    "ects": total_ects,
                    "fuente": after_d.get("web_fuente_directa_url")
                })
            elif len(elems) > 0 and not is_comp_now:
                partial_improved_degrees.append({
                    "codigo": d_code,
                    "titulo": after_d.get("titulo"),
                    "ects_obtenidos": total_ects,
                    "ects_exigidos": req_ects,
                    "fuente": after_d.get("web_fuente_directa_url")
                })
            else:
                still_unresolved.append({
                    "codigo": d_code,
                    "titulo": after_d.get("titulo"),
                    "nivel": after_d.get("nivel_academico")
                })

        # Reporte individual de la universidad
        print(f"\n >>> RESULTADOS UNIVERSIDAD [{u_code}] {u_name} (Tiempo: {elapsed}s):")
        print(f"     [OK] Titulaciones Rescatadas con Plan COMPLETO y REAL: {len(rescued_degrees)} / {n_missing}")
        for r in rescued_degrees[:5]:
            print(f"        * [{r['codigo']}] {r['titulo'][:50]} ({r['ects']} ECTS) -> {r['fuente']}")
        if len(rescued_degrees) > 5:
            print(f"        ... y {len(rescued_degrees)-5} más.")

        if partial_improved_degrees:
            print(f"     [PARCIAL] Titulaciones Parciales con Asignaturas Extraídas: {len(partial_improved_degrees)}")
        if still_unresolved:
            print(f"     [SIN PLAN] Titulaciones Sin Plan Disponible en Web: {len(still_unresolved)}")

        # Guardar en reporte consolidado
        univ_report = {
            "universidad_codigo": u_code,
            "universidad_nombre": u_name,
            "web_url": univ.get("web"),
            "titulaciones_pendientes_iniciales": n_missing,
            "titulaciones_completadas_con_exito": len(rescued_degrees),
            "titulaciones_parciales": len(partial_improved_degrees),
            "titulaciones_sin_plan": len(still_unresolved),
            "tiempo_segundos": elapsed,
            "detalles_rescatadas": rescued_degrees
        }
        results_summary.append(univ_report)

        with open(REPORT_OUTPUT, 'w', encoding='utf-8') as fp:
            json.dump({
                "universidades_procesadas": len(results_summary),
                "total_universidades": len(sorted_u_codes),
                "resultados": results_summary
            }, fp, indent=2, ensure_ascii=False)

    print("\n=======================================================================")
    print("  FASE 1 PARTE 2 FINALIZADA PARA TODAS LAS UNIVERSIDADES")
    print("=======================================================================")

if __name__ == "__main__":
    main()
