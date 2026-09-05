import os
import json
import glob
import re
import logging
from core.config import (
    DATA_DIR,
    PLANES_DIR,
    UNIVERSIDADES_JSON,
    PRECIOS_CCAA_JSON,
    DOCTORATE_TUTELA_CREDITS,
    STANDARD_YEAR_ECTS_CREDITS,
    TARGET_UNIVERSITY_CODES,
)
from core.checkpoint import atomic_json_dump, load_json_safe
from pipelines.common import iter_plan_files
from core.cancellation import raise_if_shutdown_requested

PRICE_CATALOG_ACADEMIC_YEAR = os.getenv("CRAWLER_PRICE_CATALOG_ACADEMIC_YEAR", "2025-2026")
# Un catálogo embebido en el código no es evidencia primaria por sí mismo.
# Solo se permite aplicarlo cuando la ejecución lo autoriza explícitamente.
PRICE_CATALOG_VERIFIED = os.getenv("CRAWLER_PRICE_CATALOG_VERIFIED", "false").strip().lower() in {"1", "true", "yes", "si", "sí"}
logger = logging.getLogger(__name__)


from lexicon.pricing_tables import (
    OFFICIAL_SIIU_PRICES_CATALOG,
    OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG,
    normalize_ccaa_name,
    is_public_university,
    is_verified_academic_year,
    is_price_catalog_publishable,
)


def apply_price_info_to_degree(degree_dict: dict, price_info: dict, tipo_univ: str) -> bool:
    """Aplica de forma consistente los precios ECTS y retorna True si hubo modificaciones reales."""
    changed = False
    for k in ["precio_credito_ects", "precio_credito_2", "precio_credito_3", "precio_credito_4", "precio_estimado_anual", "fuente_precio"]:
        new_v = price_info.get(k)
        if new_v is None and degree_dict.get(k) not in (None, "", "null"):
            # Una CCAA desconocida o un fallo temporal no debe borrar el último dato válido.
            continue
        if degree_dict.get(k) != new_v:
            degree_dict[k] = new_v
            changed = True
    provenance = price_info.get("proveniencia_precio")
    if provenance is not None and degree_dict.get("proveniencia_precio") != provenance:
        degree_dict["proveniencia_precio"] = provenance
        changed = True
    return changed


def load_precios_ccaa() -> dict:
    """Carga el catálogo local de precios por CCAA combinando el archivo persistido con el catálogo base oficial."""
    catalog = load_json_safe(PRECIOS_CCAA_JSON, default={})
    merged = dict(OFFICIAL_SIIU_PRICES_CATALOG)
    if isinstance(catalog, dict) and catalog:
        for ccaa_key, ccaa_val in catalog.items():
            if ccaa_key in merged and isinstance(ccaa_val, dict) and isinstance(merged[ccaa_key], dict):
                merged_ccaa = dict(merged[ccaa_key])
                merged_ccaa.update(ccaa_val)
                merged[ccaa_key] = merged_ccaa
            else:
                merged[ccaa_key] = ccaa_val
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        atomic_json_dump(merged, PRECIOS_CCAA_JSON)
    except OSError as error:
        logger.warning("No se pudo persistir el catálogo local de precios: %s", error)
    return merged


def load_universidades_map() -> dict:
    univ_map = {}
    data = load_json_safe(UNIVERSIDADES_JSON, default=[])
    if not isinstance(data, list):
        logger.warning("El catálogo de universidades no tiene formato de lista; no se cargarán precios por CCAA.")
        return univ_map
    for u in data:
        if not isinstance(u, dict):
            continue
        code = u.get("codigo")
        if code:
            code_str = str(code).strip()
            univ_map[code_str] = u
            univ_map[code_str.zfill(3)] = u
    return univ_map


