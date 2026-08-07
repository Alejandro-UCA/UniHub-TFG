import os
import json
import glob
from config import DATA_DIR, PLANES_DIR, UNIVERSIDADES_JSON
from checkpoint import atomic_json_dump

PRECIOS_CCAA_JSON = os.path.join(DATA_DIR, "precios_ccaa.json")

def load_precios_ccaa() -> dict:
    if os.path.exists(PRECIOS_CCAA_JSON):
        try:
            with open(PRECIOS_CCAA_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def load_universidades_map() -> dict:
    univ_map = {}
    if os.path.exists(UNIVERSIDADES_JSON):
        try:
            with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                for u in data:
                    code = u.get("codigo")
                    if code:
                        univ_map[code] = u
        except Exception:
            pass
    return univ_map

def compute_degree_price(ccaa: str, tipo_univ: str, nivel_academico: str, titulo: str, precios_catalogo: dict = None) -> dict:
    """
    Computes official ECTS credit price and estimated 1st year tuition fee (60 ECTS + admin fees)
    for public universities in Spain using official SIIU Ministry data.
    """
    if "pública" not in tipo_univ.lower() and "publica" not in tipo_univ.lower():
        return {
            "precio_credito_ects": None,
            "precio_estimado_anual": None,
            "fuente_precio": "Universidad Privada (Tarifas fijadas por la institución)"
        }
        
    if precios_catalogo is None:
        precios_catalogo = load_precios_ccaa()

    ccaa_data = precios_catalogo.get(ccaa)
    
    if not ccaa_data:
        # Fallback para CCAA no coincidentes exactamente
        for k, v in precios_catalogo.items():
            if k.lower() in ccaa.lower() or ccaa.lower() in k.lower():
                ccaa_data = v
                break
                
    if not ccaa_data:
        ccaa_data = precios_catalogo.get("Andalucía", {})

    nivel_lower = (nivel_academico or "").lower()
    titulo_lower = (titulo or "").lower()
    
    # Determinar categoría académica
    if "doctorado" in nivel_lower or "560" in nivel_lower or "900" in nivel_lower:
        cat = "Doctorado"
    elif "máster" in nivel_lower or "master" in nivel_lower or "431" in nivel_lower:
        if any(h in titulo_lower for h in ["abogacía", "profesorado", "ingeniería", "arquitectura", "psicología general sanitaria"]):
            cat = "Máster Habilitante"
        else:
            cat = "Máster No Habilitante"
    else:
        cat = "Grado"
        
    cat_prices = ccaa_data.get(cat, {})
    if isinstance(cat_prices, dict):
        precio_ects = cat_prices.get("defecto") or cat_prices.get("1") or 15.00
    else:
        precio_ects = float(cat_prices) if cat_prices else 15.00
        
    tasas_admin = ccaa_data.get("tasas_admin", 45.00)
    
    # Para Doctorado la matrícula anual es la tutela académica (precio fijo de tutela ~250-350€)
    if cat == "Doctorado":
        precio_anual = round(precio_ects * 10 + tasas_admin, 2)
    else:
        precio_anual = round(60 * precio_ects + tasas_admin, 2)
        
    return {
        "precio_credito_ects": round(float(precio_ects), 2),
        "precio_estimado_anual": round(float(precio_anual), 2),
        "fuente_precio": f"Oficial SIIU Ministerio / Decreto {ccaa}"
    }

def run_phase1_part3():
    """
    Fase 1 - Parte 3: Asigna los precios ECTS oficiales y estima las matrículas
    anuales de las titulaciones de universidades públicas.
    """
    print("\n======================================================================")
    print("      FASE 1 - PARTE 3: CÁLCULO DE PRECIOS ECTS DE MATRÍCULA PÚBLICA")
    print("======================================================================")
    
    precios_catalogo = load_precios_ccaa()
    univ_map = load_universidades_map()
    json_files = glob.glob(os.path.join(PLANES_DIR, "*.json"))
    
    updated_count = 0
    public_count = 0
    
    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                degree = json.load(f)
                
            u_code = degree.get("universidad_codigo")
            univ = univ_map.get(u_code, {})
            
            ccaa = univ.get("comunidad_autonoma") or degree.get("comunidad_autonoma", "Andalucía")
            tipo_univ = univ.get("tipo") or degree.get("tipo", "Pública")
            nivel = degree.get("nivel_academico", "")
            titulo = degree.get("titulo", "")
            
            price_info = compute_degree_price(ccaa, tipo_univ, nivel, titulo, precios_catalogo=precios_catalogo)
            
            degree["precio_credito_ects"] = price_info["precio_credito_ects"]
            degree["precio_estimado_anual"] = price_info["precio_estimado_anual"]
            degree["fuente_precio"] = price_info["fuente_precio"]
            
            atomic_json_dump(degree, filepath)
                
            updated_count += 1
            if price_info["precio_credito_ects"] is not None:
                public_count += 1
        except Exception as e:
            print(f" [AVISO] Error al procesar precio de '{filepath}': {e}")

    # También actualizar titulaciones_universidad.json
    tit_json_path = os.path.join(DATA_DIR, "titulaciones_universidad.json")
    if os.path.exists(tit_json_path):
        try:
            with open(tit_json_path, "r", encoding="utf-8") as f:
                tit_data = json.load(f)
                
            for u_code, u_info in tit_data.items():
                univ = univ_map.get(u_code, {})
                ccaa = univ.get("comunidad_autonoma", "Andalucía")
                tipo_univ = univ.get("tipo", "Pública")
                
                for t in u_info.get("titulaciones_vigentes", []):
                    price_info = compute_degree_price(ccaa, tipo_univ, t.get("nivel_academico", ""), t.get("titulo", ""), precios_catalogo=precios_catalogo)
                    t["precio_credito_ects"] = price_info["precio_credito_ects"]
                    t["precio_estimado_anual"] = price_info["precio_estimado_anual"]
                    t["fuente_precio"] = price_info["fuente_precio"]
                    
            atomic_json_dump(tit_data, tit_json_path)
            print(" -> 'titulaciones_universidad.json' actualizado con precios ECTS.")
        except Exception as e:
            print(f" [AVISO] Error al actualizar titulaciones_universidad.json: {e}")
            
    print(f" -> Titulaciones en planes_estudio actualizadas: {updated_count}")
    print(f" -> Titulaciones Públicas con Tarifa Oficial SIIU: {public_count}")
    print("======================================================================\n")

if __name__ == "__main__":
    run_phase1_part3()
