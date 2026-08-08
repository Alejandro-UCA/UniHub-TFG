#!/bin/sh
set -e

echo "======================================================================"
echo "   INICIANDO CONTENEDOR CRAWLER RUCT CON REGLA CRON (0 2 1 * *)"
echo "======================================================================"

# Load cron schedule rule from environment variable (default to 1st day of every month at 2:00 AM)
CRON_SCHEDULE=${CRAWLER_CRON_SCHEDULE:-"0 2 1 * *"}

# Cron strips environment variables by default. We must export them so the crawler can use them.
# IMPORTANT: Use sub() to replace only the FIRST '=' so values with '=' (e.g. passwords, URLs)
# or spaces (e.g. CRAWLER_CRON_SCHEDULE="0 2 1 * *") are preserved intact.
printenv | awk 'BEGIN{FS="="}{val=$0; sub(/^[^=]+=/, "", val); print "export " $1 "=" "\"" val "\""}' > /app/cron_env.sh
# Install the cron job directly to the root user's crontab, sourcing the environment first
echo "$CRON_SCHEDULE set -a; . /app/cron_env.sh; set +a; cd /app && /usr/local/bin/python main.py >> /var/log/crawler_cron.log 2>&1" | crontab -

# Touch log file for cron output
touch /var/log/crawler_cron.log

# Run initial crawler execution in background on container startup
echo "[INFO] Ejecutando sincronización inicial del rastreador al arrancar el contenedor..."
python /app/main.py &

# Start cron daemon in foreground
echo "[INFO] Demonio Cron activado (Programado: 1º de cada mes a las 2:00 AM)."
exec cron -f
