# Entorno Docker y Orquestación de Servicios (Fase 4)

Este directorio contiene la arquitectura física de contenerización y la orquestación mediante **Docker Compose** para la totalidad del proyecto.

---

## 🏗️ Servicios Integrados y Puertos

| Servicio | Contenedor | Fase | Puerto Host | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **Base de Datos** | `ruct_db` | Fase 2 | `5432` | PostgreSQL 15 con esquema DDL y usuario de solo lectura `ruct_api_user`. |
| **Rastreador** | `ruct_crawler` | Fase 1 | - | Python 3.10 con **demonio Cron (`0 2 1 * *`)** y escritura atómica. |
| **API REST** | `ruct_api` | Fase 2 | `8000` | FastAPI + SQLAlchemy exponiendo endpoints de consulta, CRUD y métricas. |
| **Portal Web** | `ruct_www` | Fase 3 | `80`, `5173` | Nginx + React (Vite) con diseño UCA, geolocalización y panel admin. |

---

## 🕒 Programación Cron Automatizada (Fase 1)

El contenedor `ruct_crawler` incluye la regla de programación mensual:
```cron
0 2 1 * * (El día 1 de cada mes a las 2:00 AM)
```
Al iniciar los contenedores por primera vez, el rastreador realiza una comprobación inicial y mantiene activo el demonio `cron` para ejecutar la actualización mensual desatendida.

---

## 🔄 Concurrencia y Transaccionalidad Segura

1. **Escritura Atómica en Disco**: El rastreador escribe primero en ficheros `.tmp` y aplica `os.replace`, garantizando que la API REST o la Web nunca lean un archivo parcial mientras el crawler descarga el BOE.
2. **Aislamiento ACID en PostgreSQL**: Transacciones en SQLAlchemy que permiten consultas simultáneas en el Portal Web sin bloqueos ni inconsistencias.

---

## 📊 Medición de Recurso Físico de Contenedores

La API REST expone el endpoint `GET /api/v1/estadisticas/contenedores` que devuelve:
- **Memoria RAM Máxima (RSS MB y Peak MB)**
- **Espacio en Disco Consumido por Volúmenes (MB/GB)**
- **Uso de CPU % e Hilos de Procesamiento**
- **Partición y Espacio Libre en Disco Anfitrión**

Esta información se presenta gráficamente en la pestaña **"Salud del Rastreador y Contenedores"** del Panel del Administrador de la Web.

---

## 🚀 Puesta en Marcha

1. **Iniciar todos los servicios (Fases 1, 2, 3 y 4)**:
   ```bash
   cd d:\Proyecto\Codigo\Docker
   docker compose up --build -d
   ```

2. **Ejecutar Carga de Datos en PostgreSQL (ETL)**:
   ```bash
   docker compose exec api python database/etl_loader.py
   ```

3. **Acceso al Portal Web e Interfaz**:
   - Web Portal UCA: `http://localhost` o `http://localhost:5173`
   - Documentación Swagger API: `http://localhost:8000/docs`
   - Admin Login: `admin` / `admin_pass_2026`
