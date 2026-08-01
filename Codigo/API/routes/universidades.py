from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from models.models import Universidad, Titulacion
from schemas.schemas import UniversidadOut, TitulacionOut

router = APIRouter(prefix="/api/v1/universidades", tags=["Universidades"])

@router.get("", response_model=List[UniversidadOut], summary="Listar universidades públicas y privadas")
def list_universidades(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (Pública / Privada)"),
    ccaa: Optional[str] = Query(None, description="Filtrar por Comunidad Autónoma"),
    nombre: Optional[str] = Query(None, description="Búsqueda por nombre de la universidad"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Universidad)
    if tipo:
        query = query.filter(Universidad.tipo.ilike(f"%{tipo}%"))
    if ccaa:
        query = query.filter(Universidad.comunidad_autonoma.ilike(f"%{ccaa}%"))
    if nombre:
        query = query.filter(Universidad.nombre.ilike(f"%{nombre}%"))
        
    return query.offset(skip).limit(limit).all()

@router.get("/{codigo}", response_model=UniversidadOut, summary="Obtener detalle de una universidad")
def get_universidad(codigo: str, db: Session = Depends(get_db)):
    univ = db.query(Universidad).filter(Universidad.codigo == codigo.zfill(3)).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == codigo).first()
    if not univ:
        raise HTTPException(status_code=440, detail=f"Universidad con código '{codigo}' no encontrada.")
    return univ

@router.get("/{codigo}/titulaciones", response_model=List[TitulacionOut], summary="Obtener titulaciones vigentes de una universidad")
def get_titulaciones_universidad(codigo: str, db: Session = Depends(get_db)):
    univ_code = codigo.zfill(3)
    univ = db.query(Universidad).filter(Universidad.codigo == univ_code).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == codigo).first()
    if not univ:
        raise HTTPException(status_code=440, detail=f"Universidad con código '{codigo}' no encontrada.")
        
    return db.query(Titulacion).filter(Titulacion.universidad_codigo == univ.codigo).all()
