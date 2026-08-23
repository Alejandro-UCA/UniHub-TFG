import os
import sys
import json
import glob
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.append('d:/Proyecto/Codigo/Crawler')
from parsers import compute_curriculum_total_ects, is_curriculum_complete, get_required_degree_credits

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'
ERRORES_FILE = 'd:/Proyecto/Codigo/Crawler/Datos/errores_crawler.json'
CHECKPOINT_FILE = 'd:/Proyecto/Codigo/Crawler/Datos/checkpoint.json'

files = [os.path.join(PLANES_DIR, f) for f in os.listdir(PLANES_DIR) if f.endswith('.json') and f.replace('.json', '').isdigit()]

print(f"Auditing {len(files)} degree JSON files across all quality dimensions...")

anomalies = defaultdict(list)

def audit_degree_file(fpath):
    try:
        with open(fpath, 'r', encoding='utf-8') as fp:
            d = json.load(fp)
    except Exception as e:
        anomalies["json_corrupt"].append((fpath, str(e)))
        return

    code = d.get("codigo_estudio", "")
    fname_code = os.path.splitext(os.path.basename(fpath))[0]
    if code != fname_code:
        anomalies["code_mismatch"].append((fpath, code, fname_code))

    title = d.get("titulo", "")
    if not title:
        anomalies["missing_title"].append(fpath)

    level = d.get("nivel_academico", "")
    if not level:
        anomalies["missing_level"].append(fpath)

    u_code = d.get("universidad_codigo", "")
    if not u_code:
        anomalies["missing_u_code"].append(fpath)

    plan = d.get("plan_estudios")
    origen = d.get("origen_fuente")
    web_url = d.get("web_fuente_directa_url")

    # Audit Pricing
    precio_ects = d.get("precio_credito_ects")
    if precio_ects is not None:
        try:
            p_float = float(precio_ects)
            if p_float <= 0 or p_float > 400.0:
                anomalies["anomalous_price_ects"].append((code, title, p_float, d.get("fuente_precio")))
        except Exception:
            anomalies["invalid_price_format"].append((code, precio_ects))

    if plan is not None and isinstance(plan, dict):
        elems = plan.get("elementos_curriculares", [])
        if not isinstance(elems, list):
            anomalies["invalid_elements_structure"].append((code, type(elems)))
            return

        total_ects = compute_curriculum_total_ects(elems)
        
        # Check individual subject anomalies
        for e in elems:
            s_name = str(e.get("nombre_elemento", "")).strip()
            if not s_name:
                anomalies["empty_subject_name"].append(code)
            
            # Check for suspicious single subject credit values (> 30 ECTS for a single subject unless TFG/Practicum)
            c_val = e.get("creditos_ects") or e.get("creditos")
            if c_val:
                try:
                    c_float = float(str(c_val).replace(",", "."))
                    if c_float < 0:
                        anomalies["negative_credits"].append((code, s_name, c_float))
                    elif c_float > 30.0 and not any(k in s_name.lower() for k in ["trabajo", "tfg", "tfm", "practicum", "prácticas", "tesis"]):
                        anomalies["excessive_subject_credits"].append((code, s_name, c_float))
                except Exception:
                    pass

        # Check for suspicious URLs
        if web_url:
            u_low = web_url.lower()
            if any(k in u_low for k in ["facebook.com", "twitter.com", "instagram.com", "linkedin.com", "youtube.com"]):
                anomalies["social_media_url_as_source"].append((code, web_url))
            elif any(k in u_low for k in ["wp-login", "user/login", "admin/"]):
                anomalies["login_admin_url_as_source"].append((code, web_url))

with ThreadPoolExecutor(max_workers=32) as executor:
    list(executor.map(audit_degree_file, files))

print("\n=======================================================================")
print("  REPORTE COMPLETO DE ANOMALÍAS Y PUNTOS A MEJORAR")
print("=======================================================================")
for k, v in anomalies.items():
    print(f"\n[ANOMALÍA: {k}] -> Total: {len(v)} casos")
    for item in v[:5]:
        print(f"   -> {item}")

if not anomalies:
    print("\n✅ ¡0 anomalías de corrupción, precios inválidos o URLs ilegítimas detectadas en el dataset!")
