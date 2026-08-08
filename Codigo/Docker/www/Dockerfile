# ==============================================================================
# Dockerfile: Portal Web Frontend (Fase 3) - Multietapa (Node 20 + Nginx)
# ==============================================================================

# ------------------------------------------------------------------------------
# ETAPA 1: Compilación de la aplicación React con Vite
# ------------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY Codigo/WWW/package*.json ./
RUN npm ci

# Copy web source code
COPY Codigo/WWW ./

# Inject Dynamic Configs via ARG & ENV
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

ARG VITE_ADMIN_USER
ENV VITE_ADMIN_USER=$VITE_ADMIN_USER

ARG VITE_ADMIN_FEES
ENV VITE_ADMIN_FEES=$VITE_ADMIN_FEES

ARG VITE_BECA_MEC_REFERENCE_PRICE
ENV VITE_BECA_MEC_REFERENCE_PRICE=$VITE_BECA_MEC_REFERENCE_PRICE

# Build production bundle
RUN npm run build

# ------------------------------------------------------------------------------
# ETAPA 2: Servidor Nginx de producción
# ------------------------------------------------------------------------------
FROM nginx:1.25-alpine AS production

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy custom Nginx configuration
COPY Codigo/Docker/www/nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled SPA static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
