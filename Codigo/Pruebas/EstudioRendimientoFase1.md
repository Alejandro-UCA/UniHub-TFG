# Estudio de Rendimiento (Tiempo y Espacio) y Propuesta de Optimizaciones — Fase 1 (UniHub)

**Fecha**: `2026-08-09`  
**Módulo Evaluado**: Fase 1 — Crawler de Scraping (RUCT, BOE PDF, Web Scraper, Playwright SPA, Precios ECTS)

---

## 📌 1. Resumen Ejecutivo de la Arquitectura de Rendimiento

La Fase 1 de UniHub procesa el catálogo nacional de educación superior en España: **90+ Universidades** y **~13.600 Titulaciones oficiales**.

La arquitectura está diseñada como un **pipeline de alto rendimiento en 3 partes**:
1. **Parte 1 (RUCT + BOE PDF)**: Modelo **Productor-Consumidor desacoplado con `multiprocessing`**:
   - **Proceso Productor (Red/I-O Bound)**: Scraping de metadatos RUCT y descarga de PDFs de BOE.
   - **Proceso Consumidor (CPU Bound)**: Parsing curricular profundo de PDFs con `pypdf`, `pdfplumber` y `ocr_parser`.
2. **Parte 2 (Web Crawler Oficiales + Playwright SPA)**: Modelo de **concurrencia por hilos (`ThreadPoolExecutor`) con resiliencia en cascada**:
   - Descarga de HTML estático + Fallback a navegador Headless (Playwright Chromium) para portales dinámicos en JS/React/Vue.
   - Sistema de caché en memoria a nivel de universidad (`lazy_scanned_pages_cache`).
3. **Parte 3 (Cálculo de Precios ECTS SIIU/CCAA)**: **Enriquecimiento algorítmico en memoria**:
   - Búsqueda $O(1)$ en tablas hash de precios autonómicos por grado de experimentalidad y tipo de matrícula.

---

## ⏱️ 2. Análisis de Complejidad Temporal ($O$ - Time Complexity)

| Proceso / Componente | Complejidad Temporal ($O$) | Tiempo Típico por Unidad | Tiempo Estimado Total (Nacional) | Factor Limitante (Bottleneck) |
|:---|:---:|:---:|:---:|:---|
| **Paso 1: Listado de Universidades (RUCT)** | $O(1)$ | $\sim 1.2$ segundos | $\sim 1.2$ segundos | Red (I/O) |
| **Paso 2: Titulaciones por Universidad (RUCT)** | $O(U)$ | $\sim 0.5s$ por universidad | $\sim 45$ segundos | Red (I/O) |
| **Paso 3: Ficha Detalle Titulación (RUCT)** | $O(D)$ | $\sim 0.5s$ por titulación | $\sim 6.800s$ ($\approx 1.8$h) | Red (I/O Síncrono) |
| **Parsing PDF Vectorial (BOE)** | $O(P \cdot N)$ | $\sim 0.1s - 0.5s$ por PDF | Paralelizado en Consumidor | CPU / Regex |
| **Parsing PDF Escaneado (OCR Tesseract)** | $O(P \cdot W \cdot H)$ | $\sim 1.5s - 3.5s$ por PDF | Activo solo en $< 5\%$ PDFs | CPU / Tesseract Engine |
| **Escaneo Web Oficial (Parte 2)** | $O(U \cdot K / W)$ | $\sim 2s - 8s$ por univ ($W=4$) | $\sim 4 - 8$ minutos | Red / Playwright Browser |
| **Cálculo Precios ECTS (Parte 3)** | $O(D)$ | $\sim 0.0001s$ por título | $\sim 2.5$ segundos | CPU / Acceso a Memoria |

*Donde $U \approx 90$ universidades, $D \approx 13.600$ titulaciones, $P$ páginas por PDF, $W \times H$ resolución de imagen OCR, $K \le 8$ páginas de índice por univ, $W=4$ hilos.*

---

## 💾 3. Análisis de Complejidad Espacial ($O$ - Memory & Storage Footprint)

### A) Memoria RAM (En Ejecución)
- **Estructuras en Memoria Principal**:
  - Catálogo de titulaciones e índice de universidades en memoria: $O(D)$ dicts JSON $\approx \mathbf{15 - 25\text{ MB}}$.
  - Cola Productor-Consumidor (`mp.Queue(maxsize=100)`): Delimitada a 100 elementos $\approx \mathbf{< 5\text{ MB}}$.
