# ==============================================================================
# Dockerfile: Portal Web Frontend (Fase 3) - Multietapa (Node + Nginx)
# ==============================================================================

# ------------------------------------------------------------------------------
# ETAPA 1: Compilación de la aplicación React con Vite
# ------------------------------------------------------------------------------
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY Codigo/WWW/package*.json ./
RUN npm ci

# Copy web source code and build production bundle
COPY Codigo/WWW ./
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
