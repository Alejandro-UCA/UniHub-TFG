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

# Start FastAPI server with uvicorn and proxy headers support
echo "[INFO] Arrancando servidor Uvicorn en http://0.0.0.0:8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'

