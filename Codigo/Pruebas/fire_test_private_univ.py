import sys
import os
import json

# Append Crawler directory
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "d:", "Proyecto", "Codigo", "Crawler"))
sys.path.append("Codigo/Crawler")

from config import UNIVERSIDADES_JSON, TITULACIONES_JSON, PLANES_DIR
from univ_web_crawler import UniversityWebCrawler

def setup_private_univ_data():
    """Configura CUNEF Universidad (089) en los JSONs de prueba para la prueba de fuego."""
    univ_cunef = {
        "codigo": "089",
        "nombre": "CUNEF Universidad",
        "tipo": "Privada",
        "comunidad_autonoma": "Comunidad de Madrid",
        "municipio": "Madrid",
        "provincia": "Madrid",
        "web": "www.cunef.edu",
        "email": "info@cunef.edu",
        "telefono": "91 448 08 92"
    }

    degrees_cunef = [
        {
            "codigo_estudio": "2504059",
            "titulo": "Graduado o Graduada en Administración y Dirección de Empresas por la CUNEF Universidad",
            "nivel_academico": "Grado - RD 822/2021 (2)",
            "estado": "Publicado en B.O.E."
        },
        {
            "codigo_estudio": "2504639",
            "titulo": "Graduado o Graduada en Ciencia de Datos / Bachelor in Data Science por la CUNEF Universidad",
            "nivel_academico": "Grado - RD 822/2021 (2)",
            "estado": "Publicado en B.O.E."
        },
        {
            "codigo_estudio": "4317230",
            "titulo": "Máster Universitario en Ciencia de Datos e Inteligencia Artificial por la CUNEF Universidad",
            "nivel_academico": "Máster - RD 822/2021 (3)",
            "estado": "Publicado en B.O.E."
        }
    ]

    # Load existing universities
    univs = []
    if os.path.exists(UNIVERSIDADES_JSON):
        with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
            univs = json.load(f)

    # Add CUNEF if not present
    if not any(u.get("codigo") == "089" for u in univs):
        univs.append(univ_cunef)
        with open(UNIVERSIDADES_JSON, "w", encoding="utf-8") as f:
            json.dump(univs, f, ensure_ascii=False, indent=2)

    # Load existing degrees
    degs_dict = {}
    if os.path.exists(TITULACIONES_JSON):
        with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
            degs_dict = json.load(f)

    degs_dict["089"] = {
        "universidad": univ_cunef,
        "total_titulaciones_vigentes": len(degrees_cunef),
        "titulaciones_vigentes": degrees_cunef
    }

    with open(TITULACIONES_JSON, "w", encoding="utf-8") as f:
        json.dump(degs_dict, f, ensure_ascii=False, indent=2)

    print(" [SETUP PRUEBA FUEGO PRIVADA] CUNEF Universidad (089) configurada correctamente.")
    return univ_cunef, degs_dict

def main():
    univ_data, degs_dict = setup_private_univ_data()

    # Clear previous plan files for CUNEF degrees to force fresh crawl
    for code in ["2504059", "2504639", "4317230"]:
        plan_path = os.path.join(PLANES_DIR, f"{code}.json")
        if os.path.exists(plan_path):
            os.remove(plan_path)

    print("\n" + "=" * 70)
    print("  EJECUTANDO PRUEBA DE FUEGO FASE 1 PARTE 2: UNIVERSIDAD PRIVADA (089 - CUNEF)")
    print("======================================================================\n")

    crawler = UniversityWebCrawler()
    stats = crawler.process_university_web(univ_data, degs_dict)

    print("\n" + "=" * 70)
    print("      RESULTADOS DE LA PRUEBA DE FUEGO PRIVADA (CUNEF UNIVERSIDAD)")
    print("======================================================================")
    print(f" -> Código Universidad:                 {stats['u_code']}")
    print(f" -> Nombre Universidad:                 {stats['u_name']}")
    print(f" -> Dispone de Web Oficial:             {stats['has_web']}")
    print(f" -> Permiso en robots.txt:              {stats['robots_allowed']}")
    print(f" -> Titulaciones sin plan iniciales:    {stats['missing_degrees_count']}")
    print(f" -> Titulaciones resueltas desde web:   {stats['resolved_degrees_count']}")

    # Show harvested JSON payloads
    payloads = []
    for code in ["2504059", "2504639", "4317230"]:
        plan_path = os.path.join(PLANES_DIR, f"{code}.json")
        if os.path.exists(plan_path):
            with open(plan_path, "r", encoding="utf-8") as pf:
                data = json.load(pf)
                payloads.append({
                    "codigo": code,
                    "titulo": data.get("titulo"),
                    "origen": data.get("origen_fuente"),
                    "url_fuente": data.get("web_fuente_directa_url"),
                    "precio_credito_ects": data.get("precio_credito_ects"),
                    "precio_estimado_anual": data.get("precio_estimado_anual"),
                    "fuente_precio": data.get("fuente_precio"),
                    "total_elementos": data.get("plan_estudios", {}).get("total_elementos", 0)
                })

    print("\n -> Muestra de Datos y Precios Recolectados de la Web Oficial de CUNEF:")
    print(json.dumps(payloads, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
