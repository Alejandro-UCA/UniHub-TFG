#!/bin/bash
# ==============================================================================
# Script de Lanzamiento del Proyecto UniHub / RUCT (Linux / macOS / WSL)
# Construye e inicia los 4 contenedores Docker (Fases 1, 2 y 3)
# ==============================================================================

# Colores para la terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}          INICIANDO PROYECTO UNIHUB (RUCT) EN ENTORNO DOCKER          ${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

# 1. Verificación de permisos y ejecutable Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR CRÍTICO] Docker no está instalado en este sistema.${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}[ERROR CRÍTICO] El servicio Docker no está en ejecución o el usuario no tiene permisos suficientes.${NC}"
    echo "Intenta ejecutar el script con el servicio Docker iniciado o usando 'sudo'."
    exit 1
fi

# 2. Obtener el directorio absoluto donde reside este script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOCKER_DIR="${SCRIPT_DIR}/Codigo/Docker"

if [ ! -d "$DOCKER_DIR" ]; then
    echo -e "${RED}[ERROR CRÍTICO] No se encontró el directorio de configuración Docker en: ${DOCKER_DIR}${NC}"
    exit 1
fi

cd "$DOCKER_DIR"

echo -e "${YELLOW}[1/3] Construyendo imágenes e iniciando contenedores en segundo plano...${NC}"

if docker compose version &> /dev/null; then
    docker compose up --build -d
elif command -v docker-compose &> /dev/null; then
    docker-compose up --build -d
else
    echo -e "${RED}[ERROR CRÍTICO] No se encontró el comando 'docker compose' ni 'docker-compose'.${NC}"
    exit 1
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR CRÍTICO] Falló el arranque de los contenedores Docker.${NC}"
    exit 1
fi

echo -e "${YELLOW}[2/3] Verificando estado de los 4 contenedores...${NC}"
echo ""
docker compose ps 2>/dev/null || docker-compose ps

echo ""
echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}       ¡PROYECTO UNIHUB DESPLEGADO Y EN EJECUCIÓN EXITOSA!          ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo ""
echo "  • Portal Web Frontend (Fase 3):          http://localhost:80"
echo "  • Portal Web (Puerto Alternativo):       http://localhost:5173"
echo "  • API REST & Swagger UI (Fase 2):        http://localhost:8000/docs"
echo "  • Documentación ReDoc:                   http://localhost:8000/redoc"
echo "  • Panel de Administración & Analizador:  http://localhost/admin"
echo ""
echo -e "${GREEN}======================================================================${NC}"
