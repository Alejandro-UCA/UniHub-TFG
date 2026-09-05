# UniHub: Sistema de Recolección y Consulta de Grados y Másteres Universitarios

> **Trabajo Fin de Grado (TFG) — Grado en Ingeniería Informática**  
> **Escuela Superior de Ingeniería (ESI) — Universidad de Cádiz (UCA)**  
> **Autor:** Alejandro Ramos Rodríguez  
> **Director/Tutor:** Ignacio Díaz Cano  
> **Año Académico:** 2025/2026  

---

## 📌 Descripción del Proyecto

**UniHub** es una plataforma informática integral y distribuida diseñada para la centralización, extracción automatizada, almacenamiento estructurado, auditoría de calidad y consulta interactiva de la oferta oficial de educación superior en España. 

El sistema resuelve la dispersión de datos universitarios integrando de manera sinérgica el catálogo oficial del **RUCT (Ministerio de Ciencia, Innovación y Universidades)**, las resoluciones oficiales de planes de estudio publicadas en el **Boletín Oficial del Estado (BOE)**, los portales web oficiales de las **universidades públicas y privadas**, y las normativas de **precios públicos del SIIU/CCAA**.

---

## 🏗️ Arquitectura del Sistema (4 Fases de Desarrollo)

El proyecto se estructura en cuatro subsistemas de ingeniería altamente desacoplados y conectados mediante contratos formales:

`	ext
                                  ┌───────────────────────────────┐
                                  │   Fuentes Oficiales Externas  │
                                  │   (RUCT, BOE, Webs, Precios)  │
                                  └───────────────┬───────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FASE 1: RASTREADOR / CRAWLER MODULAR (Python 3.12)                                              │
│ ├─ core/        : Checkpoint atómico, Ledger SQLite WAL, Downloader HTTP/2, Resiliencia       │
│ ├─ pipelines/   : Orquestación (Parte 1: RUCT/BOE, Parte 2: Webs, Parte 3: Precios, Parte 4)    │
│ ├─ parsers/     : Extracción geométrica de PDFs del BOE, Tablas HTML rowspan, SPAs dinámicas    │
│ ├─ extractors/  : Descubrimiento BOE/Web, temarios EEES, doctorados RD 99/2011, consorcios      │
│ ├─ quality/     : Validador curricular RD 822/2021 (ECTS 240/60/180), auditoría de calidad      │
│ └─ utils/       : Sanitización lingüística multilingüe, persistencia atómica y recuperación     │
└───────────────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                │ (planes_estudio/*.json + Semillas Maestras)
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FASE 2: BASE DE DATOS Y API REST (PostgreSQL 16 + FastAPI)                                      │
│ ├─ PostgreSQL   : Esquema relacional optimizado, JSONB curricular, RBAC (unihub_api_user)       │
│ ├─ Sync ETL     : Ingesta masiva transaccional atómica e idempotente desde JSON                 │
│ └─ FastAPI REST : Endpoints OpenAPI 3.1, paginación, filtros vocacionales y telemetría cgroup   │
└───────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                        │ (HTTP / JSON RESTful)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FASE 3: PORTAL WEB FRONTEND SPA (React 19 + Vite 8 + Tailwind/CSS)                              │
│ ├─ Identidad Institucional UCA (Azul marino / Amarillo / Tipografías corporativas)             │
│ ├─ Geolocalización del usuario por fórmula de Haversine con distancias en tiempo real          │
│ ├─ Paginación configurable (5, 10, 20, 50, 100) y ocultación de identificadores internos       │
│ ├─ Calculadora de matrículas por CCAA, coeficiente experimental y beca general MEC             │
│ └─ Panel de Administración y control del crawler accesible de forma aislada en /admin          │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FASE 4: ORQUESTACIÓN Y CONTENERIZACIÓN (Docker Compose v2 + Nginx)                              │
│ ├─ unihub_db      : PostgreSQL 15/16 Alpine con volumen persistente unihub_postgres_data         │
│ ├─ unihub_api     : Servicio Python/FastAPI con usuario no privilegiado                         │
│ ├─ unihub_www     : Nginx Alpine como servidor estático y proxy inverso en puerto 80            │
│ └─ unihub_crawler : Contenedor Chromium/Tesseract con planificación programada Cron             │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
`

---

## 🚀 Despliegue Rápido en un Solo Clic

### Requisitos Previos
* **Docker Desktop** (con soporte WSL2 en Windows o Docker Engine en Linux/macOS) en ejecución.
* Conexión a Internet para la descarga inicial de imágenes base oficiales.

