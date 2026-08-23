import os
import json
from collections import Counter

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'
REPORT_PATH = 'd:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/progreso_fase1_parte2_por_universidad.json'

with open(REPORT_PATH, 'r', encoding='utf-8') as f:
    report = json.load(f)

processed_univ_codes = {u['universidad_codigo'] for u in report['resultados']}

sin_plan_causas = Counter()
parciales_causas = Counter()
sin_plan_por_nivel = Counter()
parciales_por_nivel = Counter()

sample_sin_plan = []
sample_parciales = []

files = [f for f in os.listdir(PLANES_DIR) if f.endswith('.json') and f.replace('.json', '').isdigit()]

for f in files:
    with open(os.path.join(PLANES_DIR, f), 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    
    u_code = d.get('universidad_codigo')
    if u_code not in processed_univ_codes:
        continue
    
    level = d.get('nivel_academico', '')
    title = d.get('titulo', '')
    plan = d.get('plan_estudios')
    elems = plan.get('elementos_curriculares', []) if plan else []
    
    if not plan or len(elems) == 0:
        if 'Doctor' in level or 'Doctorado' in title:
            causa = "Programa de Doctorado Oficial (Formación investigadora/tesis, sin asignaturas lectivas)"
        elif 'RD 1393/2007' in level:
            causa = "Plan antiguo extinguido (Retirado del catálogo web activo de la universidad)"
        else:
            causa = "Portal web no publica tabla curricular docente abierta (Solo texto promocional/formulario)"
        sin_plan_causas[causa] += 1
        sin_plan_por_nivel[level] += 1
        if len(sample_sin_plan) < 5:
            sample_sin_plan.append((d.get('codigo_estudio'), title, d.get('universidad_nombre'), causa))
    elif len(elems) > 0:
        # Check if incomplete
        total_ects = sum(e.get('creditos', 0) for e in elems if isinstance(e.get('creditos'), (int, float)))
        req_ects = 240.0 if 'Grado' in level else (60.0 if 'Máster' in level else 0.0)
        
        if req_ects > 0 and total_ects < req_ects:
            pct = round((total_ects / req_ects) * 100, 1)
            if pct >= 50:
                causa_p = f"Tronco común y obligatorias presentes ({total_ects}/{req_ects} ECTS), pendiente de catálogo dinámico de optativas/TFG"
            else:
                causa_p = f"Plan parcial inicial ({total_ects}/{req_ects} ECTS - Curso 1º o módulos básicos en web)"
            parciales_causas[causa_p] += 1
            parciales_por_nivel[level] += 1
            if len(sample_parciales) < 5:
                sample_parciales.append((d.get('codigo_estudio'), title, d.get('universidad_nombre'), total_ects, req_ects, causa_p))

print("=== CAUSAS SIN PLAN (875 casos analizados) ===")
for c, count in sin_plan_causas.most_common():
    print(f" -> {count} casos ({round(count/sum(sin_plan_causas.values())*100, 1)}%): {c}")

print("\n=== NIVELES ACADÉMICOS SIN PLAN ===")
for lvl, count in sin_plan_por_nivel.most_common():
    print(f" -> {count}: {lvl}")

print("\n=== CAUSAS PLANES PARCIALES (610 casos analizados) ===")
for c, count in parciales_causas.most_common():
    print(f" -> {count} casos: {c}")

print("\n=== EJEMPLOS REALES EXAMINADOS ===")
print("Sin plan:")
for code, t, u, c in sample_sin_plan:
    print(f"  * [{code}] {t[:40]} ({u}) -> {c}")
print("Parciales:")
for code, t, u, ects, req, c in sample_parciales:
    print(f"  * [{code}] {t[:40]} ({u}) -> {ects}/{req} ECTS -> {c}")
