#!/bin/sh
set -e

echo "======================================================================"
echo "   INICIANDO API REST PYTHON / FASTAPI (FASE 2)"
echo "======================================================================"

# Wait for PostgreSQL database to be ready
echo "[INFO] Esperando conexión con PostgreSQL en ${POSTGRES_HOST}:${POSTGRES_PORT}..."
while ! nc -z ${POSTGRES_HOST:-db} ${POSTGRES_PORT:-5432}; do
  sleep 1
done
echo "[INFO] Conexión establecida con la Base de Datos PostgreSQL."

# Start FastAPI server with uvicorn
echo "[INFO] Arrancando servidor Uvicorn en http://0.0.0.0:8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
