# ==============================================================================
# Dockerfile: Rastreador / Crawler RUCT (Fase 1) - Multietapa con Cron
# ==============================================================================

# ------------------------------------------------------------------------------
# ETAPA 1: Compilación de Dependencias
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libbrotli-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Codigo/Crawler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ------------------------------------------------------------------------------
# ETAPA 2: Entorno de Producción Liviano con Cron
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages:${PYTHONPATH}"

# Instalación exclusiva de utilidades de tiempo de ejecución
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar dependencias precompiladas desde la etapa builder
COPY --from=builder /install /install

# Copiar código fuente y script de entrada
COPY Codigo/Crawler /app
COPY Codigo/Docker/crawler/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Asegurar la existencia de los directorios de almacenamiento de datos
RUN mkdir -p /app/Datos /app/Datos/Planes /app/Datos/Temp

ENTRYPOINT ["/app/entrypoint.sh"]

