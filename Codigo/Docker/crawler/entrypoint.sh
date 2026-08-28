#!/bin/sh
set -eu

echo "======================================================================"
echo "   INICIANDO CONTENEDOR CRAWLER RUCT"
echo "======================================================================"

# Validar el schedule antes de pasarlo a crontab. Solo se permiten los cinco
# campos cron básicos y caracteres de datos; nunca se evalúa como shell.
CRON_SCHEDULE=${CRAWLER_CRON_SCHEDULE:-"0 2 1 * *"}
# Evitar que los asteriscos del schedule sufran expansión de pathname.
set -f
set -- $CRON_SCHEDULE
if [ "$#" -ne 5 ]; then
    echo "[ERROR] CRAWLER_CRON_SCHEDULE debe contener exactamente cinco campos." >&2
    exit 1
fi
for field in "$@"; do
    case "$field" in
        ''|*[!0-9*/,-]*)
            echo "[ERROR] CRAWLER_CRON_SCHEDULE contiene caracteres no permitidos." >&2
            exit 1
            ;;
    esac
done
CRON_SCHEDULE="$*"

# Las variables se escriben como asignaciones propias de crontab. No se genera
# ni se carga código shell a partir de printenv o de valores externos.
for value in "${ADMIN_API_KEY:-}" "${ADMIN_API_KEYS:-}" "${API_SYNC_URL:-}" "${CRAWLER_REQUEST_DELAY:-}"; do
    if ! printf '%s' "$value" | awk 'NR > 1 { exit 1 }'; then
        echo "[ERROR] Las variables del crawler no pueden contener saltos de línea." >&2
        exit 1
    fi
done

PYTHON_BIN=/usr/local/bin/python
CRAWLER_USER=crawler
{
    printf '%s\n' "PYTHONUNBUFFERED=1"
    printf '%s\n' "CRAWLER_REQUEST_DELAY=${CRAWLER_REQUEST_DELAY:-1.0}"
    printf '%s\n' "ADMIN_API_KEY=${ADMIN_API_KEY:-}"
    printf '%s\n' "ADMIN_API_KEYS=${ADMIN_API_KEYS:-}"
    printf '%s\n' "API_SYNC_URL=${API_SYNC_URL:-}"
    printf '%s\n' "$CRON_SCHEDULE cd /app && $PYTHON_BIN /app/main.py >> /var/log/crawler_cron.log 2>&1"
} | crontab -u "$CRAWLER_USER" -

chown "$CRAWLER_USER:$CRAWLER_USER" /var/log/crawler_cron.log

# Ejecutar la sincronización inicial en primer plano. Si falla, el contenedor
# termina con error y Docker puede reiniciarlo; el fallo no queda oculto.
if [ "${CRAWLER_RUN_ON_STARTUP:-true}" = "true" ]; then
    echo "[INFO] Ejecutando sincronización inicial del rastreador..."
    su -s /bin/sh "$CRAWLER_USER" -c "exec $PYTHON_BIN /app/main.py"
fi

echo "[INFO] Sincronización inicial omitida. Activando cron: ${CRON_SCHEDULE}."
exec cron -f
