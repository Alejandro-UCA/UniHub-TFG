# 📖 Catálogo Completo de Comandos del Proyecto UniHub

Este documento recopila todos los comandos, parámetros, filtros y opciones de ejecución disponibles en las cuatro fases de la plataforma **UniHub**.

---

## 🕷️ 1. Fase 1: Extracción, Scraping y Parsers (`Codigo/Crawler/`)

El punto de entrada principal es `main.py`. Soporta ejecución integral o modular mediante argumentos de línea de comandos.

### 🔹 Ejecución Estándar (Las 3 Partes Consecutivas)
```bash
cd Codigo/Crawler
python main.py
```
> Ejecuta en secuencia:
> 1. **Parte 1:** Scraping oficial RUCT + Descarga y parsing de PDFs del BOE central con pool multiproceso CPU.
> 2. **Parte 2:** Rascado web de portales universitarios, sitemaps XML y boletines autonómicos (BOJA, DOGC, BOCM, etc.).
> 3. **Parte 3:** Ingesta de precios públicos por crédito ECTS según decretos autonómicos y fijación de tarifas privadas.

---

### 🔹 Filtros y Opciones de Línea de Comandos (`main.py`)

| Parámetro | Tipo | Descripción | Ejemplo |
| :--- | :---: | :--- | :--- |
| `--limit-univ <N>` | Entero | Procesa únicamente las primeras `N` universidades del catálogo oficial. | `python main.py --limit-univ 3` |
| `--limit-degrees <N>` | Entero | Procesa únicamente `N` titulaciones por cada universidad inspeccionada. | `python main.py --limit-degrees 5` |
| `--only-part <1\|2\|3>` | Entero | Ejecuta de forma exclusiva la parte seleccionada (1: RUCT/BOE, 2: Web, 3: Precios). | `python main.py --only-part 1` |
| `--parts <1 2 3>` | Lista | Ejecuta una combinación personalizada de partes de la Fase 1. | `python main.py --parts 1 2` |
| `--force` | Flag | **Fuerza la re-descarga y re-procesamiento** de todas las titulaciones ignorando la caché de fechas del BOE. | `python main.py --force` |

---

### 🔹 Ejemplos Prácticos de Ejecución Filtrada

* **Prueba rápida (1 universidad, 3 titulaciones):**
  ```bash
  python main.py --limit-univ 1 --limit-degrees 3
  ```
* **Ejecutar solo la Parte 1 (Scraping oficial RUCT y BOE):**
  ```bash
  python main.py --only-part 1
  ```
* **Ejecutar solo las Partes 1 y 2 (sin actualización de precios):**
  ```bash
  python main.py --parts 1 2
  ```
* **Re-procesar 100% del catálogo desde cero forzando el nuevo parser:**
  ```bash
  python main.py --force
  ```

---

### 🔹 Ejecución Aislada de Módulos Específicos

* **Ejecutar únicamente el Rascado Web Universitario (Parte 2):**
  ```bash
  python univ_web_crawler.py
  ```
* **Ejecutar únicamente la Actualización de Precios ECTS (Parte 3):**
  ```bash
  python precios_crawler.py
  ```

---

## 🗄️ 2. Fase 2: API REST y Base de Datos PostgreSQL (`Codigo/API/`)

### 🔹 Iniciar Servidor de la API en Desarrollo Local
```bash
cd Codigo/API
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
* **Documentación interactiva Swagger UI:** `http://localhost:8000/docs`
* **Documentación OpenAPI ReDoc:** `http://localhost:8000/redoc`

### 🔹 Carga y Migración ETL (JSONs $\rightarrow$ PostgreSQL)
```bash
cd Codigo/API
python database/etl_loader.py
```
> Lee los datos generados por el crawler en `Codigo/Crawler/Datos/` y los inserta de forma transaccional y acelerada (`bulk_save_objects`) en PostgreSQL con control de cerrojo de concurrencia PID.

---

## 💻 3. Fase 3: Frontend Web React SPA (`Codigo/WWW/`)

```bash
cd Codigo/WWW
```

* **Instalar dependencias:**
  ```bash
  npm install
  ```
* **Iniciar servidor de desarrollo con Hot Reload (Vite):**
  ```bash
  npm run dev
  ```
  *(Disponible en `http://localhost:5173` o `http://localhost:3000`)*
* **Compilar para producción (HTML, CSS y JS optimizados en `dist/`):**
  ```bash
  npm run build
  ```
* **Previsualizar la compilación de producción:**
  ```bash
  npm run preview
  ```
* **Auditoría de código estático (Linter):**
  ```bash
  npm run lint
  ```

