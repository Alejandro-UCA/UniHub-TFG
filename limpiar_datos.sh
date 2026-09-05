#!/usr/bin/env bash
# ==============================================================================
# UniHub - Limpieza Total de Datos y Cache (Linux / POSIX Bash)
# ==============================================================================

set -eo pipefail

echo "======================================================================"
echo "         UNIHUB - LIMPIEZA TOTAL DE DATOS Y CACHE DEL CRAWLER"
echo "======================================================================"
echo ""
echo "Este script eliminara TODOS los archivos JSON (catalogos, planes de"
echo "estudio, precios, checkpoints y estadisticas) asi como las bases de"
echo "datos SQLite y temporales para una ejecucion 100 por ciento limpia."
echo ""

AUTO_CONFIRM=0
for arg in "$@"; do
    if [ "$arg" = "-y" ] || [ "$arg" = "--yes" ]; then
        AUTO_CONFIRM=1
    fi
done

if [ $AUTO_CONFIRM -eq 0 ]; then
    read -r -p "¿Deseas limpiar TODOS los datos y caches? (s/N): " CONFIRM
    case "$CONFIRM" in
        [sS]|[sS][iI])
            ;;
        *)
            echo ""
            echo "[CANCELADO] Operacion de limpieza cancelada por el usuario."
            echo ""
            exit 0
            ;;
    esac
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Buscar interprete Python
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_EXE="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXE="python"
else
    echo "[ERROR] No se encontro ningun interprete de Python (python3 o python)."
    exit 1
fi

echo ""
echo "Ejecutando motor seguro de limpieza con preservacion de semillas maestras..."
"$PYTHON_EXE" "$SCRIPT_DIR/Codigo/Crawler/limpieza_datos.py" --force

echo ""
echo "El entorno ha quedado completamente virgen:"
echo "  - Catalogos, planes, caches y temporales del crawler reinicializados."
echo "  - Los secretos y archivos fuera de Datos/ no se han modificado."
echo "  - Directorios de trabajo recreados para una ejecucion completa."
exit 0
