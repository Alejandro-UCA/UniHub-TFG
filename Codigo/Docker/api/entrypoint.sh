#!/bin/sh
set -e

echo "======================================================================"
echo "   INICIANDO API REST PYTHON / FASTAPI (FASE 2)"
echo "======================================================================"

# Wait for PostgreSQL database to be ready with bounded timeout
echo "[INFO] Esperando conexión con PostgreSQL en ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
MAX_RETRIES=60
COUNT=0
while ! nc -z ${POSTGRES_HOST:-db} ${POSTGRES_PORT:-5432}; do
  COUNT=$((COUNT + 1))
  if [ "$COUNT" -ge "$MAX_RETRIES" ]; then
    echo "[ERROR CRÍTICO] Tiempo de espera agotado (${MAX_RETRIES}s) para conectar con PostgreSQL."
    exit 1
  fi
  sleep 1
done
echo "[INFO] Conexión establecida con la Base de Datos PostgreSQL."

# Aplicar el esquema y cada migración una sola vez también sobre volúmenes ya
# existentes. El entrypoint de PostgreSQL sólo ejecuta initdb en volúmenes
# nuevos, por lo que no basta con montar estos ficheros allí.
echo "[INFO] Verificando esquema y permisos de PostgreSQL..."
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD es obligatorio}"
psql -v ON_ERROR_STOP=1 \
  --host "${POSTGRES_HOST:-db}" \
  --port "${POSTGRES_PORT:-5432}" \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "${POSTGRES_DB:-unihub_db}" \
  --file /app/database/schema.sql
psql -v ON_ERROR_STOP=1 \
  --host "${POSTGRES_HOST:-db}" \
  --port "${POSTGRES_PORT:-5432}" \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "${POSTGRES_DB:-unihub_db}" \
  --command "CREATE TABLE IF NOT EXISTS unihub_schema_migrations (version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW());"

MIGRATION_VERSION="20260828_integrity_constraints"
if ! psql -tA \
  --host "${POSTGRES_HOST:-db}" \
  --port "${POSTGRES_PORT:-5432}" \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "${POSTGRES_DB:-unihub_db}" \
  --command "SELECT 1 FROM unihub_schema_migrations WHERE version = '${MIGRATION_VERSION}'" | grep -qx "1"; then
  echo "[INFO] Aplicando migración ${MIGRATION_VERSION}..."
  psql -v ON_ERROR_STOP=1 \
    --host "${POSTGRES_HOST:-db}" \
    --port "${POSTGRES_PORT:-5432}" \
    --username "${POSTGRES_USER:-postgres}" \
    --dbname "${POSTGRES_DB:-unihub_db}" \
    --file /app/database/03_schema_migrations.sql
  psql -v ON_ERROR_STOP=1 \
    --host "${POSTGRES_HOST:-db}" \
    --port "${POSTGRES_PORT:-5432}" \
    --username "${POSTGRES_USER:-postgres}" \
    --dbname "${POSTGRES_DB:-unihub_db}" \
    --command "INSERT INTO unihub_schema_migrations (version) VALUES ('${MIGRATION_VERSION}')"
fi
API_DB_USER="${API_DB_USER:-${POSTGRES_API_USER:-}}" \
API_DB_PASSWORD="${API_DB_PASSWORD:-${POSTGRES_API_PASSWORD:-}}" \
  sh /app/database/02_security.sh
unset PGPASSWORD

# Start FastAPI server without trusting forwarded headers from arbitrary clients.
echo "[INFO] Arrancando servidor Uvicorn en http://0.0.0.0:8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