- **Consumo por Subprocesos / Librerías**:
  - Parsing de PDF (`pdfplumber` / `pypdf`): $\approx \mathbf{20 - 5 0\text{ MB}}$ por proceso.
  - Navegador Headless Playwright (Chromium Instance): $\approx \mathbf{150 - 300\text{ MB}}$ mientras permanece abierto en la Parte 2.
  - Motor Tesseract OCR (`pdf2image` a 300 DPI): $\approx \mathbf{80 - 150\text{ MB}}$ por página procesada.
  - Caché de páginas índice (`lazy_scanned_pages_cache`): $\approx \mathbf{10 - 20\text{ MB}}$ por universidad activa (se resetea al cambiar de universidad).
- **Huella de RAM Total en Pico Máximo**: **~200 MB – 450 MB** *(Excelente para contenedores Docker con límites estándar de 1 GB)*.

### B) Almacenamiento en Disco (HDD/SSD)
- **Archivos Base de Datos JSON**:
  - `universidades_list.json` + `titulaciones_universidad.json`: $\approx \mathbf{8\text{ MB}}$.
  - `planes_estudio/*.json` (~13.600 ficheros): $\approx \mathbf{150 - 250\text{ MB}}$ en total.
- **Archivos Temporales (`TEMP_PDF_DIR`)**:
  - Los PDFs del BOE descargados se borran inmediatamente tras el parseo mediante bloques `finally: os.remove(pdf_path)`.
  - El espacio ocupado en disco por temporales nunca supera los **~10 - 30 MB**.

---

## 🚀 4. Propuesta de Optimizaciones Futuras Identificadas

Se han identificado **4 optimizaciones concretas** para acelerar la ejecución del crawler y reducir el consumo de recursos:

### ⚡ [OPT-01] Peticiones Asíncronas en Paso 3 de Parte 1 (`asyncio` / `aiohttp` o ThreadPool)
- **Diagnóstico**: La inspección de URLs de detalle en el RUCT (`URL_DETALLE_ESTUDIO_TEMPLATE`) se realiza de forma síncrona en un bucle simple. Esto genera un cuello de botella de I/O de red de $\sim 1.8$ horas.
- **Propuesta**: Implementar descargas concurrentes en lotes (*batch downloading*) con un `ThreadPoolExecutor(max_workers=10)` o `aiohttp` con limitador de frecuencia (*rate limiter* de 10 req/s).
- **Impacto Estimado**: **Reducción del tiempo de la Parte 1 en un 60% – 75%** (de 1.8 horas a ~25-30 minutos).

### 🧠 [OPT-02] Instancia Singleton y Cierre Diferido de Playwright (`SPALayoutCrawler`)
- **Diagnóstico**: En la Parte 2, cada subpágina que requiere renderizado SPA vuelve a instanciar la clase `SPALayoutCrawler()`, iniciando el proceso de Playwright Chromium.
- **Propuesta**: Convertir `SPALayoutCrawler` en un objeto Singleton persistente a nivel de ejecutor de universidad, cerrando el navegador solo cuando se completa la universidad entera.
- **Impacto Estimado**: **Ahorro de ~1.5s - 2.5s por titulación SPA**.

### 💾 [OPT-03] Escritura en Disco por Lotes (*Buffered Batch Serialization*)
- **Diagnóstico**: En `main.py` (línea 348), se ejecuta `atomic_json_dump(titulaciones_por_universidad, TITULACIONES_JSON)` en cada iteración de universidad. Reescribir un archivo JSON de varios MB 90 veces genera I/O innecesario en SSD/HDD.
- **Propuesta**: Guardar `TITULACIONES_JSON` cada N universidades (ej. cada 10 universidades) o al finalizar el bucle principal.
- **Impacto Estimado**: Reducción del 90% en operaciones de IOPS de disco.

### 🧹 [OPT-04] Caché Negativa Persistente para Recursos Inexistentes (HTTP 404)
- **Diagnóstico**: Las URLs de sitemap o enlaces rotos que devuelven `404 Not Found` en universidades se capturan en ejecución pero podrían ser reevaluadas si no se persisten en `checkpoint.json`.
- **Propuesta**: Garantizar que todas las URLs `404` confirmadas se registren en la lista `unreachable_urls` del checkpoint de forma permanente.
- **Impacto Estimado**: Omitir descargas fallidas conocidas en 0ms durante ejecuciones incrementales futuras.
