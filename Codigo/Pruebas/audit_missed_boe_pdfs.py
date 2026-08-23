import os
import sys
import json
import urllib.request
import tempfile
from collections import Counter, defaultdict

sys.path.append('d:/Proyecto/Codigo/Crawler')
from parsers import parse_boe_pdf, compute_curriculum_total_ects, get_required_degree_credits

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'

with open('d:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/02_titulaciones_incompletas_con_causas.json', 'r', encoding='utf-8') as f:
    incompletas = json.load(f)['titulaciones']

with open('d:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/03_titulaciones_sin_plan_con_causas.json', 'r', encoding='utf-8') as f:
    sin_plan = json.load(f)['titulaciones']

print(f"Total incompletas analizadas: {len(incompletas)}")
print(f"Total sin plan analizadas: {len(sin_plan)}")

# Vamos a seleccionar una muestra representativa de 100 PDFs de titulaciones incompletas y sin plan de diferentes universidades y niveles
candidates_to_test = []
for deg in incompletas[:50]:
    code = deg['codigo_estudio']
    p_path = os.path.join(PLANES_DIR, f"{code}.json")
    with open(p_path, 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    if d.get('boe_url'):
        candidates_to_test.append((code, deg['titulo'], deg['nivel_academico'], deg['universidad'], d.get('boe_url'), 'incompleto', deg['ects_extraidos'], deg['ects_exigidos']))

for deg in sin_plan[:50]:
    code = deg['codigo_estudio']
    p_path = os.path.join(PLANES_DIR, f"{code}.json")
    with open(p_path, 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    if d.get('boe_url') and "doctor" not in deg['nivel_academico'].lower():
        candidates_to_test.append((code, deg['titulo'], deg['nivel_academico'], deg['universidad'], d.get('boe_url'), 'sin_plan', 0, get_required_degree_credits(deg['nivel_academico'], deg['titulo'])))

print(f"\nIniciando análisis forense en profundidad de {len(candidates_to_test)} PDFs oficiales del BOE...")

pdf_diagnostics = Counter()
details = []

for code, title, level, univ, boe_url, status, current_ects, req_ects in candidates_to_test[:30]:
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tf:
        tmp_path = tf.name
    
    try:
        req = urllib.request.Request(boe_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            with open(tmp_path, 'wb') as fp:
                fp.write(content)

        # Inspeccionar estructura del PDF
        import pypdf
        reader = pypdf.PdfReader(tmp_path)
        num_pages = len(reader.pages)
        raw_text = "\n".join(p.extract_text() or "" for p in reader.pages)

        # 1. ¿Es un PDF puramente administrativo de 1 página sin tablas?
        has_table_words = any(w in raw_text.lower() for w in ["asignatura", "materia", "denominación", "ects", "carácter"])
        has_subject_list = len(raw_text.splitlines()) > 30 and ("curso" in raw_text.lower() or "cuatrimestre" in raw_text.lower())
        
        # 2. Re-parsear con parse_boe_pdf
        parsed = parse_boe_pdf(tmp_path, target_title=title, univ_name=univ)
        parsed_ects = compute_curriculum_total_ects(parsed.get('elementos_curriculares', []))
        
        if num_pages == 1 and not has_table_words:
            diag = "PDF BOE administrativo de 1 sola página (Decreto ministerial sin anexo de asignaturas)"
        elif "distribución del plan de estudios" in raw_text.lower() and not has_subject_list:
            diag = "PDF BOE con solo tabla resumen modular (FB, OB, OP) sin desglose de asignaturas"
        elif len(raw_text.strip()) < 100:
            diag = "PDF BOE escaneado como imagen (requiere OCR - años 2008-2010)"
        elif parsed_ects >= req_ects:
            diag = "FALSO NEGATIVO: El PDF sí tenía el plan completo"
        elif parsed_ects > current_ects:
            diag = "MEJORABLE: El PDF tenía más asignaturas pero no el 100%"
        else:
            diag = "PDF BOE original contiene únicamente plan parcial (BOE incompleto en origen)"

        pdf_diagnostics[diag] += 1
        details.append({
            "codigo": code,
            "titulo": title[:50],
            "univ": univ,
            "boe_url": boe_url,
            "num_paginas": num_pages,
            "ects_detectados": parsed_ects,
            "ects_exigidos": req_ects,
            "diagnostico": diag
        })

    except Exception as e:
        pdf_diagnostics[f"Error al descargar/examinar: {str(e)[:40]}"] += 1
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

print("\n=======================================================================")
print("  RESULTADOS DEL DIAGNÓSTICO FORENSE DE PDFs DEL BOE")
print("=======================================================================")
for diag, count in pdf_diagnostics.items():
    print(f"  [{count} PDFs] -> {diag}")

print("\nDetalle de casos examinados:")
for d in details[:10]:
    print(f" -> [{d['codigo']}] ({d['univ']}) {d['titulo']} | Pags: {d['num_paginas']} | ECTS: {d['ects_detectados']}/{d['ects_exigidos']} | {d['diagnostico']}")
