from typing import List
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session

from database.connection import get_db
from models.models import EstadisticaRendimiento, ErrorCrawler
from schemas.schemas import EstadisticaRendimientoOut, ErrorCrawlerOut
from metrics.container_metrics import collect_container_physical_stats
from database.etl_loader import run_etl
from security import verify_api_key

router = APIRouter(prefix="/api/v1", tags=["Métricas y Salud del Crawler"])

@router.get("/salud", summary="Comprobar estado de salud del servicio API")
def get_salud():
    return {"status": "ok", "service": "unihub_api"}

@router.get("/estadisticas", response_model=List[EstadisticaRendimientoOut], summary="Obtener historial de estadísticas de rendimiento del crawler")
def get_estadisticas(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    return db.query(EstadisticaRendimiento).order_by(EstadisticaRendimiento.id.desc()).limit(limit).all()

@router.get("/errores", response_model=List[ErrorCrawlerOut], summary="Obtener registro de incidencias del crawler")
def get_errores(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    return db.query(ErrorCrawler).order_by(ErrorCrawler.id.desc()).offset(skip).limit(limit).all()

@router.get("/estadisticas/contenedores", summary="Obtener métricas físicas del consumo de recursos de los contenedores Docker")
def get_estadisticas_contenedores():
    return collect_container_physical_stats()

@router.get("/crawler/checkpoint", summary="Obtener datos detallados del checkpoint de la Fase 1 (Universidades, Titulaciones, PDFs descartados y fallos)")
def get_crawler_checkpoint(api_key: str = Depends(verify_api_key)):
    """
    Lee el archivo checkpoint.json directamente del disco y expone el estado del rastreador,
    incluyendo el registro de PDFs descartados por no ser plan de estudios y fallos de descarga.
    """
    import os, json
    possible_paths = [
        "/app/Datos/checkpoint.json",
        "d:/Proyecto/Codigo/Crawler/Datos/checkpoint.json",
        "Codigo/Crawler/Datos/checkpoint.json"
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
                print(f"Error al leer checkpoint.json en {p}: {e}")
    return checkpoint_data

@router.get("/crawler/errores_json", summary="Obtener registro completo de errores en formato JSON del crawler")
def get_crawler_errores_json(api_key: str = Depends(verify_api_key)):
    """
    Lee el archivo errores_crawler.json directamente del disco de la Fase 1.
    """
    import os, json
    possible_paths = [
        "/app/Datos/errores_crawler.json",
        "d:/Proyecto/Codigo/Crawler/Datos/errores_crawler.json",
        "Codigo/Crawler/Datos/errores_crawler.json"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return []

@router.get("/api_docs_info", summary="Obtener mapa interactivo de capacidades y documentación Swagger/ReDoc de la API REST")
def get_api_docs_info():
    """
    Expone la estructura completa de controladores, métodos HTTP y capacidades de la API REST de UniHub.
    """
    return {
        "titulo": "UniHub API REST - Catálogo de Enseñanza Superior",
        "version": "1.0.0",
        "base_url": "http://localhost:8000/api/v1",
        "swagger_ui_url": "http://localhost:8000/docs",
        "redoc_ui_url": "http://localhost:8000/redoc",
        "modelos_autorizacion": "Rol de lectura pública + Rol exclusivo de Administración CRUD (/admin)",
        "endpoints_disponibles": [
            {
                "metodo": "GET",
                "path": "/api/v1/universidades",
                "descripcion": "Listado con ordenación prioritaria (Públicas primero, Privadas después) con filtros por tipo, CCAA y nombre.",
                "parametros": ["tipo (opcional)", "ccaa (opcional)", "nombre (opcional)", "skip", "limit"]
            },
            {
                "metodo": "GET",
                "path": "/api/v1/universidades/{codigo}",
                "descripcion": "Obtiene la ficha detallada de una universidad por su código RUCT (3 dígitos)."
            },
            {
                "metodo": "GET",
                "path": "/api/v1/universidades/{codigo}/titulaciones",
                "descripcion": "Obtiene el listado de titulaciones oficiales vigentes asociadas a una universidad."
            },
            {
                "metodo": "POST",
                "path": "/api/v1/universidades",
                "descripcion": "[CRUD Admin] Crea un nuevo centro universitario en PostgreSQL."
            },
            {
                "metodo": "PUT",
                "path": "/api/v1/universidades/{codigo}",
                "descripcion": "[CRUD Admin] Actualiza los datos de una universidad existente."
            },
            {
                "metodo": "DELETE",
                "path": "/api/v1/universidades/{codigo}",
                "descripcion": "[CRUD Admin] Elimina una universidad y sus titulaciones asociadas (borrado en cascada)."
            },
            {
                "metodo": "GET",
                "path": "/api/v1/titulaciones",
                "descripcion": "Listado de titulaciones clasificadas por nivel (Grado, Máster, Doctorado) con búsqueda."
            },
            {
                "metodo": "GET",
                "path": "/api/v1/titulaciones/{codigo_estudio}/plan-estudios",
                "descripcion": "Visualiza la estructura curricular ECTS y enlace al BOE del plan de estudios."
            },
            {
                "metodo": "POST",
                "path": "/api/v1/titulaciones",
                "descripcion": "[CRUD Admin] Registra una nueva titulación en la base de datos."
            },
            {
                "metodo": "PUT",
                "path": "/api/v1/titulaciones/{codigo_estudio}",
                "descripcion": "[CRUD Admin] Modifica la información de una titulación."
            },
            {
                "metodo": "DELETE",
                "path": "/api/v1/titulaciones/{codigo_estudio}",
                "descripcion": "[CRUD Admin] Elimina una titulación de la base de datos."
            },
            {
                "metodo": "GET",
                "path": "/api/v1/estadisticas/contenedores",
                "descripcion": "Analizador en vivo del consumo de recursos físicos (RAM RSS MB, CPU %) por cada contenedor Docker."
            },
            {
                "metodo": "GET",
                "path": "/api/v1/crawler/checkpoint",
                "descripcion": "Muestra el estado detallado de avance del rastreador, PDFs descartados y fallos de conexión de la Fase 1."
            },
            {
                "metodo": "GET",
                "path": "/api/v1/crawler/errores_json",
                "descripcion": "Acceso directo al registro completo de errores de scraping (errores_crawler.json)."
            },
            {
                "metodo": "POST",
                "path": "/api/v1/etl/sync",
                "descripcion": "Desencadena la carga e inserción atómica ETL de los JSON de la Fase 1 hacia PostgreSQL (Fase 2)."
            }
        ]
    }

@router.get("/estadisticas/cobertura", summary="Obtener métricas globales de cobertura curricular, Green IT y distribución por CCAA")
def get_estadisticas_cobertura(db: Session = Depends(get_db)):
    """
    Calcula la tasa global de cobertura curricular, distribución por CCAA
    e indicadores de sostenibilidad Green IT y eficiencia de caché.
    """
    import os, tempfile
    from models.models import Titulacion, PlanEstudios, Universidad
    from sqlalchemy import func

    total_titulaciones = db.query(Titulacion).count()
    titulaciones_con_plan = db.query(PlanEstudios.codigo_estudio).distinct().count()

    cobertura_pct = round((titulaciones_con_plan / total_titulaciones * 100), 2) if total_titulaciones > 0 else 0.0

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
        "titulaciones_con_plan_completo": titulaciones_con_plan,
        "tasa_cobertura_curricular_porcentaje": cobertura_pct,
        "distribucion_titulaciones_ccaa": ccaa_distribution,
        "etl_running": etl_running,
        "green_it_metrica": {
            "gco2_por_mb": 0.05,
            "descripcion": "Estimación de consumo Green IT (~0.05 gCO2 / MB procesado)"
        }
    }

@router.post("/etl/sync", summary="Ejecutar la sincronización ETL de datos de la Fase 1 a PostgreSQL (Fase 2)")
def sync_etl_data(background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    background_tasks.add_task(run_etl)
    return {"status": "ok", "mensaje": "Proceso de sincronización ETL iniciado en segundo plano."}

@router.get("/auth/verify", summary="Verificar validez de la clave de administrador X-API-Key")
def verify_admin_auth(api_key: str = Depends(verify_api_key)):
    return {"authenticated": True, "role": "admin"}
