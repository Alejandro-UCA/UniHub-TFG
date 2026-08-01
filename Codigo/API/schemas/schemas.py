from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict

class UniversidadBase(BaseModel):
    codigo: str
    nombre: str
    tipo: Optional[str] = None
    comunidad_autonoma: Optional[str] = None
    municipio: Optional[str] = None
    provincia: Optional[str] = None
    web: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None

class UniversidadOut(UniversidadBase):
    id: int
    creado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TitulacionBase(BaseModel):
    codigo_estudio: str
    titulo: str
    nivel_academico: Optional[str] = None
    estado: Optional[str] = None
    universidad_codigo: str

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
