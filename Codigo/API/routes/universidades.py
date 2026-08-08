from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import case

from database.connection import get_db, get_admin_db
from models.models import Universidad, Titulacion
from schemas.schemas import UniversidadOut, UniversidadCreate, UniversidadUpdate, TitulacionOut
from security import verify_api_key

router = APIRouter(prefix="/api/v1/universidades", tags=["Universidades"])

@router.get("", response_model=List[UniversidadOut], summary="Listar universidades públicas primero, luego privadas")
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
        
    query = query.order_by(
        case((Universidad.tipo.ilike("%públic%"), 0), (Universidad.tipo.ilike("%public%"), 0), else_=1),
        Universidad.nombre.asc()
    )
    return query.offset(skip).limit(limit).all()

@router.get("/{codigo}", response_model=UniversidadOut, summary="Obtener detalle de una universidad")
def get_universidad(codigo: str, db: Session = Depends(get_db)):
    univ = db.query(Universidad).filter(Universidad.codigo == codigo.zfill(3)).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == codigo).first()
    if not univ:
        raise HTTPException(status_code=404, detail=f"Universidad con código '{codigo}' no encontrada.")
    return univ

@router.get("/{codigo}/titulaciones", response_model=List[TitulacionOut], summary="Obtener titulaciones vigentes de una universidad")
def get_titulaciones_universidad(codigo: str, db: Session = Depends(get_db)):
    univ_code = codigo.zfill(3)
    univ = db.query(Universidad).filter(Universidad.codigo == univ_code).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == codigo).first()
    if not univ:
        raise HTTPException(status_code=404, detail=f"Universidad con código '{codigo}' no encontrada.")
        
    return db.query(Titulacion).filter(Titulacion.universidad_codigo == univ.codigo).all()

@router.post("", response_model=UniversidadOut, status_code=status.HTTP_201_CREATED, summary="Crear nueva universidad (Admin)")
def create_universidad(data: UniversidadCreate, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    code_formatted = data.codigo.zfill(3)
    existing = db.query(Universidad).filter(Universidad.codigo == code_formatted).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"La universidad con código '{code_formatted}' ya existe.")

    new_univ = Universidad(
        codigo=code_formatted,
        nombre=data.nombre,
        tipo=data.tipo,
        comunidad_autonoma=data.comunidad_autonoma,
        municipio=data.municipio,
        provincia=data.provincia,
        web=data.web,
        email=data.email,
        telefono=data.telefono,
        gestionado_por_admin=True
    )
    db.add(new_univ)
    db.commit()
    db.refresh(new_univ)
    return new_univ

@router.put("/{codigo}", response_model=UniversidadOut, summary="Actualizar universidad existente (Admin)")
def update_universidad(codigo: str, data: UniversidadUpdate, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    univ_code = codigo.zfill(3)
    univ = db.query(Universidad).filter(Universidad.codigo == univ_code).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == codigo).first()
    if not univ:
        raise HTTPException(status_code=404, detail=f"Universidad con código '{codigo}' no encontrada.")

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(univ, field, value)
    
    univ.gestionado_por_admin = True

    db.commit()
    db.refresh(univ)
    return univ

@router.delete("/{codigo}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar universidad (Admin)")
def delete_universidad(codigo: str, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    univ_code = codigo.zfill(3)
    univ = db.query(Universidad).filter(Universidad.codigo == univ_code).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == codigo).first()
    if not univ:
        raise HTTPException(status_code=404, detail=f"Universidad con código '{codigo}' no encontrada.")

    db.delete(univ)
    db.commit()
    return None
