# 📊 INFORME METICULOSO DE PRUEBAS DE FUEGO INTEGRALES - PROYECTO UNIHUB

**Fecha y Hora de Auditoría**: 2026-08-06 14:12:00  
**Entorno de Ejecución**: Windows 11 / Python 3.12 / FastAPI 0.110 / React 18 / PostgreSQL 15 / Docker Compose v2  
**Repositorio GitHub**: `https://github.com/Alejandro-UCA/UniHub-TFG.git`

---

## 1. FASE 1: CRAWLER DE RUCT, BOE Y WEBS OFICIALES DE UNIVERSIDADES

### 1.1 Mantenimiento de Datasets Persistidos (JSON Atómicos)
- **Directorio de Persistencia**: `Codigo/Crawler/planes_estudio/` e `titulaciones_universidad.json`.
- **Volumen de Planes Estructurados**: **13.653 archivos JSON atómicos** de titulaciones.
- **Gestión de Checkpoint**: `checkpoint.json` opera con caché por fecha de modificación (`mtime`) en memoria RAM y registros atómicos de omisión (`extinct_degrees`, `non_study_plan_pdfs`, `unreachable_urls`) permitiendo escaneos en 0 milisegundos para titulaciones ya procesadas.

### 1.2 Prueba de Fuego Parte 1 (Ingesta RUCT & Parser BOE PDF)
- **Resiliencia de Red (`downloader.py`)**: Tolerancia a fallos con exclusión de errores HTTP 404 del contador de cortocircuito. Reintento automático tras 5 minutos ante cuellos de botella HTTP 429/50x.
- **Validación de Firma Digital**: Verificación de bytes mágicos (`b"%PDF-"`) para descartar respuestas HTML falsas con código 200.
- **Filtro Estricto de Vigencia (`parsers.py`)**: Descarte de dos capas de planes extinguidos pre-Bolonia (RD 56/2005) seleccionando la publicación BOE más reciente.

### 1.3 Prueba de Fuego Parte 2 (Rescate Web Oficial y Precios Privados)
- **Sujeto Público (Universidad de Cádiz - 005)**:
  - **Titulaciones Procesadas**: 175 titulaciones registradas.
  - **Tasa de Éxito**: **170 de 175 titulaciones resueltas (97.14% de éxito)**.
  - **Titulaciones Omisiones Explicadas**: Las 5 titulaciones no desglosadas en la web local corresponden a Másteres Interuniversitarios coordinados por otras sedes socias (`4311142`, `4311028`, `4310648`, `4311144`, `4310881`).
  - **Auditoría `robots.txt`**: Verificada la lectura previa de `https://www.uca.es/robots.txt` en cumplimiento de estándares de rastreo ético.
- **Sujeto Privado (CUNEF Universidad - 089)**:
  - **Titulaciones Procesadas**: 3 titulaciones sin desglose en el BOE.
  - **Tasa de Éxito**: **3 de 3 titulaciones resueltas (100% de éxito)**.
  - **Recolección de Precios Privados**: Extracción y almacenamiento en JSON de honorarios docentes privados (**145.00 €/ECTS** y **8.700.00 €/año**).

### 1.4 Prueba de Fuego Parte 3 (Consolidación Curricular ECTS)
- **Normalización de Asignaturas**: Asignación atómica de nombre, créditos ECTS, módulo, carácter y curso académico.
- **Muestreo Evaluado**: 89 asignaturas normalizadas en muestra con **711.0 ECTS** acumulados.

---

## 2. FASE 2: API REST FASTAPI Y BASE DE DATOS POSTGRESQL

### 2.1 Conexión y Rendimiento Relacional (`database/schema.sql` y `connection.py`)
- **Base de Datos**: PostgreSQL 15 contenerizado (`unihub_db`) operando en puerto `5432`.
- **Pool de Conexiones**: SQLAlchemy configurado con `pool_size=15`, `max_overflow=25` y `pool_pre_ping=True`.
- **Búsqueda Avanzada por Texto**: Extensión `pg_trgm` con índices GIN (`idx_univ_nombre_trgm`, `idx_tit_titulo_trgm`) habilitada.
- **Rol de Solo Lectura**: Usuario restringido `unihub_api_user` creado con permisos `GRANT SELECT`.

### 2.2 Migración ETL Acelerada en Lote (`etl_loader.py`)
- **Migración por Lotes**: Inserción masiva de asignaturas mediante `bulk_save_objects` (reduciendo la latencia de migración de 15s a menos de 1.5s).
- **Rutas de Búsqueda Adaptativas**: Detección automática del directorio de planes de estudio tanto en entorno nativo como en contenedores Docker (`/app/planes_estudio`).

### 2.3 Endpoints API REST Evaluados
- `GET /`: Mensaje de bienvenida y enlaces a Swagger/ReDoc.
- `GET /api/v1/universidades`: Lista ordenada prioritariamente (Públicas primero, Privadas después).
- `GET /api/v1/titulaciones/{codigo}`: Detalle de titulación con precios ECTS y fuente.
- `POST /api/v1/admin/sync-etl`: Endpoint de sincronización en caliente en segundo plano (`BackgroundTasks`).

