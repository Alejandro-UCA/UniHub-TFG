from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from models.models import EstadisticaRendimiento, ErrorCrawler
from schemas.schemas import EstadisticaRendimientoOut, ErrorCrawlerOut

router = APIRouter(prefix="/api/v1", tags=["Métricas y Salud del Crawler"])

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
