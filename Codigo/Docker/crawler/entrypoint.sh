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
for value in "${ADMIN_API_KEY:-}" "${ADMIN_API_KEYS:-}" "${API_SYNC_URL:-}" "${CRAWLER_REQUEST_DELAY:-}" "${CRAWLER_API_SYNC_TIMEOUT:-}"; do
    if ! printf '%s' "$value" | awk 'NR > 1 { exit 1 }'; then
        echo "[ERROR] Las variables del crawler no pueden contener saltos de línea." >&2
        exit 1
    fi
done

PYTHON_BIN=/usr/local/bin/python
CRAWLER_USER=crawler

# El volumen de datos puede ocultar los permisos establecidos durante el build.
# Se prepara antes de ejecutar el crawler sin privilegios y se verifica de forma
# explícita para evitar fallos tardíos de SQLite como "unable to open database file".
mkdir -p /app/Datos/planes_estudio /app/Datos/logs /app/Datos/http_cache /app/temp_pdfs /home/crawler
chown -R "$CRAWLER_USER:$CRAWLER_USER" /app/Datos /app/temp_pdfs /home/crawler
if ! su -s /bin/sh "$CRAWLER_USER" -c 'test -w /app/Datos && test -w /app/Datos/planes_estudio'; then
    echo "[ERROR] El volumen /app/Datos no permite escritura al usuario crawler." >&2
    exit 1
fi

{
    printf '%s\n' "HOME=/home/crawler"
    printf '%s\n' "PYTHONUNBUFFERED=1"
    printf '%s\n' "CRAWLER_REQUEST_DELAY=${CRAWLER_REQUEST_DELAY:-1.0}"
    printf '%s\n' "ADMIN_API_KEY=${ADMIN_API_KEY:-}"
    printf '%s\n' "ADMIN_API_KEYS=${ADMIN_API_KEYS:-}"
    printf '%s\n' "API_SYNC_URL=${API_SYNC_URL:-}"
    printf '%s\n' "CRAWLER_API_SYNC_TIMEOUT=${CRAWLER_API_SYNC_TIMEOUT:-600}"
    printf '%s\n' "$CRON_SCHEDULE cd /app && export HOME=/home/crawler && $PYTHON_BIN /app/main.py >> /var/log/crawler_cron.log 2>&1"
} | crontab -u "$CRAWLER_USER" -

chown "$CRAWLER_USER:$CRAWLER_USER" /var/log/crawler_cron.log

# Ejecutar la sincronización inicial en primer plano. Si falla, el contenedor
# termina con error y Docker puede reiniciarlo; el fallo no queda oculto.
if [ "${CRAWLER_RUN_ON_STARTUP:-true}" = "true" ]; then
    echo "[INFO] Ejecutando sincronización inicial del rastreador (Fase 1 Completa)..."
    su -s /bin/sh "$CRAWLER_USER" -c "export HOME=/home/crawler && exec $PYTHON_BIN /app/main.py ${CRAWLER_PARTS_ARGS:---all}"
fi

echo "[INFO] Sincronización inicial omitida. Activando cron: ${CRON_SCHEDULE}."
exec cron -f
