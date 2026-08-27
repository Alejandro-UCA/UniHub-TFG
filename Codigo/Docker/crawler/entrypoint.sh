#!/bin/sh
set -e

echo "======================================================================"
echo "   INICIANDO CONTENEDOR CRAWLER RUCT CON REGLA CRON (${CRAWLER_CRON_SCHEDULE:-0 2 1 * *})"
echo "======================================================================"

# Load cron schedule rule from environment variable (default to 1st day of every month at 2:00 AM)
CRON_SCHEDULE=${CRAWLER_CRON_SCHEDULE:-"0 2 1 * *"}

# Cron strips environment variables by default. We must export them so the crawler can use them.
# IMPORTANT: Use sub() to replace only the FIRST '=' so values with '=' (e.g. passwords, URLs)
# or spaces are preserved intact.
printenv | awk 'BEGIN{FS="="}{val=$0; sub(/^[^=]+=/, "", val); print "export " $1 "=" "\"" val "\""}' > /app/cron_env.sh

# Install the cron job directly to the root user's crontab, sourcing the environment first
PYTHON_BIN=$(which python || echo "/usr/local/bin/python")
echo "$CRON_SCHEDULE set -a; . /app/cron_env.sh; set +a; cd /app && $PYTHON_BIN main.py >> /var/log/crawler_cron.log 2>&1" | crontab -

# Touch log file for cron output
touch /var/log/crawler_cron.log

# Graceful termination handler
cleanup() {
    echo "[INFO] Deteniendo el demonio Cron de forma segura..."
    kill -TERM "$CRON_PID" 2>/dev/null || true
    wait "$CRON_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Run initial crawler execution in background if enabled
if [ "${CRAWLER_RUN_ON_STARTUP:-true}" = "true" ]; then
    echo "[INFO] Ejecutando sincronización inicial del rastreador al arrancar el contenedor..."
    python /app/main.py &
else
    echo "[INFO] Sincronización inicial omitida (CRAWLER_RUN_ON_STARTUP=false)."
fi

# Start cron daemon
echo "[INFO] Demonio Cron activado con programación: ${CRON_SCHEDULE}."
cron -f &
CRON_PID=$!
wait "$CRON_PID"