### 1. Iniciar el Proyecto
En Windows, simplemente haz doble clic en:
`cmd
iniciar_proyecto.bat
`
O de forma manual por terminal:
`ash
docker compose -f Codigo/Docker/docker-compose.yml up --build -d
`
El orquestador construirá las imágenes, iniciará los contenedores y esperará a que todos los healthchecks pasen a estado saludable (healthy).

### 2. Acceso a los Servicios
* 🌐 **Portal Web Frontend (Fase 3):** [http://localhost](http://localhost) (puerto 80)
* 📑 **Documentación Interactiva Swagger (API):** [http://localhost/docs](http://localhost/docs)
* 📖 **Documentación ReDoc:** [http://localhost/redoc](http://localhost/redoc)
* ⚙️ **Panel de Administración:** [http://localhost/admin](http://localhost/admin) *(Ruta protegida)*
* 🩺 **Healthcheck de API y DB:** [http://localhost:8000/api/v1/salud](http://localhost:8000/api/v1/salud)

### 3. Detener o Limpiar el Proyecto
* **Detener los contenedores:** Doble clic en detener_proyecto.bat (o docker compose down).
* **Limpiar datos y cachés volátiles:** Doble clic en limpiar_datos.bat (garantiza la preservación inmutable de las 3 semillas maestras oficiales).

---

## 🧪 Batería de Pruebas y Validación

El sistema incluye **38 suites completas de pruebas automatizadas** que abarcan validación unitaria, de integración, de resiliencia ante cortes y análisis empírico con el BOE:

`powershell
# Ejecución de la batería de pruebas en el entorno local
.venv\Scripts\python.exe Codigo/Pruebas/run_codigo_unit_tests.py
`
> **Resultado:** 38/38 passed, 0 failed (100% de éxito).

---

## 📂 Estructura del Repositorio

`	ext
├── Codigo/
│   ├── API/                  # Backend FastAPI, esquemas Pydantic v2, endpoints y seguridad
│   ├── Crawler/              # Rastreador Fase 1 con arquitectura 100% modular
│   │   ├── core/             # Downloader, Checkpoint, Ledger SQLite WAL, Configuración
│   │   ├── pipelines/        # Orquestador y las 4 Partes secuenciales del crawler
│   │   ├── parsers/          # Parsers BOE PDF, Tablas HTML, RUCT, Widgets, SPA
│   │   ├── extractors/       # Búsqueda web/BOE, Guías docentes, Doctorados RD 99/2011
│   │   ├── quality/          # Validadores curriculares RD 822/2021 y control de calidad
│   │   ├── utils/            # Saneamiento de textos, persistencia y limpieza de datos
│   │   └── Datos/            # Almacén persistente (semillas maestras y planes extraídos)
│   ├── Docker/               # Dockerfiles, nginx.conf y docker-compose.yml
│   ├── Pruebas/              # 38 suites de pruebas unitarias, benchmarks y auditorías
│   └── WWW/                  # Frontend SPA en React 19, Vite 8 y Tailwind/CSS
├── Documentacion/            # Memoria oficial del TFG en LaTeX (110 páginas compiladas)
│   ├── main.pdf              # Documento PDF oficial compilado listo para entrega
│   ├── main.tex              # Archivo maestro LaTeX con plantilla oficial ESI-UCA
│   └── sections/             # Capítulos de Análisis, Requisitos, Diseño, Implementación, etc.
├── iniciar_proyecto.bat      # Script de arranque en un solo clic para Windows
├── detener_proyecto.bat      # Script de apagado ordenado de contenedores
└── limpiar_datos.bat         # Script de purga segura de cachés respetando semillas
`

---

## 📄 Memoria del Proyecto y Compilación

La memoria académica del TFG se encuentra maquetada con la plantilla oficial de la Escuela Superior de Ingeniería de la UCA y consta de **110 páginas** estructuradas en Prolegómeno, Desarrollo, Epílogo y Anexos:

Para compilar la memoria:
`ash
cd Documentacion
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
`
El archivo resultante es Documentacion/main.pdf.

---

## ⚖️ Licencia y Reconocimientos

Este proyecto ha sido desarrollado como Trabajo Fin de Grado en la **Universidad de Cádiz (UCA)** bajo licencia de código abierto académica.

* **Autor:** Alejandro Ramos Rodríguez
* **Director:** Ignacio Díaz Cano
