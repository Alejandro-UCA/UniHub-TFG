#!/bin/bash
# ==============================================================================
# Script de Detención del Proyecto UniHub / RUCT (Linux / macOS / WSL)
# Detiene y apaga los 4 contenedores Docker
# ==============================================================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}             DETENIENDO CONTENEDORES DOCKER DE UNIHUB                 ${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "${SCRIPT_DIR}/Codigo/Docker"

docker compose down 2>/dev/null || docker-compose down

echo ""
echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}    ¡TODOS LOS CONTENEDORES DE UNIHUB SE HAN DETENIDO CORRECTAMENTE!   ${NC}"
echo -e "${GREEN}======================================================================${NC}"
