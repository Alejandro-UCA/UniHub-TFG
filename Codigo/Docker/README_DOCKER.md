# Guía de Gestión e Instalación del Sistema Docker (Fase 4)

Este directorio (`d:\Proyecto\Codigo\Docker\`) contiene la configuración y los artefactos de la **Fase 4** del proyecto. Permite desplegar de forma contenerizada y orquestada los 4 servicios del sistema mediante **Docker** y **Docker Compose**.

---

## 🏛️ Arquitectura de Contenedores y Persistencia Permanente de Datos

| Servicio | Nombre Contenedor | Imagen / Dockerfile | Puerto Host | Estrategia de Persistencia Permanente |
| :--- | :--- | :--- | :--- | :--- |
| **`db`** | `ruct_db` | `postgres:15-alpine` | `5432` | **Volumen Nominado `postgres_data`**: Mantiene intactas las tablas y registros relacionales de PostgreSQL al reiniciar o apagar el contenedor. |
| **`api`** | `ruct_api` | `api/Dockerfile` | `8000` | **Montaje Directo de Host `../Crawler/Datos`**: Acceso y lectura directa sobre los archivos `.json` persistentes en el disco del host. |
| **`www`** | `ruct_www` | `www/Dockerfile` | `80`, `5173` | **Servidor Nginx**: Sirve los estáticos y redirige llamadas API vía proxy inverso. |
| **`crawler`** | `ruct_crawler` | `crawler/Dockerfile` | - | **Montaje Directo de Host `../Crawler/Datos`**: Todos los archivos `.json` descargados, planes BOE, `checkpoint.json` y `estadisticas_rendimiento.json` se guardan en el disco físico local. |

---

## 🚀 Guía de Despliegue con Docker Compose

### 1. Construir y Levantar el Sistema (Base de Datos + API + Portal Web)
Abra una consola en la carpeta `d:\Proyecto\Codigo\Docker\` y ejecute:

```bash
cd d:\Proyecto\Codigo\Docker
docker compose up --build -d
```

Este comando:
1. Creará la red privada `ruct_network` y asegurará el volumen de persistencia `postgres_data` y la carpeta de datos en el host `Codigo/Crawler/Datos`.
2. Iniciará el contenedor de base de datos `ruct_db` e importará el esquema DDL `schema.sql`.
3. Esperará a que la base de datos esté lista (*healthcheck*) para iniciar la API `ruct_api`.
4. Compilará la aplicación React en Nginx e iniciará el portal web `ruct_www`.

---

### 2. Verificar la Persistencia de Datos
Aunque cierre los contenedores con `docker compose down` o reinicie el sistema, **toda la información recopilada se conserva permanentemente**:
- **Archivos JSON del Rastreador y BOE PDFs**: Permanecen almacenados físicamente en `d:\Proyecto\Codigo\Crawler\Datos\`.
- **Base de Datos PostgreSQL**: Se conserva íntegra en el volumen de Docker `ruct_postgres_data`.

---

### 3. Cargar Datos JSON a PostgreSQL (ETL Loader)

Para migrar la información extraída a la base de datos PostgreSQL dentro de la red Docker:

```bash
docker compose exec api python database/etl_loader.py
```

---

### 4. Ejecutar el Rastreador / Crawler (Fase 1)

Para ejecutar el rastreador dentro de su contenedor aislado:

```bash
docker compose --profile crawler run --rm crawler python main.py
```

---

### 5. Acceso a los Servicios desde el Navegador

- 🌐 **Portal Web (Fase 3 - Estilo UCA)**: [http://localhost](http://localhost) o [http://localhost:5173](http://localhost:5173)
- ⚡ **API REST Documentación Swagger UI (Fase 2)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 📄 **API REST Documentación ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### 6. Detener los Contenedores MANTENIENDO los Datos Intactos

- **Detener servicios (los datos se conservan al 100%)**:
  ```bash
  docker compose down
  ```
