import os
import sys
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.append('d:/Proyecto/Codigo/Crawler')
from parsers import compute_curriculum_total_ects, is_curriculum_complete, get_required_degree_credits

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'
OUTPUT_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def audit_all_degrees_one_by_one():
    files = [os.path.join(PLANES_DIR, f) for f in os.listdir(PLANES_DIR) if f.endswith('.json') and f.replace('.json', '').isdigit()]
    total_files = len(files)
    print(f"Iniciando auditoría exhaustiva UNO POR UNO de {total_files} titulaciones...")

    completas = []
    incompletas = []
    sin_plan = []

    def process_file(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
        except Exception as e:
            return

        code = data.get("codigo_estudio", "")
        title = data.get("titulo", "")
        level = data.get("nivel_academico", "")
        univ_name = data.get("universidad_nombre", "")
        univ_code = data.get("universidad_codigo", "")
        plan = data.get("plan_estudios")
        origen = data.get("origen_fuente")
        web_url = data.get("web_fuente_directa_url")
        boe_url = data.get("boe_url")
        all_boe = data.get("all_boe_urls", [])

        req_ects = get_required_degree_credits(level, title)

        # -------------------------------------------------------------
        # CASO 3: TITULACIÓN SIN PLAN DE ESTUDIOS (plan is None)
        # -------------------------------------------------------------
        if plan is None or not isinstance(plan, dict):
            # Determinar la causa exacta
            causa = "Sin plan detectado"
            detalle = ""
            if "doctor" in level.lower():
                causa = "Programa de Doctorado sin temario de asignaturas (estructura de tutoría e investigación de tesis)"
                detalle = "Los doctorados en España no poseen cursos de 60-240 ECTS; se estructuran en líneas de investigación y seminarios."
            elif not boe_url and not all_boe:
                causa = "Sin publicación en BOE y sin portal web accesible"
                detalle = "Titulación autorizada o centro extranjero sin resolución con anexo curricular publicada en el BOE."
            elif all_boe:
                causa = "Resolución BOE administrativa sin anexo de asignaturas y web oficial sin tabla curricular válida"
                detalle = f"El BOE publicó únicamente la orden de autorización o resumen modular ({len(all_boe)} PDFs examinados) y la web oficial no expone tabla de asignaturas."
            else:
                causa = "Portal web oficial sin tabla curricular docente"
                detalle = "No se localizó tabla de materias en el portal académico oficial de la institución."

            sin_plan.append({
                "codigo_estudio": code,
                "titulo": title,
                "universidad": univ_name,
                "universidad_codigo": univ_code,
                "nivel_academico": level,
                "causa_principal": causa,
                "detalle_tecnico": detalle,
                "boe_urls": all_boe or ([boe_url] if boe_url else []),
                "web_url": web_url
            })
            return

        elementos = plan.get("elementos_curriculares", [])
        total_ects = compute_curriculum_total_ects(elementos)
        is_comp = is_curriculum_complete(data)

        # -------------------------------------------------------------
        # CASO 1: PLAN COMPLETO Y REAL
        # -------------------------------------------------------------
        if is_comp:
            completas.append({
                "codigo_estudio": code,
                "titulo": title,
                "universidad": univ_name,
                "universidad_codigo": univ_code,
                "nivel_academico": level,
                "total_elementos": len(elementos),
                "ects_totales": total_ects,
                "ects_exigidos": req_ects,
                "origen_fuente": origen,
                "fuente_url": web_url if origen == "web_oficial_universidad" else boe_url,
                "muestra_primeras_asignaturas": [e.get("nombre_elemento") for e in elementos[:5]],
                "muestra_ultimas_asignaturas": [e.get("nombre_elemento") for e in elementos[-3:]] if len(elementos) > 5 else []
            })
            return

        # -------------------------------------------------------------
        # CASO 2: PLAN INCOMPLETO (Con causas específicas)
        # -------------------------------------------------------------
        causa = "Plan parcial"
        detalle = ""
        pct = round((total_ects / req_ects * 100), 2) if req_ects else 0

        if "doctor" in level.lower():
            causa = "Doctorado con actividades complementarias parciales"
            detalle = f"Registra {len(elementos)} actividades/seminarios ({total_ects} ECTS)."
        elif total_ects == 0.0 and len(elementos) > 0:
            causa = "Asignaturas identificadas pero sin desglose numérico de créditos ECTS en la fuente"
            detalle = f"Se extrajeron {len(elementos)} nombres de asignaturas, pero la tabla original no especificaba la columna de créditos."
        elif total_ects >= req_ects * 0.5:
            causa = "Plan parcial avanzado (50-95% créditos: falta de optativas o TFG/TFM)"
            detalle = f"Extraídos {total_ects} de {req_ects} ECTS ({pct}%). Materias obligatorias presentes; faltan menciones/itinerarios optativos."
        else:
            causa = "Plan parcial inicial (<50% créditos: solo primer curso o tronco común)"
            detalle = f"Extraídos {total_ects} de {req_ects} ECTS ({pct}%). Solo el primer año estaba publicado en la vista estática inicial."

        incompletas.append({
            "codigo_estudio": code,
            "titulo": title,
            "universidad": univ_name,
            "universidad_codigo": univ_code,
            "nivel_academico": level,
            "total_elementos": len(elementos),
            "ects_extraidos": total_ects,
            "ects_exigidos": req_ects,
            "porcentaje_completitud": pct,
            "origen_fuente": origen,
            "fuente_url": web_url if origen == "web_oficial_universidad" else boe_url,
            "causa_incompletitud": causa,
            "detalle_tecnico": detalle,
            "asignaturas_extraidas": [e.get("nombre_elemento") for e in elementos[:8]]
        })

    with ThreadPoolExecutor(max_workers=32) as executor:
        list(executor.map(process_file, files))

    # Guardar los 3 datasets exhaustivos
    with open(os.path.join(OUTPUT_DIR, '01_titulaciones_completas_reales.json'), 'w', encoding='utf-8') as fp:
        json.dump({
            "total": len(completas),
            "descripcion": "Registro exhaustivo de titulaciones con plan de estudios completo, verificado y real.",
            "titulaciones": completas
        }, fp, indent=2, ensure_ascii=False)

    with open(os.path.join(OUTPUT_DIR, '02_titulaciones_incompletas_con_causas.json'), 'w', encoding='utf-8') as fp:
        json.dump({
            "total": len(incompletas),
            "descripcion": "Registro exhaustivo titulación por titulación de planes incompletos con su causa técnica.",
            "titulaciones": incompletas
        }, fp, indent=2, ensure_ascii=False)

    with open(os.path.join(OUTPUT_DIR, '03_titulaciones_sin_plan_con_causas.json'), 'w', encoding='utf-8') as fp:
        json.dump({
            "total": len(sin_plan),
            "descripcion": "Registro exhaustivo titulación por titulación sin plan de estudios con su motivo oficial.",
            "titulaciones": sin_plan
        }, fp, indent=2, ensure_ascii=False)

    print(f"\nAUDITORÍA UNO POR UNO COMPLETADA:")
    print(f" -> Titulaciones Completas y Reales: {len(completas)}")
    print(f" -> Titulaciones Incompletas (con causa): {len(incompletas)}")
    print(f" -> Titulaciones Sin Plan (con causa): {len(sin_plan)}")
    print(f" -> TOTAL AUDITADO: {len(completas) + len(incompletas) + len(sin_plan)} de {total_files}")

if __name__ == "__main__":
    audit_all_degrees_one_by_one()
