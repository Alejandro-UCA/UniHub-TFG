# Guía de Gestión e Instalación del Sistema Docker (Fase 4)

Este directorio (`d:\Proyecto\Codigo\Docker\`) contiene la configuración y los artefactos de la **Fase 4** del proyecto. Permite desplegar de forma contenerizada y orquestada los 4 servicios del sistema mediante **Docker** y **Docker Compose**.

---

## 🏛️ Arquitectura de los Contenedores

| Servicio | Nombre Contenedor | Imagen / Dockerfile | Puerto Host | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **`db`** | `ruct_db` | `postgres:15-alpine` | `5432` | Base de datos PostgreSQL con DDL y usuario de solo lectura `ruct_api_user` inicializados automáticamente. |
| **`api`** | `ruct_api` | `api/Dockerfile` | `8000` | API REST en Python / FastAPI con conexión a PostgreSQL y salud comprobada mediante *healthcheck*. |
| **`www`** | `ruct_www` | `www/Dockerfile` | `80`, `5173` | Portal Web (SPA React) servido por Nginx de producción con proxy inverso hacia `http://api:8000/api/v1`. |
| **`crawler`** | `ruct_crawler` | `crawler/Dockerfile` | - | Rastreador Python (Fase 1) en contenedor aislado con volumen de datos compartido. |

---

## 🚀 Guía de Despliegue con Docker Compose

### 1. Construir y Levantar el Sistema (Base de Datos + API + Portal Web)
Abra una consola en la carpeta `d:\Proyecto\Codigo\Docker\` y ejecute:

```bash
cd d:\Proyecto\Codigo\Docker
docker compose up --build -d
```

Este comando:
1. Creará la red privada `ruct_network` y los volúmenes persistentes `ruct_postgres_data` y `ruct_datos_volume`.
2. Iniciará el contenedor de base de datos `ruct_db` e importará el esquema DDL `schema.sql`.
3. Esperará a que la base de datos esté lista (*healthcheck*) para iniciar la API `ruct_api`.
4. Compilará la aplicación React en Nginx e iniciará el portal web `ruct_www`.

---

### 2. Verificar el Estado de los Contenedores

```bash
docker compose ps
```

Debe observar los contenedores `ruct_db`, `ruct_api` y `ruct_www` en estado `running` (healthy).

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

- 🌐 **Portal Web (Fase 3 - UCA Style)**: [http://localhost](http://localhost) o [http://localhost:5173](http://localhost:5173)
- ⚡ **API REST Documentación Swagger UI (Fase 2)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 📄 **API REST Documentación ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### 6. Revisar Registros / Logs en Tiempo Real

- Logs de todos los servicios:
  ```bash
  docker compose logs -f
  ```
- Logs de la API REST:
  ```bash
  docker compose logs -f api
  ```
- Logs del Servidor Web Nginx:
  ```bash
  docker compose logs -f www
  ```

---

### 7. Detener y Limpiar el Entorno Docker

- **Detener servicios manteniendo los datos**:
  ```bash
  docker compose down
  ```
- **Detener servicios y eliminar volúmenes (Reiniciar desde cero)**:
  ```bash
  docker compose down -v
  ```
