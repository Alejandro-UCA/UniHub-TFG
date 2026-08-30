from typing import List, Optional, Any, Dict, Union, Annotated
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Los límites reflejan los NUMERIC de PostgreSQL y evitan que `NaN` o `inf`
# lleguen a la persistencia, donde generan errores menos comprensibles.
PrecioCredito = Annotated[Optional[float], Field(default=None, ge=0, le=9999.99, allow_inf_nan=False)]
PrecioAnual = Annotated[Optional[float], Field(default=None, ge=0, le=999999.99, allow_inf_nan=False)]
CreditoDetalle = Annotated[Optional[float], Field(default=None, ge=0, le=99.99, allow_inf_nan=False)]

class UniversidadBase(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=10)
    nombre: str = Field(..., min_length=1, max_length=500)
    tipo: Optional[str] = Field(None, max_length=50)
    comunidad_autonoma: Optional[str] = Field(None, max_length=100)
    municipio: Optional[str] = Field(None, max_length=100)
    provincia: Optional[str] = Field(None, max_length=100)
    web: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=50)
    gestionado_por_admin: Optional[bool] = False

    @field_validator("codigo")
    @classmethod
    def strip_and_format_codigo(cls, v: str) -> str:
        value = v.strip() if v else v
        if not value:
            raise ValueError("El código no puede estar vacío.")
        return value

    @field_validator("nombre")
    @classmethod
    def strip_nombre(cls, v: str) -> str:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                raise ValueError("El nombre no puede estar vacío.")
            return v_str
        return v

class UniversidadCreate(UniversidadBase):
    pass

class UniversidadUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=500)
    tipo: Optional[str] = Field(None, max_length=50)
    comunidad_autonoma: Optional[str] = Field(None, max_length=100)
    municipio: Optional[str] = Field(None, max_length=100)
    provincia: Optional[str] = Field(None, max_length=100)
    web: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=50)

    @field_validator("nombre")
    @classmethod
    def strip_nombre(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                raise ValueError("El nombre no puede estar vacío.")
            return v_str
        return v

class UniversidadOut(UniversidadBase):
    id: int
    creado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TitulacionBase(BaseModel):
    codigo_estudio: str = Field(..., min_length=1, max_length=20)
    titulo: str = Field(..., min_length=1)
    nivel_academico: Optional[str] = Field(None, max_length=200)
    estado: Optional[str] = Field(None, max_length=200)
    universidad_codigo: str = Field(..., min_length=1, max_length=10)
    precio_credito_ects: PrecioCredito = None
    precio_credito_2: PrecioCredito = None
    precio_credito_3: PrecioCredito = None
    precio_credito_4: PrecioCredito = None
    precio_estimado_anual: PrecioAnual = None
    fuente_precio: Optional[str] = Field(None, max_length=255)
    gestionado_por_admin: Optional[bool] = False

    @field_validator("codigo_estudio", "universidad_codigo")
    @classmethod
    def strip_codigos(cls, v: str) -> str:
        value = v.strip() if v else v
        if not value:
            raise ValueError("El código no puede estar vacío.")
        return value

    @field_validator("titulo")
    @classmethod
    def strip_titulo(cls, v: str) -> str:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                raise ValueError("El título no puede estar vacío.")
            return v_str
        return v

class TitulacionCreate(TitulacionBase):
    pass

class TitulacionUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1)
    nivel_academico: Optional[str] = Field(None, max_length=200)
    estado: Optional[str] = Field(None, max_length=200)
    universidad_codigo: Optional[str] = Field(None, max_length=10)
    precio_credito_ects: PrecioCredito = None
    precio_credito_2: PrecioCredito = None
    precio_credito_3: PrecioCredito = None
    precio_credito_4: PrecioCredito = None
    precio_estimado_anual: PrecioAnual = None
    fuente_precio: Optional[str] = Field(None, max_length=255)

    @field_validator("titulo")
    @classmethod
    def strip_titulo(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                raise ValueError("El título no puede estar vacío.")
            return v_str
        return v

class TitulacionOut(TitulacionBase):
    id: int
    creado_en: Optional[datetime] = None
    universidad_nombre: Optional[str] = None
    universidad_tipo: Optional[str] = None
    centro_adscrito: Optional[str] = None
    es_alianza_europea: bool = False
    web_fuente_directa_url: Optional[str] = None
    estado_calidad_plan: Optional[str] = None
    origen_fuente: Optional[str] = None
    fuente_verificada_url: Optional[str] = None
    tiene_plan_verificado: bool = False
    plan_incompleto: bool = False

    model_config = ConfigDict(from_attributes=True)


class ElementoCurricularBase(BaseModel):
    modulo: Optional[str] = None
    materia: Optional[str] = None
    nombre_elemento: Optional[str] = Field("Materia sin especificar")
    creditos_ects: Optional[str] = None
    caracter: Optional[str] = None
    curso: Optional[str] = None
    cuatrimestre: Optional[str] = None
    url_guia_docente: Optional[str] = None
    temario: Optional[Any] = None
    sistema_evaluacion: Optional[Any] = None
    profesorado: Optional[Any] = None
    bibliografia: Optional[Any] = None
    idioma: Optional[str] = None
    creditos_teoria: CreditoDetalle = None
    creditos_practica: CreditoDetalle = None
    tipo_asistencia: Optional[str] = None
    calificacion_minima: CreditoDetalle = None
    departamento: Optional[str] = None

    @field_validator("nombre_elemento")
    @classmethod
    def strip_nombre_elem(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_str = v.strip()
            return v_str or "Materia sin especificar"
        return "Materia sin especificar"

class ElementoCurricularCreate(ElementoCurricularBase):
    nombre_elemento: str = Field(..., min_length=1)

    @field_validator("nombre_elemento")
    @classmethod
    def validate_create_nombre(cls, v: str) -> str:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                raise ValueError("El nombre del elemento curricular no puede estar vacío.")
            return v_str
        raise ValueError("El nombre del elemento curricular no puede estar vacío.")

class ElementoCurricularUpdate(BaseModel):
    modulo: Optional[str] = None
    materia: Optional[str] = None
    nombre_elemento: Optional[str] = Field(None, min_length=1)
    creditos_ects: Optional[str] = None
    caracter: Optional[str] = None
    curso: Optional[str] = None
    cuatrimestre: Optional[str] = None
    url_guia_docente: Optional[str] = None
    temario: Optional[Any] = None
    sistema_evaluacion: Optional[Any] = None
    profesorado: Optional[Any] = None
    bibliografia: Optional[Any] = None
    idioma: Optional[str] = None
    creditos_teoria: CreditoDetalle = None
    creditos_practica: CreditoDetalle = None
    tipo_asistencia: Optional[str] = None
    calificacion_minima: CreditoDetalle = None
    departamento: Optional[str] = None

    @field_validator("nombre_elemento")
    @classmethod
    def strip_nombre_elem(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                raise ValueError("El nombre del elemento curricular no puede estar vacío.")
            return v_str
        return v

class ElementoCurricularOut(ElementoCurricularBase):
    id: int

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
    origen_fuente: Optional[str] = None
    pdf_sha256: Optional[str] = None
    estado_calidad: str
    motivos_calidad: Optional[Dict[str, Any]] = None
    fuente_verificada_url: Optional[str] = None
    verificado_en: Optional[datetime] = None
    fecha_procesado: Optional[datetime] = None
    tipo_estructura: Optional[str] = None
    ects_exigidos: Optional[str] = None
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
