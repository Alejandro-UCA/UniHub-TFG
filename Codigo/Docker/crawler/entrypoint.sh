#!/bin/sh
set -e

echo "======================================================================"
echo "   INICIANDO CONTENEDOR CRAWLER RUCT CON REGLA CRON (0 2 1 * *)"
echo "======================================================================"

# Write cron schedule rule: 1st day of every month at 2:00 AM (0 2 1 * *)
echo "0 2 1 * * root cd /app && /usr/local/bin/python main.py >> /var/log/crawler_cron.log 2>&1" > /etc/cron.d/crawler-cron
chmod 0644 /etc/cron.d/crawler-cron
crontab /etc/cron.d/crawler-cron

# Touch log file for cron output
touch /var/log/crawler_cron.log

# Run initial crawler execution in background on container startup
echo "[INFO] Ejecutando sincronización inicial del rastreador al arrancar el contenedor..."
python /app/main.py &

# Start cron daemon in foreground
echo "[INFO] Demonio Cron activado (Programado: 1º de cada mes a las 2:00 AM)."
exec cron -f
