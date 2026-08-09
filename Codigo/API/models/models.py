from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Numeric, ForeignKey, func, Boolean
from sqlalchemy.orm import relationship
from database.connection import Base

class Universidad(Base):
    __tablename__ = "universidades"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(10), unique=True, nullable=False, index=True)
    nombre = Column(Text, nullable=False)
    tipo = Column(String(100))
    comunidad_autonoma = Column(String(200))
    municipio = Column(String(200))
    provincia = Column(String(200))
    web = Column(Text)
    email = Column(String(500))
    telefono = Column(String(200))
    gestionado_por_admin = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=func.now())

    titulaciones = relationship("Titulacion", back_populates="universidad", cascade="all, delete-orphan")


class Titulacion(Base):
    __tablename__ = "titulaciones"

    id = Column(Integer, primary_key=True, index=True)
    codigo_estudio = Column(String(20), unique=True, nullable=False, index=True)
    titulo = Column(Text, nullable=False)
    nivel_academico = Column(Text, index=True)
    estado = Column(String(200))
    universidad_codigo = Column(String(10), ForeignKey("universidades.codigo", ondelete="CASCADE"), nullable=False)
    precio_credito_ects = Column(Numeric(6, 2), nullable=True)
    precio_credito_2 = Column(Numeric(6, 2), nullable=True)
    precio_credito_3 = Column(Numeric(6, 2), nullable=True)
    precio_credito_4 = Column(Numeric(6, 2), nullable=True)
    precio_estimado_anual = Column(Numeric(8, 2), nullable=True)
    fuente_precio = Column(Text, nullable=True)
    gestionado_por_admin = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=func.now())

    universidad = relationship("Universidad", back_populates="titulaciones")
    plan_estudios = relationship("PlanEstudios", back_populates="titulacion", uselist=False, cascade="all, delete-orphan")


class PlanEstudios(Base):
    __tablename__ = "planes_estudio"

    id = Column(Integer, primary_key=True, index=True)
    codigo_estudio = Column(String(20), ForeignKey("titulaciones.codigo_estudio", ondelete="CASCADE"), unique=True, nullable=False)
    boe_url = Column(Text)
    boe_fecha = Column(Date)
    origen_fuente = Column(String(100))
    pdf_sha256 = Column(String(64))
    fecha_procesado = Column(DateTime)
    creado_en = Column(DateTime, default=func.now())

    titulacion = relationship("Titulacion", back_populates="plan_estudios")
    resumen_creditos = relationship("ResumenCreditos", back_populates="plan_estudios", cascade="all, delete-orphan")
    elementos_curriculares = relationship("ElementoCurricular", back_populates="plan_estudios", cascade="all, delete-orphan")


class ResumenCreditos(Base):
    __tablename__ = "resumen_creditos"

    id = Column(Integer, primary_key=True, index=True)
    plan_estudio_id = Column(Integer, ForeignKey("planes_estudio.id", ondelete="CASCADE"), nullable=False)
    tipo_credito = Column(Text, nullable=False)
    cantidad_creditos = Column(Text, nullable=False)

    plan_estudios = relationship("PlanEstudios", back_populates="resumen_creditos")


class ElementoCurricular(Base):
    __tablename__ = "elementos_curriculares"

    id = Column(Integer, primary_key=True, index=True)
    plan_estudio_id = Column(Integer, ForeignKey("planes_estudio.id", ondelete="CASCADE"), nullable=False, index=True)
    modulo = Column(Text)
    materia = Column(Text)
    nombre_elemento = Column(Text, nullable=False)
    creditos_ects = Column(Text)
    caracter = Column(Text, index=True)
    curso = Column(Text)
    cuatrimestre = Column(Text)

    plan_estudios = relationship("PlanEstudios", back_populates="elementos_curriculares")


class ErrorCrawler(Base):
    __tablename__ = "errores_crawler"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime)
    fase = Column(String(100))
    id_entidad = Column(String(50))
    url = Column(Text)
    motivo_fallo = Column(Text)
    detalles_excepcion = Column(Text)


class EstadisticaRendimiento(Base):
    __tablename__ = "estadisticas_rendimiento"

    id = Column(Integer, primary_key=True, index=True)
    timestamp_reporte = Column(DateTime)
    uso_memoria_actual_mb = Column(Numeric(10, 2))
    pico_maximo_memoria_mb = Column(Numeric(10, 2))
    porcentaje_uso_memoria = Column(Numeric(5, 2))
    tiempo_total_ejecucion_seg = Column(Numeric(10, 2))
    tiempo_procesamiento_cpu_seg = Column(Numeric(10, 2))
    tiempo_espera_io_red_seg = Column(Numeric(10, 2))
    universidades_inspeccionadas = Column(Integer)
    titulaciones_inspeccionadas = Column(Integer)
    titulaciones_al_dia = Column(Integer)
    titulaciones_actualizadas = Column(Integer)
    pdfs_parseados = Column(Integer)
    errores_registrados = Column(Integer)
