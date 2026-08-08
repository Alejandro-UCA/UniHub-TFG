from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, Field

class UniversidadBase(BaseModel):
    codigo: str = Field(..., max_length=10)
    nombre: str = Field(..., max_length=500)
    tipo: Optional[str] = Field(None, max_length=50)
    comunidad_autonoma: Optional[str] = Field(None, max_length=100)
    municipio: Optional[str] = Field(None, max_length=100)
    provincia: Optional[str] = Field(None, max_length=100)
    web: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=50)
    gestionado_por_admin: Optional[bool] = False

class UniversidadCreate(UniversidadBase):
    pass

class UniversidadUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=500)
    tipo: Optional[str] = Field(None, max_length=50)
    comunidad_autonoma: Optional[str] = Field(None, max_length=100)
    municipio: Optional[str] = Field(None, max_length=100)
    provincia: Optional[str] = Field(None, max_length=100)
    web: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=50)

class UniversidadOut(UniversidadBase):
    id: int
    creado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TitulacionBase(BaseModel):
    codigo_estudio: str = Field(..., max_length=20)
    titulo: str
    nivel_academico: Optional[str] = Field(None, max_length=200)
    estado: Optional[str] = Field(None, max_length=200)
    universidad_codigo: str = Field(..., max_length=10)
    precio_credito_ects: Optional[float] = None
    precio_credito_2: Optional[float] = None
    precio_credito_3: Optional[float] = None
    precio_credito_4: Optional[float] = None
    precio_estimado_anual: Optional[float] = None
    fuente_precio: Optional[str] = Field(None, max_length=255)
    gestionado_por_admin: Optional[bool] = False

class TitulacionCreate(TitulacionBase):
    pass

class TitulacionUpdate(BaseModel):
    titulo: Optional[str] = None
    nivel_academico: Optional[str] = Field(None, max_length=200)
    estado: Optional[str] = Field(None, max_length=200)
    universidad_codigo: Optional[str] = Field(None, max_length=10)
    precio_credito_ects: Optional[float] = None
    precio_credito_2: Optional[float] = None
    precio_credito_3: Optional[float] = None
    precio_credito_4: Optional[float] = None
    precio_estimado_anual: Optional[float] = None
    fuente_precio: Optional[str] = Field(None, max_length=255)

class TitulacionOut(TitulacionBase):
    id: int
    creado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ElementoCurricularOut(BaseModel):
    id: int
    modulo: Optional[str] = None
    materia: Optional[str] = None
    nombre_elemento: str
    creditos_ects: Optional[str] = None
    caracter: Optional[str] = None
    curso: Optional[str] = None
    cuatrimestre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ResumenCreditosOut(BaseModel):
    id: int
    tipo_credito: str
    cantidad_creditos: str

    model_config = ConfigDict(from_attributes=True)


class PlanEstudiosOut(BaseModel):
    id: int
    codigo_estudio: str
    boe_url: Optional[str] = None
    boe_fecha: Optional[date] = None
    fecha_procesado: Optional[datetime] = None
    resumen_creditos: List[ResumenCreditosOut] = []
    elementos_curriculares: List[ElementoCurricularOut] = []

    model_config = ConfigDict(from_attributes=True)


class TitulacionDetalleOut(TitulacionOut):
    plan_estudios: Optional[PlanEstudiosOut] = None


class ErrorCrawlerOut(BaseModel):
    id: int
    timestamp: Optional[datetime] = None
    fase: Optional[str] = None
    id_entidad: Optional[str] = None
    url: Optional[str] = None
    motivo_fallo: Optional[str] = None
    detalles_excepcion: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EstadisticaRendimientoOut(BaseModel):
    id: int
    timestamp_reporte: Optional[datetime] = None
    uso_memoria_actual_mb: Optional[float] = None
    pico_maximo_memoria_mb: Optional[float] = None
    porcentaje_uso_memoria: Optional[float] = None
    tiempo_total_ejecucion_seg: Optional[float] = None
    tiempo_procesamiento_cpu_seg: Optional[float] = None
    tiempo_espera_io_red_seg: Optional[float] = None
    universidades_inspeccionadas: Optional[int] = None
    titulaciones_inspeccionadas: Optional[int] = None
    titulaciones_al_dia: Optional[int] = None
    titulaciones_actualizadas: Optional[int] = None
    pdfs_parseados: Optional[int] = None
    errores_registrados: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