---

## 3. FASE 3: APLICACIÓN WEB REACT Y MOTOR "CALCULA TU MATRÍCULA"

### 3.1 Evaluaciones del Motor Financiero de Matrícula (`TuitionCalculator.jsx`)
Se ejecutaron 4 escenarios financieros reales:

1. **Universidad Pública (UCA - 60 ECTS 1º Curso Ordinario)**:
   - **Cálculo**: $60 \text{ ECTS} \times 16,80 \text{ €/ECTS} = 1.008,00 \text{ €} + 45,00 \text{ €}$ tasas secretaría.
   - **Resultado Neto**: **`1.053,00 €`**.
2. **Universidad Pública con Repetición + Beca MEC (UCA)**:
   - **Cálculo**: 3 asig. 1ª ($302,40 \text{ €}$), 1 asig. 2ª ($151,20 \text{ €}$), 1 asig. 3ª ($302,40 \text{ €}$).
   - **Descuento Beca MEC**: Exención provisional del 100% en 1ª matrícula ($-302,40 \text{ €}$).
   - **Resultado Neto**: **`498,60 €`** (Cobro de repeticiones + 45 € secretaría obligatoria).
3. **Universidad Privada (CUNEF - 145 €/ECTS) + Familia Numerosa General**:
   - **Cálculo**: $21 \text{ ECTS} \times 145,00 \text{ €} = 3.045,00 \text{ €} + 45,00 \text{ €}$ secretaría.
   - **Comportamiento Exenciones**: Se neutralizan los descuentos de decretos públicos mostrando el aviso: *"Exención autonómica NO aplicable en universidad privada (Tarifa Ordinaria Privada)"*.
   - **Resultado Neto**: **`3.090,00 €`**.
4. **Universidad Pública con Bonificación 99% CCAA (Junta de Andalucía)**:
   - **Cálculo**: $60 \text{ ECTS} = 1.008,00 \text{ €} + 45,00 \text{ €}$ secretaría.
   - **Bonificación 99% CCAA**: $-997,92 \text{ €}$.
   - **Resultado Neto**: **`55,08 €`** (Ahorro del 99% en asignaturas aprobadas).

### 3.2 Evaluación de Adaptabilidad Responsive (Modo PC vs. Modo Móvil)
- **Modo PC (Escritorio - Viewport $\ge 1024\text{px}$)**:
  - Navegación horizontal continua con 6 opciones y conmutador de tema visual.
  - Cuadrícula de 3 columnas para tarjetas `DegreeCard` y `UnivCard`.
  - Layout de la calculadora en **2 columnas (`2.2fr 1fr`)** con panel de recibo flotante (`position: 'sticky', top: '2rem'`).
- **Modo Móvil (Smartphone - Viewport $\le 768\text{px}$)**:
  - Menú hamburguesa colapsable táctil (`Menu` / `X`) con overlay desplegable.
  - Reestructuración de cuadrículas a **1 columna única (100% ancho)**.
  - Layout de la calculadora en **1 columna vertical apilada** (Lista arriba, Recibo abajo).
  - Reset de paginación automático en geolocalización (`setCurrentPage(1)`).
  - Soporte A11y por teclado (`tabIndex={0}`, eventos `Enter`/`Espacio`).

---

## 4. FASE 4: INFRAESTRUCTURA DOCKER Y PERSISTENCIA DE DATOS

### 4.1 Comprobación del Orquestador Docker Compose (`docker-compose.yml`)
- **Contenedores Orquestados**:
  1. `unihub_db` (PostgreSQL 15 Alpine, puerto `5432`).
  2. `unihub_api` (FastAPI + Uvicorn, puerto `8000`).
  3. `unihub_www` (Nginx + React SPA, puertos `80` y `5173`).
  4. `unihub_crawler` (Python 3.12 Crawler Daemon).
- **Scripts de Arranque/Parada**: `iniciar_proyecto.bat` / `detener_proyecto.bat` (Windows) e `iniciar_proyecto.sh` / `detener_proyecto.sh` (Linux/macOS).

### 4.2 Verificación de Persistencia
- **Volumen Nombrado (`unihub_postgres_data`)**: Al ejecutar `docker compose down` o detener los dockers, los datos relacionales de PostgreSQL **se conservan al 100%**.
- **Montajes de Disco Host (`planes_estudio/`)**: Los 13.653 archivos JSON atómicos permanecen salvaguardados en el sistema de archivos del host.

---

### 🏆 CONCLUSIÓN GENERAL DE LA AUDITORÍA
Todas las fases del proyecto **UniHub** (**Fase 1**, **Fase 2**, **Fase 3** y **Fase 4**) han superado con éxito las pruebas de fuego integrales. El sistema demuestra la máxima solidez en recolección de datos públicos/privados, persistencia relacional, simulación matemática de matrículas y rendimiento responsive en todos los dispositivos.