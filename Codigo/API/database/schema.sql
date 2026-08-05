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
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla de Planes de Estudio (Metadatos BOE por Titulación)
CREATE TABLE IF NOT EXISTS planes_estudio (
    id SERIAL PRIMARY KEY,
    codigo_estudio VARCHAR(20) UNIQUE REFERENCES titulaciones(codigo_estudio) ON DELETE CASCADE,
    boe_url TEXT,
    boe_fecha DATE,
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
    modulo VARCHAR(500),
    materia VARCHAR(500),
    nombre_elemento TEXT NOT NULL,
    creditos_ects VARCHAR(50),
    caracter VARCHAR(100),
    curso VARCHAR(50),
    cuatrimestre VARCHAR(50)
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
-- SEGURIDAD: ROL DE SOLO LECTURA PARA LA API REST ('ruct_api_user')
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ruct_api_user') THEN
        CREATE ROLE ruct_api_user WITH LOGIN PASSWORD 'ruct_api_password_sec2026';
    END IF;
END
$$;

-- Otorgar únicamente acceso SELECT al rol de la API
GRANT CONNECT ON DATABASE ruct_db TO ruct_api_user;
GRANT USAGE ON SCHEMA public TO ruct_api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ruct_api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ruct_api_user;
