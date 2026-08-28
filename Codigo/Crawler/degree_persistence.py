"""
Módulo de persistencia unificada para planes de estudio y metadatos de titulaciones.
Centraliza la serialización atómica en formato JSON, particionado por universidad y actualización de checkpoints.
"""
import os
import logging
from datetime import datetime
from checkpoint import atomic_json_dump
from config import get_plan_filepath, find_plan_filepath
from parsers import detect_academic_language
from data_quality import apply_plan_quality, source_record

logger = logging.getLogger(__name__)

def save_degree_payload(plan_file: str, d_code: str, d_title: str, u_code: str, u_name: str, 
                        nivel_academico: str, boe_url: str = None, boe_fecha: str = None, 
                        plan_estudios: dict = None, all_boe_urls: list = None, 
                        origen_fuente: str = None, checkpoint_mgr=None, existing_data: dict = None,
                        idioma: str = None, source_status: str = None,
                        source_checked_at: str = None):
    """
    Guarda atómicamente el payload JSON del plan de estudios y actualiza el checkpoint del sistema.
    Soporta particionado automático en subcarpeta de universidad y persistencia dual.
    """
    payload = existing_data if existing_data is not None else {}
    now_iso = datetime.now().isoformat()
    
    # Determinar idioma predominante si no viene especificado
    if not idioma:
        if isinstance(plan_estudios, dict) and plan_estudios.get("idioma_predominante"):
            idioma = plan_estudios["idioma_predominante"]
        else:
            idioma = detect_academic_language(d_title)

    payload.update({
        "codigo_estudio": d_code,
        "titulo": d_title,
        "nivel_academico": nivel_academico,
        "universidad_codigo": u_code,
        "universidad_nombre": u_name,
        "idioma_plan": idioma,
        "fecha_procesado": now_iso,
        "boe_url": boe_url if boe_url else payload.get("boe_url"),
        "boe_fecha": boe_fecha if boe_fecha else payload.get("boe_fecha")
    })
    if all_boe_urls:
        payload["all_boe_urls"] = all_boe_urls
    if source_status:
        payload["estado_fuente"] = str(source_status)
    if source_checked_at:
        payload["fecha_ultima_comprobacion_fuente"] = str(source_checked_at)
    if origen_fuente:
        payload["origen_fuente"] = origen_fuente
        source_url = boe_url or payload.get("web_fuente_directa_url")
        if source_url:
            fuentes = payload.setdefault("fuentes", [])
            if not isinstance(fuentes, list):
                fuentes = []
                payload["fuentes"] = fuentes
            record = source_record(
                source_url,
                "BOE" if "boe" in origen_fuente.lower() else origen_fuente.upper(),
                confidence=0.95 if "boe" in origen_fuente.lower() else 0.85,
            )
            fuentes[:] = [item for item in fuentes if item.get("url") != record["url"]]
            fuentes.append(record)

    # La persistencia es el último punto común antes de escribir el JSON:
    # ninguna ruta de RUCT/BOE puede publicar un candidato sin esta evaluación.
    apply_plan_quality(payload, plan_estudios, origen_fuente)

    # Guardar en la ruta destino indicada
    parent_dir = os.path.dirname(os.path.abspath(plan_file))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    atomic_json_dump(payload, plan_file)

    # Si la ruta es plana, guardar también en la ruta particionada para organización limpia del catálogo
    if u_code and d_code:
        part_path = get_plan_filepath(u_code, d_code, partitioned=True, ensure_dirs=True)
        if os.path.abspath(plan_file) != os.path.abspath(part_path):
            try:
                atomic_json_dump(payload, part_path)
            except Exception as exc:
                logger.warning("No se pudo escribir la copia particionada %s: %s", part_path, exc)

    if checkpoint_mgr:
        checkpoint_mgr.update_degree_record(d_code, boe_url, boe_fecha, now_iso)
