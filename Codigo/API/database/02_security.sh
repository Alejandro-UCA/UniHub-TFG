#!/bin/sh
set -e

echo "[INFO] Configurando Seguridad Dinámica para PostgreSQL (Fase 2)"

: "${API_DB_USER:=${POSTGRES_API_USER:-}}"
: "${API_DB_PASSWORD:=${POSTGRES_API_PASSWORD:-}}"
: "${API_DB_USER:?API_DB_USER o POSTGRES_API_USER debe configurarse}"
: "${API_DB_PASSWORD:?API_DB_PASSWORD o POSTGRES_API_PASSWORD debe configurarse}"

API_USER=$API_DB_USER
API_PASSWORD=$API_DB_PASSWORD

HOST_OPTS=""
if [ -n "$POSTGRES_HOST" ]; then
    HOST_OPTS="--host $POSTGRES_HOST --port ${POSTGRES_PORT:-5432}"
fi

SAFE_USER=$(echo "$API_USER" | sed "s/'/''/g")
SAFE_PASSWORD=$(echo "$API_PASSWORD" | sed "s/'/''/g")

psql -v ON_ERROR_STOP=1 \
    $HOST_OPTS \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${SAFE_USER}') THEN
            EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', '${SAFE_USER}', '${SAFE_PASSWORD}');
        ELSE
            EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${SAFE_USER}', '${SAFE_PASSWORD}');
        END IF;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), '${SAFE_USER}');
    END
    \$\$;

    GRANT USAGE ON SCHEMA public TO "${SAFE_USER}";
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO "${SAFE_USER}";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "${SAFE_USER}";
EOSQL

echo "[INFO] Rol de solo lectura '$API_USER' configurado con éxito."
