from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import case

from database.connection import get_db
from models.models import Titulacion, PlanEstudios, Universidad
from schemas.schemas import TitulacionOut, TitulacionDetalleOut, PlanEstudiosOut, TitulacionCreate, TitulacionUpdate

router = APIRouter(prefix="/api/v1/titulaciones", tags=["Titulaciones y Planes de Estudio"])

@router.get("", response_model=List[TitulacionOut], summary="Búsqueda global de titulaciones oficiales (Públicas primero)")
def list_titulaciones(
    titulo: Optional[str] = Query(None, description="Filtrar por nombre o palabra clave de la titulación"),
    nivel_academico: Optional[str] = Query(None, description="Filtrar por Grado, Máster o Doctorado"),
    universidad_codigo: Optional[str] = Query(None, description="Filtrar por código de universidad"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Titulacion).join(Universidad)
    if titulo:
        query = query.filter(Titulacion.titulo.ilike(f"%{titulo}%"))
    if nivel_academico:
        query = query.filter(Titulacion.nivel_academico.ilike(f"%{nivel_academico}%"))
    if universidad_codigo:
        query = query.filter(Titulacion.universidad_codigo == universidad_codigo.zfill(3))
        
    query = query.order_by(
        case((Universidad.tipo.ilike("%públic%"), 0), (Universidad.tipo.ilike("%public%"), 0), else_=1),
        Titulacion.titulo.asc()
    )
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

@router.post("", response_model=TitulacionOut, status_code=status.HTTP_201_CREATED, summary="Crear nueva titulación (Admin)")
def create_titulacion(data: TitulacionCreate, db: Session = Depends(get_db)):
    existing = db.query(Titulacion).filter(Titulacion.codigo_estudio == data.codigo_estudio).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"La titulación con código '{data.codigo_estudio}' ya existe.")

    univ_code = data.universidad_codigo.zfill(3)
    univ = db.query(Universidad).filter(Universidad.codigo == univ_code).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == data.universidad_codigo).first()
    if not univ:
        raise HTTPException(status_code=400, detail=f"Universidad asociada '{data.universidad_codigo}' no existe.")

    new_degree = Titulacion(
        codigo_estudio=data.codigo_estudio,
        titulo=data.titulo,
        nivel_academico=data.nivel_academico,
        estado=data.estado or "Publicado en B.O.E.",
        universidad_codigo=univ.codigo
    )
    db.add(new_degree)
    db.commit()
    db.refresh(new_degree)
    return new_degree

@router.put("/{codigo_estudio}", response_model=TitulacionOut, summary="Actualizar titulación existente (Admin)")
def update_titulacion(codigo_estudio: str, data: TitulacionUpdate, db: Session = Depends(get_db)):
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == codigo_estudio).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación con código '{codigo_estudio}' no encontrada.")

    update_dict = data.model_dump(exclude_unset=True)
    if "universidad_codigo" in update_dict and update_dict["universidad_codigo"]:
        update_dict["universidad_codigo"] = update_dict["universidad_codigo"].zfill(3)

    for field, value in update_dict.items():
        setattr(tit, field, value)

    db.commit()
    db.refresh(tit)
    return tit

@router.delete("/{codigo_estudio}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar titulación (Admin)")
def delete_titulacion(codigo_estudio: str, db: Session = Depends(get_db)):
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == codigo_estudio).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación con código '{codigo_estudio}' no encontrada.")

    db.delete(tit)
    db.commit()
    return None
