#!/bin/sh
set -e

echo "[INFO] Configurando Seguridad Dinámica para PostgreSQL (Fase 2)"

: "${API_DB_USER:=${POSTGRES_API_USER:-}}"
: "${API_DB_PASSWORD:=${POSTGRES_API_PASSWORD:-}}"
: "${API_DB_USER:?API_DB_USER o POSTGRES_API_USER debe configurarse}"
: "${API_DB_PASSWORD:?API_DB_PASSWORD o POSTGRES_API_PASSWORD debe configurarse}"

API_USER=$API_DB_USER
API_PASSWORD=$API_DB_PASSWORD

psql -v ON_ERROR_STOP=1 \
    -v api_user="$API_USER" \
    -v api_password="$API_PASSWORD" \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'api_user') THEN
            EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'api_user', :'api_password');
        ELSE
            EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'api_user', :'api_password');
        END IF;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'api_user');
    END
    \$\$;

    GRANT USAGE ON SCHEMA public TO :"api_user";
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"api_user";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO :"api_user";
EOSQL

echo "[INFO] Rol de solo lectura '$API_USER' configurado con éxito."
