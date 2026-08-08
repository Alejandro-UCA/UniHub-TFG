import os
import glob
import json
import time

PLANES_DIR = r"d:\Proyecto\Codigo\Crawler\Datos\planes_estudio"
OUTPUT_FILE = r"C:\Users\aleja\.gemini\antigravity\brain\a0ec713f-b4e4-4ff2-bc07-7f8151a1a42a\scratch\extraction_report.json"

HEADER_KEYWORDS = ["asignatura", "materia", "nombre", "crédito", "credito", "ects", "curso", "carácter", "caracter", "tipo", "código", "codigo", "guía", "guia"]
INVALID_SUBJECT_KEYWORDS = ["lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "aula", "edificio", "horario", "calendario", "examen", "convocatoria"]

def is_valid_subject_item(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    name = item.get("nombre_elemento", "").strip()
    if not name or len(name) < 4:
        return False
    name_lower = name.lower()
    if any(hk in name_lower for hk in HEADER_KEYWORDS) or any(sk in name_lower for sk in INVALID_SUBJECT_KEYWORDS):
        return False
    return True

def analyze():
    t0 = time.time()
    json_files = glob.glob(os.path.join(PLANES_DIR, "*.json"))
    total_files = len(json_files)

    exito_total_boe = 0
    exito_total_web = 0
    solo_metadatos_boe = 0
    sin_plan = 0
    total_asignaturas_extraidas = 0

    universidades_stats = {}

    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            u_code = data.get("universidad_codigo", "DESCONOCIDA")
            u_name = data.get("universidad_nombre", "Desconocida")
            if u_code not in universidades_stats:
                universidades_stats[u_code] = {
                    "nombre": u_name,
                    "total": 0,
                    "exito_total": 0,
                    "solo_metadatos": 0,
                    "sin_plan": 0
                }
            universidades_stats[u_code]["total"] += 1

            plan = data.get("plan_estudios")
            boe_url = data.get("boe_url")
            origen = data.get("origen_fuente", "boe")

            has_valid_subjects = False
            valid_subject_count = 0

            if plan and isinstance(plan, dict):
                elementos = plan.get("elementos_curriculares", [])
                valid_items = [e for e in elementos if is_valid_subject_item(e)]
                valid_subject_count = len(valid_items)
                if valid_subject_count > 0:
                    has_valid_subjects = True
                    total_asignaturas_extraidas += valid_subject_count

            if has_valid_subjects:
                if origen == "web_oficial_universidad":
                    exito_total_web += 1
                else:
                    exito_total_boe += 1
                universidades_stats[u_code]["exito_total"] += 1
            elif boe_url:
                solo_metadatos_boe += 1
                universidades_stats[u_code]["solo_metadatos"] += 1
            else:
                sin_plan += 1
                universidades_stats[u_code]["sin_plan"] += 1

        except Exception:
            sin_plan += 1

    exito_total = exito_total_boe + exito_total_web
    tasa_exito_real = round((exito_total / total_files) * 100, 2) if total_files > 0 else 0
    tasa_boe_parcial = round((solo_metadatos_boe / total_files) * 100, 2) if total_files > 0 else 0
    tasa_sin_plan = round((sin_plan / total_files) * 100, 2) if total_files > 0 else 0

    report = {
        "tiempo_ejecucion_seg": round(time.time() - t0, 2),
        "total_titulaciones_analizadas": total_files,
        "exito_total_verdaderas_asignaturas": exito_total,
        "tasa_exito_real_porcentaje": tasa_exito_real,
        "desglose_exito": {
            "via_boe_pdf": exito_total_boe,
            "via_web_oficial": exito_total_web
        },
        "solo_metadatos_boe_sin_desglose": solo_metadatos_boe,
        "tasa_boe_parcial_porcentaje": tasa_boe_parcial,
        "sin_plan_estudios": sin_plan,
        "tasa_sin_plan_porcentaje": tasa_sin_plan,
        "total_asignaturas_extraidas": total_asignaturas_extraidas,
        "promedio_asignaturas_por_titulo_exitoso": round(total_asignaturas_extraidas / exito_total, 1) if exito_total > 0 else 0,
        "total_universidades_analizadas": len(universidades_stats),
        "top_universidades": dict(list(sorted(universidades_stats.items(), key=lambda x: x[1]["exito_total"], reverse=True))[:15])
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("SUCCESS: Report saved to", OUTPUT_FILE)

if __name__ == "__main__":
    analyze()
