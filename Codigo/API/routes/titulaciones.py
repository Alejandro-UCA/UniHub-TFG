from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import case, or_

try:
    from API.database.connection import get_db, get_admin_db
    from API.models.models import Titulacion, PlanEstudios, Universidad, ElementoCurricular
    from API.schemas.schemas import (
        TitulacionOut, TitulacionDetalleOut, PlanEstudiosOut, TitulacionCreate, TitulacionUpdate,
        ElementoCurricularOut, ElementoCurricularCreate, ElementoCurricularUpdate
    )
    from API.security import verify_api_key
except (ImportError, AttributeError):
    from database.connection import get_db, get_admin_db
    from models.models import Titulacion, PlanEstudios, Universidad, ElementoCurricular
    from schemas.schemas import (
        TitulacionOut, TitulacionDetalleOut, PlanEstudiosOut, TitulacionCreate, TitulacionUpdate,
        ElementoCurricularOut, ElementoCurricularCreate, ElementoCurricularUpdate
    )
    from security import verify_api_key

router = APIRouter(prefix="/api/v1/titulaciones", tags=["Titulaciones y Planes de Estudio"])

@router.get("", response_model=List[TitulacionOut], summary="Búsqueda global de titulaciones oficiales (Públicas primero)")
def list_titulaciones(
    response: Response,
    titulo: Optional[str] = Query(None, description="Filtrar por nombre o palabra clave de la titulación"),
    nivel_academico: Optional[str] = Query(None, description="Filtrar por Grado, Máster o Doctorado"),
    universidad_codigo: Optional[str] = Query(None, description="Filtrar por código de universidad"),
    ccaa: Optional[str] = Query(None, description="Filtrar por CCAA de la universidad"),
    tipo_universidad: Optional[str] = Query(None, description="Filtrar por tipo de universidad (pública/privada)"),
    rama: Optional[str] = Query(None, description="Filtrar por rama de conocimiento (salud, ingenieria, sociales, humanidades, ciencias)"),
    con_plan: Optional[bool] = Query(None, description="Filtrar solo titulaciones con plan de estudios y asignaturas disponibles"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Titulacion).outerjoin(Universidad)
    if con_plan is True:
        query = query.filter(Titulacion.plan_estudios.has(PlanEstudios.elementos_curriculares.any()))
    elif con_plan is False:
        query = query.filter(
            or_(
                ~Titulacion.plan_estudios.has(),
                ~Titulacion.plan_estudios.has(PlanEstudios.elementos_curriculares.any())
            )
        )
    if titulo and titulo.strip():
        query = query.filter(Titulacion.titulo.ilike(f"%{titulo.strip()}%"))
    if nivel_academico and nivel_academico.strip():
        query = query.filter(Titulacion.nivel_academico.ilike(f"%{nivel_academico.strip()}%"))
    if universidad_codigo and universidad_codigo.strip():
        u_clean = universidad_codigo.strip()
        query = query.filter(or_(Titulacion.universidad_codigo == u_clean.zfill(3), Titulacion.universidad_codigo == u_clean))
    if ccaa and ccaa.strip():
        query = query.filter(Universidad.comunidad_autonoma.ilike(f"%{ccaa.strip()}%"))
    if tipo_universidad and tipo_universidad.strip():
        query = query.filter(Universidad.tipo.ilike(f"%{tipo_universidad.strip()}%"))
    if rama and rama.lower().strip() not in ["todas", "all"]:
        r_low = rama.lower().strip()
        if "salud" in r_low:
            kws = ["médic", "medic", "salud", "enferm", "psicol", "farmac", "fisioter", "odontol", "veterin", "nutric", "bioméd", "biomed", "podol", "terapia", "óptic", "optic"]
            query = query.filter(or_(*[Titulacion.titulo.ilike(f"%{kw}%") for kw in kws]))
        elif "ingenier" in r_low or "arquitect" in r_low or "tecnolog" in r_low or "inform" in r_low:
            kws = ["ingenier", "informát", "informat", "computac", "telecomunic", "arquitect", "industrial", "software", "aeronáut", "aeronaut", "robótic", "robotic", "electr", "teleco", "mecán", "mecan", "civil"]
            query = query.filter(or_(*[Titulacion.titulo.ilike(f"%{kw}%") for kw in kws]))
        elif "social" in r_low or "jurid" in r_low or "derecho" in r_low or "econom" in r_low:
            kws = ["derecho", "administrac", "empresa", "ade", "econom", "marketing", "educac", "magisterio", "pedagog", "comunicac", "periodis", "criminol", "turismo", "sociolog", "polític", "politic", "finanz"]
            query = query.filter(or_(*[Titulacion.titulo.ilike(f"%{kw}%") for kw in kws]))
        elif "arte" in r_low or "humanid" in r_low or "filolog" in r_low:
            kws = ["historia", "filolog", "filosof", "lengua", "arte", "música", "musica", "traducc", "humanid", "literat", "arqueol", "diseño", "diseno", "bellas artes"]
            query = query.filter(or_(*[Titulacion.titulo.ilike(f"%{kw}%") for kw in kws]))
        elif "ciencia" in r_low or "experimental" in r_low:
            kws = ["físic", "fisic", "químic", "quimic", "matemát", "matemat", "biolog", "geolog", "biotecnol", "ciencias del mar", "estadíst", "estadist", "bioquím", "bioquim", "nanotecnol"]
            query = query.filter(or_(*[Titulacion.titulo.ilike(f"%{kw}%") for kw in kws]))
        
    query = query.order_by(
        case((Universidad.tipo.ilike("%públic%"), 0), (Universidad.tipo.ilike("%public%"), 0), else_=1),
        Titulacion.titulo.asc()
    )
    
    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    
    return query.offset(skip).limit(limit).all()

@router.get("/{codigo_estudio}", response_model=TitulacionDetalleOut, summary="Obtener información detallada de una titulación")
def get_titulacion(codigo_estudio: str, db: Session = Depends(get_db)):
    clean_code = codigo_estudio.strip()
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == clean_code).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación con código '{codigo_estudio}' no encontrada.")
    return tit

