import logging
from typing import List
from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("unihub_api.estadisticas")

try:
    from API.config import settings
    from API.database.connection import get_db
    from API.models.models import EstadisticaRendimiento, ErrorCrawler, Titulacion, PlanEstudios, ElementoCurricular, Universidad
    from API.schemas.schemas import EstadisticaRendimientoOut, ErrorCrawlerOut
    from API.metrics.container_metrics import collect_container_physical_stats
    from API.database.etl_loader import run_etl
    from API.security import verify_api_key
except (ImportError, AttributeError):
    from config import settings
    from database.connection import get_db
    from models.models import EstadisticaRendimiento, ErrorCrawler, Titulacion, PlanEstudios, ElementoCurricular, Universidad
    from schemas.schemas import EstadisticaRendimientoOut, ErrorCrawlerOut
    from metrics.container_metrics import collect_container_physical_stats
    from database.etl_loader import run_etl
    from security import verify_api_key

router = APIRouter(prefix="/api/v1", tags=["Métricas y Salud del Crawler"])

@router.get("/salud", summary="Comprobar estado de disponibilidad de la API y PostgreSQL")
def get_salud(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("La comprobación de disponibilidad de PostgreSQL ha fallado")
        raise HTTPException(status_code=503, detail="Base de datos no disponible.")
    return {"status": "ok", "service": "unihub_api", "database": "ok"}

@router.get("/estadisticas", response_model=List[EstadisticaRendimientoOut], summary="Obtener historial de estadísticas de rendimiento del crawler")
def get_estadisticas(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    return db.query(EstadisticaRendimiento).order_by(EstadisticaRendimiento.id.desc()).limit(limit).all()

@router.get("/errores", response_model=List[ErrorCrawlerOut], summary="Obtener registro de incidencias del crawler")
def get_errores(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    return db.query(ErrorCrawler).order_by(ErrorCrawler.id.desc()).offset(skip).limit(limit).all()

@router.get("/estadisticas/contenedores", summary="Obtener métricas físicas del consumo de recursos de los contenedores Docker")
def get_estadisticas_contenedores(api_key: str = Depends(verify_api_key)):
    return collect_container_physical_stats()

@router.get("/crawler/checkpoint", summary="Obtener datos detallados del checkpoint de la Fase 1 (Universidades, Titulaciones, PDFs descartados y fallos)")
def get_crawler_checkpoint(api_key: str = Depends(verify_api_key)):
    """
    Lee el archivo checkpoint.json directamente del disco y expone el estado del rastreador,
    incluyendo el registro de PDFs descartados por no ser plan de estudios y fallos de descarga.
    """
    import os, json
    possible_paths = [
        settings.CHECKPOINT_PATH,
        os.path.join(settings.CRAWLER_DATA_DIR, "checkpoint.json")
    ]
    checkpoint_data = {
        "universities_downloaded": False,
        "total_universidades_procesadas": 0,
        "processed_universities": [],
        "total_titulaciones_procesadas": 0,
        "processed_degrees": {},
        "total_pdfs_descartados_no_plan": 0,
        "non_study_plan_pdfs": [],
        "total_fallos_descarga_pdf": 0,
        "failed_pdf_downloads": {}
    }
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    univs = raw.get("processed_universities", [])
                    degs = raw.get("processed_degrees", {})
                    non_plans = raw.get("non_study_plan_pdfs", [])
                    failed = raw.get("failed_pdf_downloads", {})
                    return {
                        "universities_downloaded": raw.get("universities_downloaded", False),
                        "total_universidades_procesadas": len(univs),
                        "processed_universities": univs,
                        "total_titulaciones_procesadas": len(degs) if isinstance(degs, dict) else len(degs),
                        "processed_degrees": degs,
                        "total_pdfs_descartados_no_plan": len(non_plans),
                        "non_study_plan_pdfs": non_plans,
                        "total_fallos_descarga_pdf": len(failed) if isinstance(failed, dict) else 0,
                        "failed_pdf_downloads": failed
                    }
            except Exception as e:
                logger.error(f"Error al leer checkpoint.json en {p}: {e}")
    return checkpoint_data

@router.get("/crawler/errores_json", summary="Obtener registro completo de errores en formato JSON del crawler")
def get_crawler_errores_json(api_key: str = Depends(verify_api_key)):
    """
    Lee el archivo errores_crawler.json directamente del disco de la Fase 1.
    """
    import os, json
    possible_paths = [
        os.path.join(settings.CRAWLER_DATA_DIR, "errores_crawler.json"),
        "/app/Datos/errores_crawler.json"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error al leer errores_crawler.json en {p}: {e}")
    return []

@router.get("/api_docs_info", summary="Obtener mapa interactivo de capacidades y documentación Swagger/ReDoc de la API REST")
def get_api_docs_info(request: Request):
    """Genera el catálogo desde OpenAPI, la fuente de verdad de las rutas."""
    schema = request.app.openapi()
    endpoints = []
    for path, operations in sorted(schema.get("paths", {}).items()):
        for method, operation in sorted(operations.items()):
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            endpoints.append({
                "metodo": method.upper(),
                "path": path,
                "descripcion": operation.get("summary") or operation.get("description") or "",
                "parametros": [parameter["name"] for parameter in operation.get("parameters", [])],
            })
    return {
        "titulo": schema.get("info", {}).get("title", "UniHub API REST"),
        "version": schema.get("info", {}).get("version", ""),
        "base_url": "/api/v1",
        "swagger_ui_url": "/docs",
        "redoc_ui_url": "/redoc",
        "modelos_autorizacion": "Lectura pública y operaciones protegidas con X-API-Key.",
        "endpoints_disponibles": endpoints,
    }

@router.get("/estadisticas/cobertura", summary="Obtener métricas globales de cobertura curricular, Green IT y distribución por CCAA")
def get_estadisticas_cobertura(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    """
    Calcula la tasa global de cobertura curricular, distribución por CCAA
    e indicadores de sostenibilidad Green IT y eficiencia de caché.
    """
    import os, tempfile
    from sqlalchemy import func

    total_titulaciones = db.query(Titulacion).count()
    titulaciones_con_plan_detallado = (
        db.query(PlanEstudios.codigo_estudio)
        .join(ElementoCurricular, ElementoCurricular.plan_estudio_id == PlanEstudios.id)
        .distinct()
        .count()
    )

    cobertura_pct = round((titulaciones_con_plan_detallado / total_titulaciones * 100), 2) if total_titulaciones > 0 else 0.0

    # Distribución de titulaciones por CCAA
    ccaa_distribution = {}
    ccaa_query = db.query(Universidad.comunidad_autonoma, func.count(Titulacion.id))\
        .join(Titulacion, Titulacion.universidad_codigo == Universidad.codigo)\
        .group_by(Universidad.comunidad_autonoma).all()

    for ccaa, count in ccaa_query:
        if ccaa:
            ccaa_distribution[ccaa] = count

    # Estado del ETL lock file
    lock_file = os.path.join(tempfile.gettempdir(), "etl_running.lock")
    etl_running = os.path.exists(lock_file)

    return {
        "total_titulaciones_bd": total_titulaciones,
        "titulaciones_con_plan_detallado": titulaciones_con_plan_detallado,
        "tasa_cobertura_curricular_porcentaje": cobertura_pct,
        "distribucion_titulaciones_ccaa": ccaa_distribution,
        "etl_running": etl_running,
        "green_it_metrica": {
            "medicion_disponible": False,
            "gco2_por_mb": None,
            "descripcion": "No hay medición Green IT global disponible; las estimaciones del proceso API se exponen por separado."
        }
    }

@router.post("/etl/sync", summary="Ejecutar la sincronización ETL de datos de la Fase 1 a PostgreSQL (Fase 2)")
def sync_etl_data(api_key: str = Depends(verify_api_key)):
    if not run_etl():
        raise HTTPException(status_code=503, detail="La sincronización ETL no pudo completarse.")
    return {"status": "ok", "mensaje": "Proceso de sincronización ETL completado correctamente."}

@router.get("/auth/verify", summary="Verificar validez de la clave de administrador X-API-Key")
def verify_admin_auth(api_key: str = Depends(verify_api_key)):
    return {"authenticated": True, "role": "admin"}