def classify_degree_experimental_tier(titulo: str) -> str:
    """Clasifica el grado en una de las tres categorías de experimentalidad oficial:
    - Grado - Salud: Nivel 1 (Medicina, Enfermería, Veterinaria, Odontología, Farmacia...)
    - Grado - Ciencias e Ingeniería: Nivel 2 (Ingenierías, Arquitectura, Física, Química, Biología, Informática...)
    - Grado - Ciencias Sociales y Humanidades: Nivel 3 (Derecho, ADE, Historia, Filología, Educación...)
    """
    t = (titulo or "").lower()
    if any(k in t for k in [
        "medicina", "enfermería", "enfermeria", "infermeria", "odontología", "odontologia",
        "veterinaria", "farmacia", "fisioterapia", "podología", "podologia",
        "biomedicina", "ciencias biomédicas", "ciències biomèdiques", "nutrición", "nutricio"
    ]):
        return "Grado - Salud"
    if any(k in t for k in [
        "ingeniería", "ingenieria", "enginyeria", "enxeñaría", "ingeniaritza", "engineering",
        "informática", "informatica", "informàtica", "software", "computadores", "datos", "data",
        "química", "quimica", "física", "fisica", "biología", "biologia", "biotecnología", "biotecnologia",
        "matemáticas", "matematicas", "matemàtiques", "geología", "geologia", "arquitectura", "biomédica",
        "telecomunicación", "telecomunicació", "telecomunicaciones", "aeroespacial", "naval", "mecánica", "mecanica", "eléctrica", "electrica", "industrial"
    ]):
        return "Grado - Ciencias e Ingeniería"
    return "Grado - Ciencias Sociales y Humanidades"


