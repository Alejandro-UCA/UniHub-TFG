# ==============================================================================
# Dockerfile: Rastreador / Crawler RUCT (Fase 1)
# ==============================================================================
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies (curl, build tools for pdf processing if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    libbrotli-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy crawler requirements first for caching
COPY Codigo/Crawler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy crawler application code
COPY Codigo/Crawler /app

# Ensure data output directory exists
RUN mkdir -p /app/Datos /app/Datos/Planes /app/Datos/Temp

# Command to execute crawler
CMD ["python", "main.py"]
