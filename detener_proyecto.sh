#!/usr/bin/env bash
# ==============================================================================
# Script de Detencion del Proyecto UniHub (Linux / POSIX Bash)
# Detiene y apaga los 4 contenedores Docker
# ==============================================================================

set -eo pipefail

echo "======================================================================"
echo "            DETENIENDO CONTENEDORES DOCKER DE UNIHUB"
echo "======================================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/Codigo/Docker"

COMPOSE_CMD="docker compose"
if ! docker compose version >/dev/null 2>&1; then
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    else
        echo "[ERROR CRITICO] No se encontro 'docker compose' ni 'docker-compose'."
        exit 1
    fi
fi

$COMPOSE_CMD down

echo ""
echo "======================================================================"
echo "   TODOS LOS CONTENEDORES DE UNIHUB SE HAN DETENIDO CORRECTAMENTE"
echo "======================================================================"
echo ""
exit 0