def compute_degree_price(
    ccaa: str,
    tipo_univ: str,
    nivel_academico: str,
    titulo: str,
    precios_catalogo: dict = None,
    univ_codigo: str = None,
    univ_nombre: str = None,
) -> dict:
    """Calcula una estimación a partir del catálogo local configurado por CCAA (públicas) o tarifarios institucionales (privadas).

    El año académico y la vigencia deben verificarse fuera de este módulo.
    """
    if not is_public_university(tipo_univ):
        # 1. Búsqueda en catálogo de universidades privadas por código o nombre
        u_code_norm = str(univ_codigo or "").zfill(3)
        priv_entry = OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG.get(u_code_norm)
        if not priv_entry and univ_nombre:
            u_nom_low = univ_nombre.lower()
            for code, data in OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG.items():
                if data.get("nombre", "").lower() in u_nom_low or u_nom_low in data.get("nombre", "").lower():
                    priv_entry = data
                    break

        if priv_entry:
            nivel_lower = (nivel_academico or "").lower()
            titulo_lower = (titulo or "").lower()

            if "doctorado" in nivel_lower or "doctor" in titulo_lower:
                tarifa = priv_entry.get("Doctorado")
            elif any(marker in nivel_lower or marker in titulo_lower for marker in ("máster", "master", "màster", "m�ster", "mster", "posgrado", "postgrado")):
                tarifa = priv_entry.get("Máster Habilitante") if any(h in titulo_lower for h in ["profesorado", "abogacía", "ingeniería"]) else (priv_entry.get("Máster No Habilitante") or priv_entry.get("Máster"))
            else:
                exp_tier = classify_degree_experimental_tier(titulo)
                tarifa = priv_entry.get(exp_tier) or priv_entry.get("Grado")

            if isinstance(tarifa, dict):
                p_ects = tarifa.get("precio_credito_ects")
                p_anual = tarifa.get("precio_estimado_anual") or (round(p_ects * 60, 2) if p_ects else None)
                fuente = priv_entry.get("fuente") or f"Tarifario Oficial Institución Privada - {priv_entry.get('nombre', 'Universidad Privada')}"
                return {
                    "precio_credito_ects": p_ects,
                    "precio_credito_2": p_ects,
                    "precio_credito_3": p_ects,
                    "precio_credito_4": p_ects,
                    "precio_estimado_anual": p_anual,
                    "fuente_precio": fuente,
                    "proveniencia_precio": {
                        "curso_academico": PRICE_CATALOG_ACADEMIC_YEAR,
                        "tipo": "tarifario_privado_embebido",
                        "verificado": PRICE_CATALOG_VERIFIED,
                        "url": priv_entry.get("fuente_url"),
                        "es_estimacion": True,
                    }
                }

        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Universidad Privada ({univ_nombre or 'Tarifas fijadas por la institución'} - Consultar con la institución)",
            "proveniencia_precio": {
                "curso_academico": PRICE_CATALOG_ACADEMIC_YEAR,
                "tipo": "sin_tarifario_verificado",
                "verificado": False,
                "url": None,
                "es_estimacion": True,
            }
        }
        
    if precios_catalogo is None:
        precios_catalogo = load_precios_ccaa()

    canonical_ccaa = normalize_ccaa_name(ccaa)
    ccaa_data = precios_catalogo.get(canonical_ccaa)
    
    if not ccaa_data and canonical_ccaa:
        # Búsqueda difusa por nombre de CCAA
        for k, v in precios_catalogo.items():
            if k.lower() in canonical_ccaa.lower() or canonical_ccaa.lower() in k.lower():
                ccaa_data = v
                canonical_ccaa = k
                break
                
    if not ccaa_data:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"CCAA desconocida o no registrada ({ccaa or 'Sin CCAA'})"
        }

    nivel_lower = (nivel_academico or "").lower()
    titulo_lower = (titulo or "").lower()
    
    # Determinar categoría académica oficial
    if "doctorado" in nivel_lower or "doctor" in titulo_lower:
        cat = "Doctorado"
        cat_prices = ccaa_data.get(cat)
    elif any(marker in nivel_lower or marker in titulo_lower for marker in ("máster", "master", "màster", "m�ster", "mster", "posgrado", "postgrado")):
        # Másteres que habilitan para el ejercicio de profesiones reguladas en España (soporte multilingüe ES, CA, GL, EU)
        habilitantes = [
            "abogacía", "abogacia", "advocacia", "advocacia i procura", "procura",
            "profesorado", "profesor", "secundaria", "formació del professorat", "formacion del profesorado", "formacion do profesorado", "irakasleen prestakuntza",
            "ingeniería de caminos", "enginyeria de camins", "enxeñaría de camiños",
            "ingeniería industrial", "enginyeria industrial", "enxeñaría industrial", "industria ingeniaritza",
            "ingeniería de telecomunicación", "enginyeria de telecomunicació", "enxeñaría de telecomunicación", "telekomunikazio ingeniaritza",
            "ingeniería aeronáutica", "enginyeria aeronàutica", "enxeñaría aeronáutica", "aeronautika ingeniaritza",
            "ingeniería agronómica", "enginyeria agronòmica", "enxeñaría agronómica", "nekazaritza ingeniaritza",
            "ingeniería naval", "enginyeria naval", "enxeñaría naval",
            "ingeniería de montes", "enginyeria de forests", "enxeñaría de montes",
            "ingeniería de minas", "enginyeria de mines", "enxeñaría de minas",
            "arquitectura", "arkitektura",
            "psicología general sanitaria", "psicologia general sanitaria", "psicologia general sanitària", "osasun psikologia orokorra",
            "náutica y transporte marítimo", "nautica y transporte maritimo", "nàutica i transport marítim", "gestión y planificación portuaria", "marina mercante",
            "ingeniería química", "enginyeria química", "enxeñaría química", "ingenieria quimica"
        ]
        if any(h in titulo_lower for h in habilitantes):
            cat = "Máster Habilitante"
        else:
            cat = "Máster No Habilitante"
        cat_prices = ccaa_data.get(cat)
    else:
        cat = "Grado"
        exp_tier = classify_degree_experimental_tier(titulo)
        cat_prices = ccaa_data.get(exp_tier) or ccaa_data.get(cat)
        
    if not cat_prices:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Categoría {cat} no registrada en decreto de {canonical_ccaa}"
        }

    if isinstance(cat_prices, dict):
        precio_ects = cat_prices.get("1") or cat_prices.get("defecto")
        precio_2 = cat_prices.get("2")
        precio_3 = cat_prices.get("3")
        precio_4 = cat_prices.get("4")
    else:
        precio_ects = cat_prices
        precio_2 = None
        precio_3 = None
        precio_4 = None

    if precio_ects is None:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Precio no disponible en decreto de {canonical_ccaa}"
        }

    try:
        precio_ects = float(precio_ects)
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_ects malformado en catálogo: {precio_ects}")
        precio_ects = None

    if precio_ects is None or precio_ects <= 0:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Precio por ECTS inválido en el catálogo de {canonical_ccaa}",
        }

    try:
        precio_2 = float(precio_2) if precio_2 is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_2 malformado en catálogo: {precio_2}")
        precio_2 = None

    try:
        precio_3 = float(precio_3) if precio_3 is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_3 malformado en catálogo: {precio_3}")
        precio_3 = None

    try:
        precio_4 = float(precio_4) if precio_4 is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_4 malformado en catálogo: {precio_4}")
        precio_4 = None
        
    try:
        tasas_admin = float(ccaa_data.get("tasas_admin", 0.0))
    except (ValueError, TypeError):
        logger.warning("Tasa administrativa malformada en el catálogo de %s", canonical_ccaa)
        tasas_admin = 0.0
    decreto_fuente = ccaa_data.get("decreto_oficial", f"Decreto de Precios Públicos de {canonical_ccaa}")
    
    # Para Doctorado la matrícula anual es la tutela académica (~100-400€)
    if cat == "Doctorado":
        precio_anual = round(precio_ects + tasas_admin, 2)
    else:
        precio_anual = round(STANDARD_YEAR_ECTS_CREDITS * precio_ects + tasas_admin, 2)
        
    return {
        "precio_credito_ects": round(precio_ects, 2),
        "precio_credito_2": round(precio_2, 2) if precio_2 is not None else None,
        "precio_credito_3": round(precio_3, 2) if precio_3 is not None else None,
        "precio_credito_4": round(precio_4, 2) if precio_4 is not None else None,
        "precio_estimado_anual": round(precio_anual, 2),
        "fuente_precio": (
            f"Catálogo local SIIU ({PRICE_CATALOG_ACADEMIC_YEAR}) / {decreto_fuente}; "
            "verificar vigencia"
        ),
        "proveniencia_precio": {
            "curso_academico": PRICE_CATALOG_ACADEMIC_YEAR,
            "tipo": "catalogo_autonomico_embebido",
            "verificado": PRICE_CATALOG_VERIFIED,
            "url": ccaa_data.get("decreto_url"),
            "experimentalidad": cat,
            "es_estimacion": True,
        },
    }


