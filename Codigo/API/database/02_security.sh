#!/bin/sh
set -e

echo "[INFO] Configurando Seguridad Dinámica para PostgreSQL (Fase 2)"

API_USER=${POSTGRES_API_USER:-unihub_api_user}
API_PASSWORD=${POSTGRES_API_PASSWORD:-unihub_api_password_sec2026}

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$API_USER') THEN
            CREATE ROLE "$API_USER" WITH LOGIN PASSWORD '$API_PASSWORD';
        END IF;
        
        EXECUTE 'GRANT CONNECT ON DATABASE ' || quote_ident(current_database()) || ' TO "$API_USER"';
    END
    \$\$;

    GRANT USAGE ON SCHEMA public TO "$API_USER";
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO "$API_USER";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "$API_USER";
EOSQL

echo "[INFO] Rol de solo lectura '$API_USER' configurado con éxito."
