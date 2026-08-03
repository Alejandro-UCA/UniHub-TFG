# ==============================================================================
# Dockerfile: Rastreador / Crawler RUCT (Fase 1) con Cron (0 2 1 * *)
# ==============================================================================
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies including cron
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    gcc \
    g++ \
    libbrotli-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy crawler requirements first for caching
COPY Codigo/Crawler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy crawler application code and entrypoint
COPY Codigo/Crawler /app
COPY Codigo/Docker/crawler/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Ensure data output directory exists
RUN mkdir -p /app/Datos /app/Datos/Planes /app/Datos/Temp

# Entrypoint script runs initial sync and starts cron daemon
ENTRYPOINT ["/app/entrypoint.sh"]