@router.get("/{codigo_estudio}/plan-estudios", response_model=PlanEstudiosOut, summary="Obtener plan de estudios de la titulación extraído del BOE / Web")
def get_plan_estudios(codigo_estudio: str, db: Session = Depends(get_db)):
    clean_code = codigo_estudio.strip()
    plan = db.query(PlanEstudios).filter(PlanEstudios.codigo_estudio == clean_code).first()
    if not plan:
        raise HTTPException(
            status_code=404, 
            detail=f"Plan de estudios para la titulación '{codigo_estudio}' no encontrado."
        )
    return plan

@router.get("/{codigo_estudio}/asignaturas/{elemento_id}/guia-docente", response_model=ElementoCurricularOut, summary="Obtener guía docente y temario de una asignatura específica")
def get_asignatura_guia_docente(codigo_estudio: str, elemento_id: int, db: Session = Depends(get_db)):
    clean_code = codigo_estudio.strip()
    plan = db.query(PlanEstudios).filter(PlanEstudios.codigo_estudio == clean_code).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan de estudios '{codigo_estudio}' no encontrado.")
    
    elem = db.query(ElementoCurricular).filter(
        ElementoCurricular.plan_estudio_id == plan.id,
        ElementoCurricular.id == elemento_id
    ).first()
    if not elem:
        raise HTTPException(status_code=404, detail=f"Asignatura con ID {elemento_id} no encontrada en este plan.")
    return elem

