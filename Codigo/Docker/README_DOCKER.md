# Entorno Docker y Orquestación de Servicios (Fase 4)

Este directorio contiene la arquitectura física de contenerización y la orquestación mediante **Docker Compose** para la totalidad del proyecto **UniHub**.

---

## 🏗️ Servicios Integrados y Puertos

| Servicio | Contenedor | Fase | Puerto Host | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **Base de Datos** | `unihub_db` | Fase 2 | `5432` | PostgreSQL 15 con esquema DDL `01_schema.sql`, índices GIN de trigramas y usuario de solo lectura `unihub_api_user`. |
| **Rastreador** | `unihub_crawler` | Fase 1 | - | Python 3.12 con demonio Cron (`0 2 1 * *`), arquitectura multihilo de dos procesos (Red/CPU) y escritura atómica. |
| **API REST** | `unihub_api` | Fase 2 | `8000` | FastAPI + SQLAlchemy exponiendo endpoints de consulta, CRUD, métricas cgroup y sincronización reactiva `/api/v1/admin/sync-etl`. |
| **Portal Web** | `unihub_www` | Fase 3 | `80`, `5173` | Nginx + React SPA (Vite) con diseño responsive, simulador de matrícula, geolocalización Haversine y panel admin. |

---

## 🛡️ Resiliencia en Arranque desde Cero (Healthcheck & Initial DDL)

Para garantizar la puesta en marcha limpia en máquinas o volúmenes vacíos (`unihub_postgres_data`), la sonda de salud (*healthcheck*) del contenedor `unihub_db` incluye un periodo de gracia:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-unihub_db}"]
      interval: 3s
      timeout: 5s
      retries: 10
      start_period: 20s
```

*Finalidad*: Al arrancar por primera vez, PostgreSQL ejecuta el script de tablas e índices `01_schema.sql` (10-15s). El parámetro `start_period: 20s` impide que Docker declare prematuramente la base de datos como `unhealthy`, permitiendo un arranque fluido y automático de los servicios dependientes (`unihub_api` y `unihub_www`).

---

## 🕒 Programación Cron Automatizada (Fase 1)

El contenedor `unihub_crawler` incluye la regla de programación mensual:
```cron
0 2 1 * * (El día 1 de cada mes a las 2:00 AM)
```
Al iniciar los contenedores por primera vez, el rastreador realiza una comprobación inicial y mantiene activo el demonio `cron` para ejecutar la actualización mensual desatendida.

---

## 🔄 Concurrencia, Transaccionalidad y Sincronización Reactiva

1. **Escritura Atómica en Disco**: El rastreador escribe primero en ficheros `.tmp` y aplica `os.replace`, garantizando que la API REST o la Web nunca lean un archivo parcial durante la descarga del BOE.
2. **Sincronización Reactiva ETL**: Al finalizar la recolección de datos de la Fase 1, `main.py` notifica automáticamente a la API REST vía HTTP POST `http://unihub_api:8000/api/v1/admin/sync-etl` para iniciar la migración a PostgreSQL en segundo plano sin bloquear el hilo principal.
3. **Ejecución Modular por Partes**: Posibilidad de ejecutar partes específicas del crawler (`--parts 1`, `--parts 2 3` o `--parts 3`) con aislamiento de variables locales y gestión independiente de tareas.
4. **Aislamiento ACID en PostgreSQL**: Transacciones en SQLAlchemy que permiten consultas simultáneas en el Portal Web sin bloqueos ni inconsistencias.

---

## 📊 Telemetría cgroup y Métricas Green IT

La API REST expone el endpoint `GET /api/v1/estadisticas/contenedores` que devuelve:
- **Consumo de Memoria RAM Físico (RSS MB y Peak MB)**
- **Uso de CPU % e Hilos de Procesamiento por Contenedor**
- **Estimación de Huella de Carbono Green IT ($gCO_2$)**
- **Ratio de Compresión de PDFs vs JSON y Hit Ratio % de Caché**
- **Partición y Espacio Libre en Disco Anfitrión**

Toda esta información se visualiza gráficamente en el **Panel de Administración** (`http://localhost/admin`).

---

## 🚀 Puesta en Marcha

1. **Mediante Scripts de Conveniencia (Recomendado en Windows)**:
   - **Iniciar Proyecto**: `iniciar_proyecto.bat` (Construye imágenes, verifica puertos y arranca los 4 contenedores `unihub_*`).
   - **Detener Proyecto**: `detener_proyecto.bat` (Apaga contenedores y libera puertos limpios).

2. **Despliegue General con Docker Compose**:
   ```bash
   cd d:\Proyecto\Codigo\Docker
   docker compose up --build -d
   ```

3. **Despliegue Selectivo (Sin Crawler de Fase 1)**:
   ```bash
   docker compose up -d db api www
   ```

4. **Acceso al Portal Web e Interfaz**:
   - Portal Web SPA (Fase 3): `http://localhost` o `http://localhost:5173`
   - API REST & Documentación Swagger (Fase 2): `http://localhost/docs`
   - Documentación ReDoc: `http://localhost/redoc`
   - Login Administrador: configure `ADMIN_API_KEY` in your local `.env`; during rotation, `ADMIN_API_KEYS` may contain several keys separated by commas. No credential is bundled with the project.
