# ==============================================================================
# Dockerfile: API REST Python / FastAPI (Fase 2)
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    netcat-openbsd \
    curl \
    gcc \
    g++ \
    libpq-dev \
    libbrotli-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Codigo/API/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY Codigo/API /app
COPY Codigo/Crawler/Datos /app/Datos

COPY Codigo/Docker/api/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
