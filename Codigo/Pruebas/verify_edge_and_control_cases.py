import sys
import os
import json

sys.path.append('d:/Proyecto/Codigo/Crawler')
from pipelines.parte2_web_crawler import UniversityWebCrawler
from core.downloader import RUCTDownloader

crawler = UniversityWebCrawler()

test_cases = [
    # --- Casos que daban fallos / falsos positivos ---
    {
        "label": "FALLO 1: UBU Cookies (1500375)",
        "univ": {"codigo": "051", "nombre": "Universidad de Burgos", "web": "https://www.ubu.es"},
        "degree": {"codigo_estudio": "1500375", "titulo": "Graduado o Graduada en Matemática Aplicada y Computación por la Universidad de Burgos", "nivel_academico": "Grado - RD 822/2021 (2)"},
        "expect_no_cookies": True
    },
    {
        "label": "FALLO 2: UniRioja Baremo Notas (2500849)",
        "univ": {"codigo": "045", "nombre": "Universidad de La Rioja", "web": "https://www.unirioja.es"},
        "degree": {"codigo_estudio": "2500849", "titulo": "Graduado o Graduada en Ingeniería Informática por la Universidad de La Rioja", "nivel_academico": "Grado - RD 1393/2007 (1)"},
        "expect_no_grade_scale": True
    },
    {
        "label": "FALLO 3: UAM Reconocimiento Actividades (2500772)",
        "univ": {"codigo": "023", "nombre": "Universidad Autónoma de Madrid", "web": "https://www.uam.es"},
        "degree": {"codigo_estudio": "2500772", "titulo": "Graduado o Graduada en Estudios Hispánicos: Lengua Española y sus Literaturas por la Universidad Autónoma de Madrid", "nivel_academico": "Grado - RD 1393/2007 (1)"},
        "expect_no_extracurricular": True
    },
    {
        "label": "FALLO 4: UJA Protección de Datos (4310722)",
        "univ": {"codigo": "029", "nombre": "Universidad de Jaén", "web": "https://www.ujaen.es"},
        "degree": {"codigo_estudio": "4310722", "titulo": "Máster Universitario en Dependencia e Igualdad en la Autonomía Personal por la Universidad de Jaén", "nivel_academico": "Máster - RD 1393/2007 (1)"},
        "expect_no_privacy": True
    },
    # --- Caso de control que NO daba fallos (No Regresión) ---
    {
        "label": "CONTROL POSITIVO (Sin Fallos): UCA Grado Informática (2500216)",
        "univ": {"codigo": "025", "nombre": "Universidad de Cádiz", "web": "https://www.uca.es"},
        "degree": {"codigo_estudio": "2500216", "titulo": "Graduado o Graduada en Ingeniería Informática por la Universidad de Cádiz", "nivel_academico": "Grado - RD 1393/2007 (1)"},
        "expect_valid_subjects": True
    }
]

print("=======================================================================")
print("  VERIFICACIÓN RIGUROSA: CASOS PROBLEMÁTICOS vs CASOS DE CONTROL")
print("=======================================================================")

results = []

for tc in test_cases:
    lbl = tc["label"]
    univ = tc["univ"]
    deg = tc["degree"]
    d_code = deg["codigo_estudio"]
    
    print(f"\n>>> Ejecutando: {lbl} ...")
    stats = crawler.process_university_web(univ, [deg])
    
    # Leer el JSON resultante
    plan_path = os.path.join("d:/Proyecto/Codigo/Crawler/Datos/planes_estudio", f"{d_code}.json")
    with open(plan_path, "r", encoding="utf-8") as fp:
        res_json = json.load(fp)
        
    plan = res_json.get("plan_estudios")
    url = res_json.get("web_fuente_directa_url", "")
    
    if tc.get("expect_no_cookies"):
        is_bad = "cookies" in url.lower() if url else False
        if plan and isinstance(plan, dict):
            elems = plan.get("elementos_curriculares", [])
            if any("_ga" in str(e.get("nombre_elemento", "")) or "_fbp" in str(e.get("nombre_elemento", "")) for e in elems):
                is_bad = True
        status = "PASSED (0 cookies detectadas)" if not is_bad else "FAILED (Detectadas cookies)"
        print(f"    Resultado: {status} | URL final: {url}")
        results.append((lbl, not is_bad))
        
    elif tc.get("expect_no_grade_scale"):
        is_bad = "reconocimientos" in url.lower() if url else False
        if plan and isinstance(plan, dict):
            elems = plan.get("elementos_curriculares", [])
            if any("suspenso" in str(e.get("nombre_elemento", "")).lower() or "aprobado" in str(e.get("nombre_elemento", "")).lower() for e in elems):
                is_bad = True
        status = "PASSED (0 baremos de notas detectados)" if not is_bad else "FAILED (Detectado baremo de notas)"
        print(f"    Resultado: {status} | URL final: {url}")
        results.append((lbl, not is_bad))

    elif tc.get("expect_no_extracurricular"):
        is_bad = "reconocimiento-de-creditos" in url.lower() if url else False
        if plan and isinstance(plan, dict):
            elems = plan.get("elementos_curriculares", [])
            if any("coro" in str(e.get("nombre_elemento", "")).lower() or "teatro" in str(e.get("nombre_elemento", "")).lower() for e in elems):
                is_bad = True
        status = "PASSED (0 actividades extracurriculares detectadas)" if not is_bad else "FAILED (Detectadas actividades extracurriculares)"
        print(f"    Resultado: {status} | URL final: {url}")
        results.append((lbl, not is_bad))

    elif tc.get("expect_no_privacy"):
        is_bad = "proteccion-de-datos" in url.lower() if url else False
        if plan and isinstance(plan, dict):
            elems = plan.get("elementos_curriculares", [])
            if any("dpo" in str(e.get("nombre_elemento", "")).lower() or "tratamiento" in str(e.get("nombre_elemento", "")).lower() for e in elems):
                is_bad = True
        status = "PASSED (0 datos DPO/privacidad detectados)" if not is_bad else "FAILED (Detectados datos DPO)"
        print(f"    Resultado: {status} | URL final: {url}")
        results.append((lbl, not is_bad))

    elif tc.get("expect_valid_subjects"):
        has_plan = plan is not None
        elems_count = len(plan.get("elementos_curriculares", [])) if has_plan else 0
        status = f"PASSED ({elems_count} asignaturas curriculares auténticas)" if has_plan and elems_count > 0 else "FAILED (Sin plan)"
        print(f"    Resultado: {status} | URL final: {url}")
        results.append((lbl, has_plan and elems_count > 0))

print("\n=======================================================================")
print("  RESUMEN FINAL DE LA VERIFICACIÓN DE CONTROL")
print("=======================================================================")
all_ok = True
for lbl, ok in results:
    icon = "✅" if ok else "❌"
    print(f"  {icon} {lbl}")
    if not ok:
        all_ok = False

print(f"\nESTADO GLOBAL: {'100% EXITOSO' if all_ok else 'FALLARON PRUEBAS'}")
