# ==============================================================================
# Dockerfile: API REST Python / FastAPI (Fase 2) - Multietapa Optimizado
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
    libpq-dev \
    libbrotli-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Codigo/API/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ------------------------------------------------------------------------------
# ETAPA 2: Entorno de Producción Liviano
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages:${PYTHONPATH}"

# Instalación exclusiva de utilidades de tiempo de ejecución
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    netcat-openbsd \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar dependencias precompiladas desde la etapa builder
COPY --from=builder /install /install

# Copiar únicamente el código fuente. Los datos se montan como volumen en runtime.
COPY Codigo/API /app

COPY Codigo/Docker/api/entrypoint.sh /app/entrypoint.sh
RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /app/Datos \
    && chown -R app:app /app \
    && sed -i -e 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