@router.post("", response_model=TitulacionOut, status_code=status.HTTP_201_CREATED, summary="Crear nueva titulación (Admin)")
def create_titulacion(data: TitulacionCreate, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    clean_code = data.codigo_estudio.strip()
    existing = db.query(Titulacion).filter(Titulacion.codigo_estudio == clean_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"La titulación con código '{clean_code}' ya existe.")

    univ_code = data.universidad_codigo.strip().zfill(3)
    univ = db.query(Universidad).filter(Universidad.codigo == univ_code).first()
    if not univ:
        univ = db.query(Universidad).filter(Universidad.codigo == data.universidad_codigo.strip()).first()
    if not univ:
        raise HTTPException(status_code=400, detail=f"Universidad asociada '{data.universidad_codigo}' no existe.")

    new_degree = Titulacion(
        codigo_estudio=clean_code,
        titulo=data.titulo.strip(),
        nivel_academico=data.nivel_academico.strip() if data.nivel_academico else None,
        estado=data.estado.strip() if data.estado else None,
        universidad_codigo=univ.codigo,
        precio_credito_ects=data.precio_credito_ects,
        precio_credito_2=data.precio_credito_2,
        precio_credito_3=data.precio_credito_3,
        precio_credito_4=data.precio_credito_4,
        precio_estimado_anual=data.precio_estimado_anual,
        fuente_precio=data.fuente_precio.strip() if data.fuente_precio else None,
        gestionado_por_admin=True
    )
    db.add(new_degree)
    db.commit()
    db.refresh(new_degree)
    return new_degree

@router.put("/{codigo_estudio}", response_model=TitulacionOut, summary="Actualizar titulación existente (Admin)")
def update_titulacion(codigo_estudio: str, data: TitulacionUpdate, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    clean_code = codigo_estudio.strip()
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == clean_code).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación con código '{codigo_estudio}' no encontrada.")

    update_dict = data.model_dump(exclude_unset=True)
    
    if "titulo" in update_dict:
        if not update_dict["titulo"] or not update_dict["titulo"].strip():
            raise HTTPException(status_code=422, detail="El título de la titulación no puede ser nulo ni vacío.")
        update_dict["titulo"] = update_dict["titulo"].strip()
            
    if "universidad_codigo" in update_dict:
        if not update_dict["universidad_codigo"] or not update_dict["universidad_codigo"].strip():
            raise HTTPException(status_code=422, detail="El código de universidad no puede ser nulo ni vacío.")
        
        u_code = update_dict["universidad_codigo"].strip().zfill(3)
        univ = db.query(Universidad).filter(Universidad.codigo == u_code).first()
        if not univ:
            univ = db.query(Universidad).filter(Universidad.codigo == update_dict["universidad_codigo"].strip()).first()
        if not univ:
            raise HTTPException(status_code=400, detail=f"Universidad asociada '{update_dict['universidad_codigo']}' no existe.")
        update_dict["universidad_codigo"] = univ.codigo

    for field, value in update_dict.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(tit, field, value)
        
    tit.gestionado_por_admin = True

    db.commit()
    db.refresh(tit)
    return tit

@router.delete("/{codigo_estudio}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar titulación (Admin)")
def delete_titulacion(codigo_estudio: str, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    clean_code = codigo_estudio.strip()
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == clean_code).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación con código '{codigo_estudio}' no encontrada.")

    db.delete(tit)
    db.commit()
    return None

# ==============================================================================
# CRUD ASIGNATURAS / ELEMENTOS CURRICULARES (ADMIN)
# ==============================================================================

@router.get("/{codigo_estudio}/asignaturas", response_model=List[ElementoCurricularOut], summary="Listar asignaturas de una titulación")
def list_asignaturas_titulacion(
    codigo_estudio: str,
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    clean_code = codigo_estudio.strip()
    plan = db.query(PlanEstudios).filter(PlanEstudios.codigo_estudio == clean_code).first()
    if not plan:
        return []
    query = db.query(ElementoCurricular).filter(ElementoCurricular.plan_estudio_id == plan.id)
    response.headers["X-Total-Count"] = str(query.count())
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return query.order_by(ElementoCurricular.curso.asc(), ElementoCurricular.nombre_elemento.asc()).offset(skip).limit(limit).all()

@router.post("/{codigo_estudio}/asignaturas", response_model=ElementoCurricularOut, status_code=status.HTTP_201_CREATED, summary="Crear nueva asignatura para una titulación (Admin)")
def create_asignatura(codigo_estudio: str, data: ElementoCurricularCreate, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    clean_code = codigo_estudio.strip()
    tit = db.query(Titulacion).filter(Titulacion.codigo_estudio == clean_code).first()
    if not tit:
        raise HTTPException(status_code=404, detail=f"Titulación '{codigo_estudio}' no existe.")

    plan = db.query(PlanEstudios).filter(PlanEstudios.codigo_estudio == clean_code).first()
    if not plan:
        plan = PlanEstudios(codigo_estudio=clean_code, origen_fuente="gestion_admin")
        db.add(plan)
        db.flush()

    create_dict = data.model_dump()
    if "nombre_elemento" in create_dict and create_dict["nombre_elemento"]:
        create_dict["nombre_elemento"] = create_dict["nombre_elemento"].strip()

    new_sub = ElementoCurricular(
        plan_estudio_id=plan.id,
        **create_dict
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
    return new_sub

@router.put("/asignaturas/{asignatura_id}", response_model=ElementoCurricularOut, summary="Actualizar asignatura existente (Admin)")
def update_asignatura(asignatura_id: int, data: ElementoCurricularUpdate, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    sub = db.query(ElementoCurricular).filter(ElementoCurricular.id == asignatura_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail=f"Asignatura con ID {asignatura_id} no encontrada.")

    update_dict = data.model_dump(exclude_unset=True)
    if "nombre_elemento" in update_dict:
        if not update_dict["nombre_elemento"] or not update_dict["nombre_elemento"].strip():
            raise HTTPException(status_code=422, detail="El nombre de la asignatura no puede ser nulo ni vacío.")
        update_dict["nombre_elemento"] = update_dict["nombre_elemento"].strip()

    for field, value in update_dict.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(sub, field, value)

    db.commit()
    db.refresh(sub)
    return sub

@router.delete("/asignaturas/{asignatura_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar asignatura (Admin)")
def delete_asignatura(asignatura_id: int, db: Session = Depends(get_admin_db), api_key: str = Depends(verify_api_key)):
    sub = db.query(ElementoCurricular).filter(ElementoCurricular.id == asignatura_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail=f"Asignatura con ID {asignatura_id} no encontrada.")

    db.delete(sub)
    db.commit()
    return None
