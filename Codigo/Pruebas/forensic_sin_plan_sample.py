import os, sys, json, requests
sys.path.append('d:/Proyecto/Codigo/Crawler')
from parsers import parse_degree_detail_html, parse_boe_pdf
from bs4 import BeautifulSoup

REPORT_PATH = 'd:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/progreso_fase1_parte2_por_universidad.json'
PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'

with open(REPORT_PATH, 'r', encoding='utf-8') as f:
    report = json.load(f)

processed_codes = {u['universidad_codigo'] for u in report['resultados']}

sample_sin_plan = []
for f in os.listdir(PLANES_DIR):
    if not (f.endswith('.json') and f.replace('.json', '').isdigit()):
        continue
    with open(os.path.join(PLANES_DIR, f), 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    if d.get('universidad_codigo') not in processed_codes:
        continue
    
    level = d.get('nivel_academico', '')
    title = d.get('titulo', '')
    if 'Doctor' in level or 'Doctorado' in title:
        continue
    
    plan = d.get('plan_estudios')
    elems = plan.get('elementos_curriculares', []) if (plan and isinstance(plan, dict)) else []
    if len(elems) == 0:
        sample_sin_plan.append(d)

print(f"Total títulos de Grado/Máster 'Sin Plan' en las 11 universidades procesadas: {len(sample_sin_plan)}")
print("\n--- ANÁLISIS FORENSE DE MUESTRA ---")

for idx, deg in enumerate(sample_sin_plan[:8], 1):
    code = deg.get('codigo_estudio')
    title = deg.get('titulo')
    univ = deg.get('universidad_nombre')
    u_code = deg.get('universidad_codigo')
    web_url = deg.get('web_fuente_directa_url', '')
    boe_url = deg.get('boe_url', '')
    level = deg.get('nivel_academico', '')
    
    print(f"\n[{idx}] Titulación: [{code}] {title}")
    print(f"    Universidad: [{u_code}] {univ} | Nivel: {level}")
    print(f"    BOE: {boe_url}")
    print(f"    Web registrada: {web_url if web_url else '(Ninguna encontrada)'}")
