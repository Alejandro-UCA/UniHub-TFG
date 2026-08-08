import os
import glob
import json

PLANES_DIR = r"d:\Proyecto\Codigo\Crawler\Datos\planes_estudio"
TEST_UNIV_CODES = {"086", "105", "092", "099", "089"}

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

def analyze_sample():
    json_files = glob.glob(os.path.join(PLANES_DIR, "*.json"))
    
    sample_files = []
    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            u_code = data.get("universidad_codigo")
            if u_code in TEST_UNIV_CODES:
                sample_files.append((filepath, data))
        except Exception:
            pass

    total_degrees = len(sample_files)
    exito_total_boe = 0
    exito_total_web = 0
    solo_metadatos = 0
    sin_plan = 0
    total_asignaturas = 0

    univ_summary = {code: {"nombre": "", "total": 0, "exito_total": 0, "solo_metadatos": 0, "sin_plan": 0, "asignaturas": 0} for code in TEST_UNIV_CODES}

    for filepath, data in sample_files:
        u_code = data.get("universidad_codigo")
        u_name = data.get("universidad_nombre")
        univ_summary[u_code]["nombre"] = u_name
        univ_summary[u_code]["total"] += 1

        plan = data.get("plan_estudios")
        boe_url = data.get("boe_url")
        origen = data.get("origen_fuente", "boe")

        has_valid_subjects = False
        if plan and isinstance(plan, dict):
            elementos = plan.get("elementos_curriculares", [])
            valid_items = [e for e in elementos if is_valid_subject_item(e)]
            if len(valid_items) > 0:
                has_valid_subjects = True
                cnt = len(valid_items)
                total_asignaturas += cnt
                univ_summary[u_code]["asignaturas"] += cnt

        if has_valid_subjects:
            if origen == "web_oficial_universidad":
                exito_total_web += 1
            else:
                exito_total_boe += 1
            univ_summary[u_code]["exito_total"] += 1
        elif boe_url:
            solo_metadatos += 1
            univ_summary[u_code]["solo_metadatos"] += 1
        else:
            sin_plan += 1
            univ_summary[u_code]["sin_plan"] += 1

    exito_total = exito_total_boe + exito_total_web
    tasa_exito = round((exito_total / total_degrees) * 100, 2) if total_degrees > 0 else 0
    tasa_metadatos = round((solo_metadatos / total_degrees) * 100, 2) if total_degrees > 0 else 0

    report = {
        "total_titulaciones_muestra": total_degrees,
        "exito_total_verdaderas_asignaturas": exito_total,
        "tasa_exito_real_porcentaje": tasa_exito,
        "desglose_exito": {
            "via_boe_pdf": exito_total_boe,
            "via_web_oficial": exito_total_web
        },
        "solo_metadatos_boe_sin_desglose": solo_metadatos,
        "tasa_solo_metadatos_porcentaje": tasa_metadatos,
        "sin_plan": sin_plan,
        "total_asignaturas_extraidas": total_asignaturas,
        "promedio_asignaturas_por_titulo_exitoso": round(total_asignaturas / exito_total, 1) if exito_total > 0 else 0,
        "desglose_por_universidad": univ_summary
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    analyze_sample()
