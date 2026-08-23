import os, json
from concurrent.futures import ThreadPoolExecutor

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'
files = [os.path.join(PLANES_DIR, f) for f in os.listdir(PLANES_DIR) if f.endswith('.json') and f.replace('.json', '').isdigit()]

def process_file(fpath):
    try:
        with open(fpath, 'r', encoding='utf-8') as fp:
            d = json.load(fp)
    except Exception:
        return None
    
    level = d.get('nivel_academico', '')
    title = d.get('titulo', '')
    
    if 'Doctor' in level or 'Doctorado' in title:
        return None
    
    plan = d.get('plan_estudios')
    elems = plan.get('elementos_curriculares', []) if (plan and isinstance(plan, dict)) else []
    
    total_ects = 0.0
    for e in elems:
        val_str = str(e.get('creditos_ects') or e.get('creditos') or '0').replace(',', '.').strip()
        try:
            total_ects += float(val_str)
        except ValueError:
            pass
    
    req_ects = 240.0 if 'Grado' in level else 60.0
    
    is_comp = (req_ects > 0 and total_ects >= req_ects)
    is_parc = (len(elems) > 0 and not is_comp)
    
    group = None
    if '822/2021' in level:
        group = '822'
    elif '1393/2007' in level and ('Grado' in level or 'Máster' in level or 'Master' in level):
        group = '1393'
    
    return group, is_comp, is_parc, total_ects

with ThreadPoolExecutor(max_workers=16) as ex:
    results = list(ex.map(process_file, files))

rd822_comp, rd822_parc, rd822_sin = 0, 0, 0
rd1393_comp, rd1393_parc, rd1393_sin = 0, 0, 0

for res in results:
    if not res:
        continue
    group, is_comp, is_parc, total_ects = res
    if group == '822':
        if is_comp:
            rd822_comp += 1
        elif is_parc:
            rd822_parc += 1
        else:
            rd822_sin += 1
    elif group == '1393':
        if is_comp:
            rd1393_comp += 1
        elif is_parc:
            rd1393_parc += 1
        else:
            rd1393_sin += 1

tot_822 = rd822_comp + rd822_parc + rd822_sin
tot_1393 = rd1393_comp + rd1393_parc + rd1393_sin
tot = tot_822 + tot_1393

print(f"=== RESULTADOS GRADOS Y MÁSTERES MATRICULABLES ===")
print(f"TOTAL_GRADOS_Y_MASTERES = {tot}")
print(f"")
print(f"1. PLANES VIGENTES MODERNOS (RD 822/2021 - {tot_822} títulos):")
print(f"   * COMPLETOS Y REALES: {rd822_comp} ({round(rd822_comp/tot_822*100, 1)}%)")
print(f"   * PARCIALES (Con asignaturas): {rd822_parc} ({round(rd822_parc/tot_822*100, 1)}%)")
print(f"   * SIN PLAN: {rd822_sin} ({round(rd822_sin/tot_822*100, 1)}%)")
print(f"   * COBERTURA TOTAL CON ASIGNATURAS: {round((rd822_comp+rd822_parc)/tot_822*100, 1)}%")
print(f"")
print(f"2. PLANES EN IMPARTICIÓN (RD 1393/2007 - {tot_1393} títulos):")
print(f"   * COMPLETOS Y REALES: {rd1393_comp} ({round(rd1393_comp/tot_1393*100, 1)}%)")
print(f"   * PARCIALES (Con asignaturas): {rd1393_parc} ({round(rd1393_parc/tot_1393*100, 1)}%)")
print(f"   * SIN PLAN: {rd1393_sin} ({round(rd1393_sin/tot_1393*100, 1)}%)")
print(f"   * COBERTURA TOTAL CON ASIGNATURAS: {round((rd1393_comp+rd1393_parc)/tot_1393*100, 1)}%")
print(f"")
print(f"3. BALANCE GLOBAL (GRADOS Y MÁSTERES):")
print(f"   * TOTAL COMPLETOS Y REALES: {rd822_comp + rd1393_comp} ({round((rd822_comp + rd1393_comp)/tot*100, 1)}%)")
print(f"   * TOTAL PARCIALES: {rd822_parc + rd1393_parc} ({round((rd822_parc + rd1393_parc)/tot*100, 1)}%)")
print(f"   * TOTAL SIN PLAN: {rd822_sin + rd1393_sin} ({round((rd822_sin + rd1393_sin)/tot*100, 1)}%)")
print(f"   * COBERTURA CURRICULAR GLOBAL: {round((rd822_comp + rd1393_comp + rd822_parc + rd1393_parc)/tot*100, 1)}%")
