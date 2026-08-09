-- =====================================================================
-- ESQUEMA BASE DE DATOS POSTGRESQL - RUCT UNIVERSIDADES Y TITULACIONES
-- =====================================================================

-- 1. Tabla de Universidades (Públicas y Privadas)
CREATE TABLE IF NOT EXISTS universidades (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(10) UNIQUE NOT NULL,
    nombre VARCHAR(500) NOT NULL,
    tipo VARCHAR(50),
    comunidad_autonoma VARCHAR(100),
    municipio VARCHAR(100),
    provincia VARCHAR(100),
    web VARCHAR(500),
    email VARCHAR(255),
    telefono VARCHAR(50),
    gestionado_por_admin BOOLEAN DEFAULT FALSE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla de Titulaciones (Grados, Másteres, Doctorados Vigentes)
CREATE TABLE IF NOT EXISTS titulaciones (
    id SERIAL PRIMARY KEY,
    codigo_estudio VARCHAR(20) UNIQUE NOT NULL,
    titulo TEXT NOT NULL,
    nivel_academico VARCHAR(200),
    estado VARCHAR(100),
    universidad_codigo VARCHAR(10) REFERENCES universidades(codigo) ON DELETE CASCADE,
    precio_credito_ects NUMERIC(6, 2),
    precio_credito_2 NUMERIC(6, 2),
    precio_credito_3 NUMERIC(6, 2),
    precio_credito_4 NUMERIC(6, 2),
    precio_estimado_anual NUMERIC(8, 2),
    fuente_precio VARCHAR(255),
    gestionado_por_admin BOOLEAN DEFAULT FALSE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla de Planes de Estudio (Metadatos BOE por Titulación)
CREATE TABLE IF NOT EXISTS planes_estudio (
    id SERIAL PRIMARY KEY,
    codigo_estudio VARCHAR(20) UNIQUE REFERENCES titulaciones(codigo_estudio) ON DELETE CASCADE,
    boe_url TEXT,
    boe_fecha DATE,
    origen_fuente VARCHAR(100),
    pdf_sha256 VARCHAR(64),
    fecha_procesado TIMESTAMP,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabla de Resumen de Créditos ECTS
CREATE TABLE IF NOT EXISTS resumen_creditos (
    id SERIAL PRIMARY KEY,
    plan_estudio_id INT REFERENCES planes_estudio(id) ON DELETE CASCADE,
    tipo_credito VARCHAR(200) NOT NULL,
    cantidad_creditos VARCHAR(50) NOT NULL
);

-- 5. Tabla de Elementos Curriculares (Asignaturas, Módulos, Materias, Bloques)
CREATE TABLE IF NOT EXISTS elementos_curriculares (
    id SERIAL PRIMARY KEY,
    plan_estudio_id INT REFERENCES planes_estudio(id) ON DELETE CASCADE,
    modulo TEXT,
    materia TEXT,
    nombre_elemento TEXT NOT NULL,
    creditos_ects TEXT,
    caracter TEXT,
    curso TEXT,
    cuatrimestre TEXT
);

-- 6. Tabla de Registro de Errores del Crawler
CREATE TABLE IF NOT EXISTS errores_crawler (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    fase VARCHAR(100),
    id_entidad VARCHAR(50),
    url TEXT,
    motivo_fallo TEXT,
    detalles_excepcion TEXT
);

-- 7. Tabla de Estadísticas de Rendimiento
CREATE TABLE IF NOT EXISTS estadisticas_rendimiento (
    id SERIAL PRIMARY KEY,
    timestamp_reporte TIMESTAMP,
    uso_memoria_actual_mb NUMERIC(10, 2),
    pico_maximo_memoria_mb NUMERIC(10, 2),
    porcentaje_uso_memoria NUMERIC(5, 2),
    tiempo_total_ejecucion_seg NUMERIC(10, 2),
    tiempo_procesamiento_cpu_seg NUMERIC(10, 2),
    tiempo_espera_io_red_seg NUMERIC(10, 2),
    universidades_inspeccionadas INT,
    titulaciones_inspeccionadas INT,
    titulaciones_al_dia INT,
    titulaciones_actualizadas INT,
    pdfs_parseados INT,
    errores_registrados INT
);

-- Extension de Trigramas para busquedas de texto ultra rapidas
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Indices de rendimiento para consultas de la API REST
CREATE INDEX IF NOT EXISTS idx_univ_codigo ON universidades(codigo);
CREATE INDEX IF NOT EXISTS idx_univ_nombre_trgm ON universidades USING gin (nombre gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tit_univ ON titulaciones(universidad_codigo);
CREATE INDEX IF NOT EXISTS idx_tit_nivel ON titulaciones(nivel_academico);
CREATE INDEX IF NOT EXISTS idx_tit_titulo_trgm ON titulaciones USING gin (titulo gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_elem_plan ON elementos_curriculares(plan_estudio_id);
CREATE INDEX IF NOT EXISTS idx_elem_caracter ON elementos_curriculares(caracter);

-- =====================================================================
-- SEGURIDAD:
-- La creación del rol de solo lectura y asignación de permisos 
-- se ha movido al script '02_security.sh' para soportar variables de entorno.
-- =====================================================================