def run_phase1_part3(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
    degree_title_filter: str | None = None,
    target_universities: list[str] | set[str] | None = None,
) -> dict:
    """
    Fase 1 - Parte 3: Asigna tarifas catalogadas y estima las matrículas
    anuales de las titulaciones de universidades públicas.
    """
    print("\n======================================================================")
    print("      FASE 1 - PARTE 3: CÁLCULO DE PRECIOS ECTS DE MATRÍCULA PÚBLICA")
    print("======================================================================")

    if not is_price_catalog_publishable(PRICE_CATALOG_ACADEMIC_YEAR, PRICE_CATALOG_VERIFIED):
        print(" [AVISO PARTE 3] Catálogo de precios sin curso y verificación explícita; no se publican importes.")
        return {
            "status": "skipped",
            "reason": "unverified_price_catalog",
            "academic_year": PRICE_CATALOG_ACADEMIC_YEAR,
            "verified": PRICE_CATALOG_VERIFIED,
        }
    
    precios_catalogo = load_precios_ccaa()
    univ_map = load_universidades_map()
    json_files = iter_plan_files(PLANES_DIR)

    selected_files = []
    selected_universities = []
    degrees_per_university = {}
    effective_targets = {str(c).zfill(3) for c in (target_universities or TARGET_UNIVERSITY_CODES or [])}
    for filepath in json_files:
        degree = load_json_safe(filepath, default={}) or {}
        if degree_title_filter:
            from pipelines.common import matches_degree_title
            if not matches_degree_title(degree.get("titulo"), degree_title_filter):
                continue
        u_code = str(degree.get("universidad_codigo") or os.path.basename(os.path.dirname(filepath))).strip().zfill(3)
        if effective_targets and u_code not in effective_targets:
            continue
        if u_code not in degrees_per_university:
            if limit_universities is not None and len(selected_universities) >= max(0, limit_universities):
                continue
            selected_universities.append(u_code)
            degrees_per_university[u_code] = 0
        if limit_degrees is not None and degrees_per_university[u_code] >= max(0, limit_degrees):
            continue
        degrees_per_university[u_code] += 1
        selected_files.append(filepath)
    
    updated_count = 0
    public_count = 0
    prices_cache = {}
    processing_errors = 0
    
    for position, filepath in enumerate(selected_files, start=1):
        raise_if_shutdown_requested()
        try:
            degree = load_json_safe(filepath, default={}) or {}
            d_code = degree.get("codigo_estudio") or os.path.splitext(os.path.basename(filepath))[0]
                
            u_code = str(degree.get("universidad_codigo") or os.path.basename(os.path.dirname(filepath))).strip().zfill(3)
            univ = univ_map.get(u_code, {})
            
            ccaa = univ.get("comunidad_autonoma") or degree.get("comunidad_autonoma") or ""
            tipo_univ = univ.get("tipo") or degree.get("tipo") or ""
            nivel = degree.get("nivel_academico", "")
            titulo = degree.get("titulo", "")
            
            univ_nombre = univ.get("nombre") or degree.get("universidad_nombre") or ""
            price_info = compute_degree_price(
                ccaa,
                tipo_univ,
                nivel,
                titulo,
                precios_catalogo=precios_catalogo,
                univ_codigo=u_code,
                univ_nombre=univ_nombre,
            )
            prices_cache[d_code] = (price_info, tipo_univ)
            
            changed = apply_price_info_to_degree(degree, price_info, tipo_univ)
            if changed:
                atomic_json_dump(degree, filepath)
                updated_count += 1
            
            if price_info.get("precio_credito_ects") is not None:
                public_count += 1
            if progress_emitter is not None:
                progress_emitter.update_degree(
                    position,
                    len(selected_files),
                    str(d_code),
                    degree.get("titulo", ""),
                    "Precio actualizado" if changed else "Sin cambios",
                )
        except Exception as e:
            processing_errors += 1
            print(f" [AVISO] Error al procesar precio de '{filepath}': {e}")

    # También actualizar titulaciones_universidad.json
    tit_json_path = os.path.join(DATA_DIR, "titulaciones_universidad.json")
    catalog_update_failed = False
    if os.path.exists(tit_json_path):
        try:
            tit_data = load_json_safe(tit_json_path)
                
            if isinstance(tit_data, dict):
                items_to_iter = tit_data.items()
            elif isinstance(tit_data, list):
                items_to_iter = [(u.get("codigo", ""), u) for u in tit_data if isinstance(u, dict)]
            else:
                items_to_iter = []
                
            for u_code, u_info in items_to_iter:
                if not isinstance(u_info, dict):
                    continue
                univ = univ_map.get(u_code, {})
                ccaa = univ.get("comunidad_autonoma") or ""
                tipo_univ = univ.get("tipo") or ""
                univ_nombre = univ.get("nombre") or ""
                
                for t in u_info.get("titulaciones_vigentes", []):
                    t_code = t.get("codigo_estudio") or t.get("codigo")
                    if t_code in prices_cache:
                        price_info, t_tipo = prices_cache[t_code]
                    elif limit_universities is not None or limit_degrees is not None:
                        continue
                    else:
                        price_info = compute_degree_price(
                            ccaa,
                            tipo_univ,
                            t.get("nivel_academico", ""),
                            t.get("titulo", ""),
                            precios_catalogo=precios_catalogo,
                            univ_codigo=u_code,
                            univ_nombre=univ_nombre,
                        )
                        t_tipo = tipo_univ
                        
                    apply_price_info_to_degree(t, price_info, t_tipo)
                    
            atomic_json_dump(tit_data, tit_json_path)
            print(" -> 'titulaciones_universidad.json' actualizado con precios ECTS.")
        except Exception as e:
            catalog_update_failed = True
            print(f" [AVISO] Error al actualizar titulaciones_universidad.json: {e}")
            
    print(f" -> Titulaciones en planes_estudio actualizadas: {updated_count}")
    print(f" -> Titulaciones Públicas con Tarifa Oficial SIIU: {public_count}")
    print("======================================================================\n")

    return {
        "status": "partial" if processing_errors or catalog_update_failed else "completed",
        "plans_inspected": len(selected_files),
        "plans_updated": updated_count,
        "public_degrees_priced": public_count,
        "errors": processing_errors + int(catalog_update_failed),
    }


if __name__ == "__main__":
    run_phase1_part3()
