import sys
import os
import json
from collections import Counter

sys.path.append("Codigo/Crawler")
sys.stdout.reconfigure(encoding='utf-8')

from config import PLANES_DIR, TITULACIONES_JSON, UNIVERSIDADES_JSON

def run_fire_test_phase1_part3():
    print("\n" + "=" * 70)
    print("      EJECUTANDO PRUEBA DE FUEGO FASE 1 PARTE 3: CONSOLIDACIÓN DE DATOS")
    print("======================================================================\n")

    # 1. Inspect output files in PLANES_DIR
    if not os.path.exists(PLANES_DIR):
        print(f" [ERROR] El directorio {PLANES_DIR} no existe.")
        return

    plan_files = [f for f in os.listdir(PLANES_DIR) if f.endswith(".json")]
    total_plans = len(plan_files)
    print(f" -> Total de planes de estudio estructurados en disco: {total_plans} archivos JSON.")

    if total_plans == 0:
        print(" [AVISO] No se encontraron archivos de planes de estudio en PLANES_DIR.")
        return

    # 2. Analyze curriculum structure quality on sample degrees
    sample_codes = ["2500021", "2504059", "2504639", "4317230"]
    sample_results = []
    
    total_subjects_scanned = 0
    ects_type_counter = Counter()
    course_distribution = Counter()
    total_ects_sum = 0.0

    for code in sample_codes:
        file_path = os.path.join(PLANES_DIR, f"{code}.json")
        if not os.path.exists(file_path):
            continue

        with open(file_path, "r", encoding="utf-8") as pf:
            data = json.load(pf)

        plan = data.get("plan_estudios", {})
        summary_ects = plan.get("resumen_creditos", {})
        elements = plan.get("elementos_curriculares", [])

        # Categorize subjects
        subject_types = Counter()
        ects_in_degree = 0.0
        
        for elem in elements:
            total_subjects_scanned += 1
            stype = elem.get("tipo", "Obligatoria")
            subject_types[stype] += 1
            ects_type_counter[stype] += 1

            course = elem.get("curso", "1º Curso")
            course_distribution[course] += 1

            try:
                ects_val = float(elem.get("creditos_ects", 6))
            except (ValueError, TypeError):
                ects_val = 6.0

            ects_in_degree += ects_val
            total_ects_sum += ects_val

        sample_results.append({
            "codigo_estudio": data.get("codigo_estudio"),
            "titulo": data.get("titulo"),
            "universidad": data.get("universidad_nombre"),
            "fuente_origen": data.get("origen", "BOE / Web Oficial"),
            "precio_ects": data.get("precio_credito_ects"),
            "resumen_creditos": summary_ects,
            "total_asignaturas": len(elements),
            "total_creditos_calculados": round(ects_in_degree, 1),
            "desglose_tipos": dict(subject_types)
        })

    # 3. Print Structured Results
    print("\n -> MUESTRA DE AUDITORÍA DE ESTRUCTURA Y CRÉDITOS (FASE 1 PARTE 3):")
    print(json.dumps(sample_results, ensure_ascii=False, indent=2))

    print("\n" + "=" * 70)
    print("      METRICAS GLOBALIZADAS DE CONSOLIDACIÓN (FASE 1 PARTE 3)")
    print("======================================================================")
    print(f" -> Archivos JSON de Titulaciones Analizados:   {total_plans}")
    print(f" -> Asignaturas Normalizadas en la Muestra:     {total_subjects_scanned}")
    print(f" -> Suma Total Créditos ECTS Muestreados:      {total_ects_sum:.1f} ECTS")
    print(f" -> Distribución por Tipo de Crédito ECTS:      {dict(ects_type_counter)}")
    print(f" -> Distribución por Cursos Académicos:         {dict(course_distribution)}")

if __name__ == "__main__":
    run_fire_test_phase1_part3()
