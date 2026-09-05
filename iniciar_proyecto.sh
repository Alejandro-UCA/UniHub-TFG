#!/usr/bin/env bash
# ==============================================================================
# Script de Lanzamiento del Proyecto UniHub (Linux / POSIX Bash)
# Construye e inicia los 4 contenedores Docker (Fases 1, 2, 3 y 4)
# ==============================================================================

set -eo pipefail

echo "======================================================================"
echo "         INICIANDO PROYECTO UNIHUB EN ENTORNO DOCKER (LINUX)"
echo "======================================================================"
echo ""

# 1. Verificacion de Docker en ejecucion
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR CRITICO] El demonio de Docker no se encuentra en ejecucion."
    echo "Por favor, inicia el servicio de Docker (p. ej. 'sudo systemctl start docker') o comprueba permisos de usuario."
    echo ""
    exit 1
fi

# 2. Navegar a la carpeta de configuracion Docker
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/Codigo/Docker"

# 3. Determinar comando compose
COMPOSE_CMD="docker compose"
if ! docker compose version >/dev/null 2>&1; then
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    else
        echo "[ERROR CRITICO] No se encontro 'docker compose' ni 'docker-compose'."
        exit 1
    fi
fi

echo "[1/3] Construyendo imagenes e iniciando contenedores en segundo plano..."
$COMPOSE_CMD up --build -d

echo ""
echo "[2/3] Esperando a que los servicios alcancen un estado saludable..."
echo ""

WAIT_SECONDS=0
MAX_WAIT=120

while [ $WAIT_SECONDS -lt $MAX_WAIT ]; do
    FAILED_SERVICES=$($COMPOSE_CMD ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null | grep -Ei 'exited|dead|unhealthy' || true)
    if [ -n "$FAILED_SERVICES" ]; then
        echo "[ERROR CRITICO] Al menos un contenedor esta detenido o no saludable:"
        echo "$FAILED_SERVICES"
        exit 1
    fi

    STARTING_SERVICES=$($COMPOSE_CMD ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep -i 'starting' || true)
    if [ -z "$STARTING_SERVICES" ]; then
        break
    fi

    sleep 5
    WAIT_SECONDS=$((WAIT_SECONDS + 5))
done

if [ $WAIT_SECONDS -ge $MAX_WAIT ]; then
    echo "[ADVERTENCIA] Los contenedores tardaron mas de ${MAX_WAIT}s en reportar salud, verificando estado..."
fi

echo ""
$COMPOSE_CMD ps

echo ""
echo "======================================================================"
echo "      ¡PROYECTO UNIHUB DESPLEGADO Y EN EJECUCION EXITOSA!"
echo "======================================================================"
echo ""
echo "  * Portal Web Frontend (Fase 3):          http://localhost:80"
echo "  * API REST & Swagger UI (Fase 2):        http://localhost/docs"
echo "  * Documentacion ReDoc:                   http://localhost/redoc"
echo "  * Panel de Administracion:               http://localhost/admin"
echo ""
echo "======================================================================"
exit 0
