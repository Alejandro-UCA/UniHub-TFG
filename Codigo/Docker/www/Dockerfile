# ==============================================================================
# Dockerfile: Portal Web Frontend (Fase 3) - Multietapa (Node 20 + Nginx)
# ==============================================================================

# ------------------------------------------------------------------------------
# ETAPA 1: Compilación de la aplicación React con Vite
# ------------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar archivos de dependencias e instalación limpia y determinista
COPY Codigo/WWW/package*.json ./
RUN npm ci --prefer-offline --no-audit

# Copiar código fuente del portal web
COPY Codigo/WWW ./

# Inyección de configuraciones dinámicas vía ARG & ENV en compilación de Vite
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

ARG VITE_ADMIN_USER
ENV VITE_ADMIN_USER=$VITE_ADMIN_USER

ARG VITE_ADMIN_FEES
ENV VITE_ADMIN_FEES=$VITE_ADMIN_FEES

ARG VITE_BECA_MEC_REFERENCE_PRICE
ENV VITE_BECA_MEC_REFERENCE_PRICE=$VITE_BECA_MEC_REFERENCE_PRICE

# Compilar bundle de producción optimizado
RUN npm run build

# ------------------------------------------------------------------------------
# ETAPA 2: Servidor Web Nginx de Producción
# ------------------------------------------------------------------------------
FROM nginx:1.25-alpine AS production

# Limpiar archivos estáticos por defecto de Nginx
RUN rm -rf /usr/share/nginx/html/*

# Copiar configuración personalizada y securizada de Nginx
COPY Codigo/Docker/www/nginx.conf /etc/nginx/conf.d/default.conf

# Copiar artefactos estáticos compilados desde la etapa builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Asegurar permisos adecuados de lectura
RUN chmod -R 755 /usr/share/nginx/html

EXPOSE 80

STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]