---

## 🐳 4. Fase 4: Despliegue con Docker y Docker Compose (`Codigo/Docker/`)

Todos los comandos de Docker se pueden ejecutar desde la raíz del proyecto usando el flag `-f`:

### 🔹 Gestión Completa del Entorno Multicontenedor

* **Construir y levantar todos los servicios en segundo plano:**
  ```bash
  docker compose -f Codigo/Docker/docker-compose.yml up -d --build
  ```
* **Detener todos los servicios:**
  ```bash
  docker compose -f Codigo/Docker/docker-compose.yml down
  ```
* **Detener y eliminar volúmenes de datos (reinicio total de base de datos):**
  ```bash
  docker compose -f Codigo/Docker/docker-compose.yml down -v
  ```
* **Ver estado de los contenedores en ejecución:**
  ```bash
  docker compose -f Codigo/Docker/docker-compose.yml ps
  ```
* **Monitoreo de recursos (CPU / RAM en tiempo real):**
  ```bash
  docker stats unihub_db unihub_crawler unihub_api unihub_www
  ```

---

### 🔹 Gestión por Servicio Individual

| Servicio | Comando de Arranque / Reconstrucción | Comando de Logs en Vivo |
| :--- | :--- | :--- |
| **Crawler (Fase 1)** | `docker compose -f Codigo/Docker/docker-compose.yml up -d --build crawler` | `docker logs -f unihub_crawler` |
| **API REST (Fase 2)** | `docker compose -f Codigo/Docker/docker-compose.yml up -d --build api` | `docker logs -f unihub_api` |
| **Frontend WWW (Fase 3)** | `docker compose -f Codigo/Docker/docker-compose.yml up -d --build www` | `docker logs -f unihub_www` |
| **PostgreSQL (BD)** | `docker compose -f Codigo/Docker/docker-compose.yml up -d --build db` | `docker logs -f unihub_db` |

---

### 🔹 Disparar Tareas Dentro de los Contenedores

* **Ejecutar la ingesta ETL en la base de datos dentro del contenedor API:**
  ```bash
  docker compose -f Codigo/Docker/docker-compose.yml exec api python database/etl_loader.py
  ```
* **Abrir una terminal interactiva dentro de un contenedor:**
  ```bash
  docker exec -it unihub_crawler /bin/sh
  docker exec -it unihub_api /bin/sh
  ```

---

## ⚡ 5. Scripts Automatizados en la Raíz del Proyecto

Para simplificar la administración y ejecución en sistemas Windows:

* **Iniciar el proyecto completo:**
  ```cmd
  iniciar_proyecto.bat
  ```
  *(Verifica Docker, compila imágenes, inicializa base de datos, API y Frontend en `http://localhost:3000`)*

* **Detener el proyecto completamente:**
  ```cmd
  detener_proyecto.bat
  ```
  *(Apaga ordenadamente los 4 contenedores y libera los puertos del sistema)*

* **Ejecutar la Fase 1 Parte 1 (Scraping oficial RUCT + Parsing BOE):**
  ```cmd
  ejecutar_fase1_parte1.bat
  ```
  *(Lanza la recolección oficial y admite parámetros adicionales, ej. `ejecutar_fase1_parte1.bat --limit-univ 5`)*

* **Limpieza total de datos y caché para ejecución limpia desde cero:**
  ```cmd
  limpiar_datos.bat
  ```
  *(Vacía `planes_estudio/`, elimina la base de datos de caché SQLite WAL y deja el entorno preparado para reconstruir el 100% del catálogo sin datos residuales)*

---

## 🧪 6. Suites de Pruebas Automatizadas (`Codigo/Pruebas/`)

```bash
cd Codigo/Pruebas
```

* **Suite de Verificación Integral End-to-End (14/14 Tests):**
  ```bash
  python test_verification_suite.py
  ```
* **Suite Exhaustiva de Frontend SPA y Seguridad (15/15 Tests):**
  ```bash
  python test_fase3_exhaustive.py
  ```
* **Suite de Regresión y Precisión de Parsers Curriculares:**
  ```bash
  python test_parser_regression.py
  ```
* **Suite de Desambiguación Multi-Titulación y Macro-Resoluciones BOE:**
  ```bash
  python test_multi_degree_boe.py
  ```
* **Suite de Auditoría Detallada sobre Universidades Reales:**
  ```bash
  python run_phase1_detailed_test.py
  ```
* **Ejecutar todas las suites de prueba en un solo comando:**
  ```bash
  python test_verification_suite.py; python test_fase3_exhaustive.py; python test_parser_regression.py; python test_multi_degree_boe.py
  ```
