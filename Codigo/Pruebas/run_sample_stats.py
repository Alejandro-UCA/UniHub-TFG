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

def main():
    json_files = glob.glob(os.path.join(PLANES_DIR, "*.json"))
    sample_data = []

    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                d = json.load(f)
            u_code = d.get("universidad_codigo")
            if u_code in TEST_UNIV_CODES:
                sample_data.append(d)
        except Exception:
            pass

    total = len(sample_data)
    exito = 0
    solo_meta = 0
    sin_plan = 0
    total_asig = 0

    per_univ = {}

    for d in sample_data:
        uc = d.get("universidad_codigo")
        un = d.get("universidad_nombre")
        if uc not in per_univ:
            per_univ[uc] = {"nombre": un, "total": 0, "exito": 0, "solo_meta": 0, "sin_plan": 0, "total_asignaturas": 0}
        per_univ[uc]["total"] += 1

        plan = d.get("plan_estudios")
        boe_url = d.get("boe_url")

        valid_items = []
        if plan and isinstance(plan, dict):
            elementos = plan.get("elementos_curriculares", [])
            valid_items = [e for e in elementos if is_valid_subject_item(e)]

        if len(valid_items) > 0:
            exito += 1
            per_univ[uc]["exito"] += 1
            asig_cnt = len(valid_items)
            total_asig += asig_cnt
            per_univ[uc]["total_asignaturas"] += asig_cnt
        elif boe_url:
            solo_meta += 1
            per_univ[uc]["solo_meta"] += 1
        else:
            sin_plan += 1
            per_univ[uc]["sin_plan"] += 1

    print("SAMPLE_RESULT_START")
    print(json.dumps({
        "total_titulaciones_muestra": total,
        "exito_total": exito,
        "tasa_exito_porcentaje": round((exito / total) * 100, 2) if total > 0 else 0,
        "solo_metadatos_boe": solo_meta,
        "tasa_solo_metadatos_porcentaje": round((solo_meta / total) * 100, 2) if total > 0 else 0,
        "sin_plan": sin_plan,
        "total_asignaturas_extraidas": total_asig,
        "promedio_asignaturas_por_titulo_exitoso": round(total_asig / exito, 1) if exito > 0 else 0,
        "desglose_por_universidad": per_univ
    }, indent=2, ensure_ascii=False))
    print("SAMPLE_RESULT_END")

if __name__ == "__main__":
    main()
