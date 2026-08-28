-- =====================================================================
-- Migraciones de integridad compatibles con el modelo SQLAlchemy.
-- Este fichero se ejecuta tanto en volúmenes nuevos como existentes.
-- =====================================================================

-- Las ampliaciones de tamaño y cambios de tipo no destruyen información.
ALTER TABLE IF EXISTS universidades
    ALTER COLUMN tipo TYPE VARCHAR(100),
    ALTER COLUMN comunidad_autonoma TYPE VARCHAR(200),
    ALTER COLUMN municipio TYPE VARCHAR(200),
    ALTER COLUMN provincia TYPE VARCHAR(200),
    ALTER COLUMN email TYPE VARCHAR(500),
    ALTER COLUMN telefono TYPE VARCHAR(200);

ALTER TABLE IF EXISTS titulaciones
    ALTER COLUMN nivel_academico TYPE TEXT,
    ALTER COLUMN estado TYPE VARCHAR(200);

-- No se inventan relaciones para reparar datos antiguos: si existen filas
-- incompletas, el arranque falla con un diagnóstico explícito.
DO $$
DECLARE
    invalid_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO invalid_count FROM titulaciones WHERE universidad_codigo IS NULL;
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'Migración detenida: % titulaciones no tienen universidad_codigo.', invalid_count;
    END IF;

    SELECT COUNT(*) INTO invalid_count FROM planes_estudio WHERE codigo_estudio IS NULL;
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'Migración detenida: % planes_estudio no tienen codigo_estudio.', invalid_count;
    END IF;

    SELECT COUNT(*) INTO invalid_count FROM resumen_creditos
        WHERE plan_estudio_id IS NULL OR tipo_credito IS NULL OR cantidad_creditos IS NULL;
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'Migración detenida: % filas de resumen_creditos incumplen integridad.', invalid_count;
    END IF;

    SELECT COUNT(*) INTO invalid_count FROM elementos_curriculares
        WHERE plan_estudio_id IS NULL OR nombre_elemento IS NULL;
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'Migración detenida: % elementos_curriculares incumplen integridad.', invalid_count;
    END IF;
END $$;

ALTER TABLE IF EXISTS titulaciones
    ALTER COLUMN universidad_codigo SET NOT NULL;

ALTER TABLE IF EXISTS planes_estudio
    ALTER COLUMN codigo_estudio SET NOT NULL;

ALTER TABLE IF EXISTS resumen_creditos
    ALTER COLUMN plan_estudio_id SET NOT NULL,
    ALTER COLUMN tipo_credito SET NOT NULL,
    ALTER COLUMN cantidad_creditos SET NOT NULL;

ALTER TABLE IF EXISTS elementos_curriculares
    ALTER COLUMN plan_estudio_id SET NOT NULL,
    ALTER COLUMN nombre_elemento SET NOT NULL;
