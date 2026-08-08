import sys
import os
import json

sys.path.append("Codigo/Crawler")

from config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    URL_UNIVERSIDADES_LIST,
    URL_ESTUDIOS_UNIV_TEMPLATE
)
from downloader import RUCTDownloader
from parsers import parse_universities_xls, parse_degrees_xls
from checkpoint import atomic_json_dump, CheckpointManager
from univ_web_crawler import UniversityWebCrawler

print("=" * 70)
print("      PRUEBA DE FUEGO LIMPIA FASE 1 PARTE 2: UNIVERSIDAD DE CÁDIZ")
print("======================================================================")

# 1. Obtener Universidad de Cádiz
downloader = RUCTDownloader()
univ_file = os.path.join(TEMP_PDF_DIR, "universidades_list.xls")
downloader.download_file(URL_UNIVERSIDADES_LIST, univ_file)
all_univs = parse_universities_xls(univ_file)

uca_univ = [u for u in all_univs if "cádiz" in u["nombre"].lower() or "cadiz" in u["nombre"].lower()][0]
print(f" -> Universidad objetivo: [{uca_univ['codigo']}] {uca_univ['nombre']}")
print(f" -> Web oficial:          {uca_univ.get('web')}")

atomic_json_dump([uca_univ], UNIVERSIDADES_JSON)

# 2. Descargar catálogo de titulaciones de la UCA
u_code = uca_univ["codigo"]
degrees_url = URL_ESTUDIOS_UNIV_TEMPLATE.format(codigo_universidad=u_code)
degrees_file = os.path.join(TEMP_PDF_DIR, f"degrees_{u_code}.xls")
downloader.download_file(degrees_url, degrees_file)

active_degrees = parse_degrees_xls(degrees_file)

# LIMPIAR ARCHIVOS EXISTENTES PARA FORZAR PRUEBA DE FUEGO DESDE CERO
for deg in active_degrees:
    plan_file = os.path.join(PLANES_DIR, f"{deg['codigo_estudio']}.json")
    if os.path.exists(plan_file):
        os.remove(plan_file)

titulaciones_dict = {
    u_code: {
        "universidad_nombre": uca_univ["nombre"],
        "titulaciones_vigentes": active_degrees
    }
}
atomic_json_dump(titulaciones_dict, TITULACIONES_JSON)
print(f" -> Titulaciones vigentes obtenidas de la UCA: {len(active_degrees)}")
print(" -> Archivos de plan de estudios en disco limpiados para la prueba de fuego.")

# 3. Ejecutar prueba de fuego de la Fase 1 Parte 2
crawler = UniversityWebCrawler()
stats = crawler.process_university_web(uca_univ, titulaciones_dict)

print("\n" + "=" * 70)
print("      RESULTADOS DE LA PRUEBA DE FUEGO (UNIVERSIDAD DE CÁDIZ)")
print("======================================================================")
print(f" -> Código Universidad:                 {stats['u_code']}")
print(f" -> Nombre Universidad:                 {stats['u_name']}")
print(f" -> Dispone de Web Oficial:             {stats['has_web']}")
print(f" -> Permiso en robots.txt:              {stats['robots_allowed']}")
print(f" -> Titulaciones sin plan iniciales:    {stats['missing_degrees_count']}")
print(f" -> Titulaciones resueltas desde web:   {stats['resolved_degrees_count']}")

# Muestreo de titulaciones procesadas / extraídas desde la web oficial
resolved_details = []
for deg in active_degrees:
    d_code = deg["codigo_estudio"]
    plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
    if os.path.exists(plan_file):
        with open(plan_file, "r", encoding="utf-8") as f:
            d_data = json.load(f)
            plan = d_data.get("plan_estudios", {})
            if plan and plan.get("total_elementos", 0) > 0:
                resolved_details.append({
                    "codigo": d_code,
                    "titulo": deg["titulo"],
                    "origen": d_data.get("origen_fuente"),
                    "url_fuente": d_data.get("web_fuente_directa_url"),
                    "total_elementos": plan.get("total_elementos", 0),
                    "primeras_asignaturas": [elem.get("nombre_elemento") for elem in plan.get("elementos_curriculares", [])[:5]]
                })

print(f"\n -> Total de titulaciones completadas con plan de estudios: {len(resolved_details)}")
print("\n -> Muestra de Planes de Estudio Obtenidos desde la Web Oficial de la UCA:")
print(json.dumps(resolved_details[:5], ensure_ascii=False, indent=2))
