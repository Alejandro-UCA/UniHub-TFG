from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from models.models import Titulacion, PlanEstudios
from schemas.schemas import TitulacionOut, TitulacionDetalleOut, PlanEstudiosOut

router = APIRouter(prefix="/api/v1/titulaciones", tags=["Titulaciones y Planes de Estudio"])

@router.get("", response_model=List[TitulacionOut], summary="Búsqueda global de titulaciones oficiales vigentes")
def list_titulaciones(
    titulo: Optional[str] = Query(None, description="Filtrar por nombre o palabra clave de la titulación"),
    nivel_academico: Optional[str] = Query(None, description="Filtrar por Grado, Máster o Doctorado"),
    universidad_codigo: Optional[str] = Query(None, description="Filtrar por código de universidad"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Titulacion)
    if titulo:
        query = query.filter(Titulacion.titulo.ilike(f"%{titulo}%"))
    if nivel_academico:
        query = query.filter(Titulacion.nivel_academico.ilike(f"%{nivel_academico}%"))
    if universidad_codigo:
        query = query.filter(Titulacion.universidad_codigo == universidad_codigo.zfill(3))
        
    return query.offset(skip).limit(limit).all()

@router.get("/{codigo_estudio}", response_model=TitulacionDetalleOut, summary="Obtener información detallada de una titulación")
def get_titulacion(codigo_estudio: str, db: Session = Depends(get_db)):
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == codigo_estudio).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación con código '{codigo_estudio}' no encontrada.")
    return tit

@router.get("/{codigo_estudio}/plan-estudios", response_model=PlanEstudiosOut, summary="Obtener plan de estudios de la titulación extraído del BOE")
def get_plan_estudios(codigo_estudio: str, db: Session = Depends(get_db)):
    plan = db.query(PlanEstudios).filter(PlanEstudios.codigo_estudio == codigo_estudio).first()
    if not plan:
        raise HTTPException(
            status_code=404, 
            detail=f"Plan de estudios extraído del BOE para la titulación '{codigo_estudio}' no encontrado."
        )
    return plan
