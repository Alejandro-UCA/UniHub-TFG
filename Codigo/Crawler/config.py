import os

# ==============================================================================
# 1. DIRECTORIOS Y RUTAS BASE DE SISTEMA
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "Datos")
PLANES_DIR = os.path.join(DATA_DIR, "planes_estudio")
TEMP_PDF_DIR = os.path.join(BASE_DIR, "temp_pdfs")

# Asegurar la existencia de los directorios de trabajo
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PLANES_DIR, exist_ok=True)
os.makedirs(TEMP_PDF_DIR, exist_ok=True)

# ==============================================================================
# 2. ARCHIVOS DE PERSISTENCIA Y CACHÉ DUAL (JSON & SQLITE WAL)
# ==============================================================================
UNIVERSIDADES_JSON = os.path.join(DATA_DIR, "universidades.json")
TITULACIONES_JSON = os.path.join(DATA_DIR, "titulaciones_universidad.json")
ERRORES_JSON = os.path.join(DATA_DIR, "errores_crawler.json")
CHECKPOINT_JSON = os.path.join(DATA_DIR, "checkpoint.json")
ESTADISTICAS_JSON = os.path.join(DATA_DIR, "estadisticas_rendimiento.json")
PRECIOS_CCAA_JSON = os.path.join(DATA_DIR, "precios_ccaa.json")
CACHE_DB_PATH = os.path.join(DATA_DIR, "unihub_cache.sqlite3")

# ==============================================================================
# 3. ENDPOINTS Y PLANTILLAS OFICIALES DEL RUCT (MINISTERIO DE EDUCACIÓN)
# ==============================================================================
URL_UNIVERSIDADES_LIST = (
    "https://www.educacion.gob.es/ruct/listauniversidades"
    "?actual=universidades&cccaa=&tipo_univ=&d-8320336-e=2&6578706f7274=1&codigoUniversidad=&consulta=1"
)

URL_ESTUDIOS_UNIV_TEMPLATE = (
    "https://www.educacion.gob.es/ruct/listaestudiosuniversidad"
    "?actual=universidades&d-1335801-e=2&6578706f7274=1&codigoUniversidad={codigo_universidad}"
)

URL_DETALLE_ESTUDIO_TEMPLATE = (
    "https://www.educacion.gob.es/ruct/estudiouniversidad.action"
    "?codigoCiclo=SC&codigoEstudio={codigo_estudio}&actual=universidad"
)

URL_VERIFICACION_ESTADO_TEMPLATE = (
    "https://www.educacion.gob.es/ruct/listaestudios"
    "?actual=estudios&codigoEstudio={codigo_estudio}"
)

# ==============================================================================
# 4. CONFIGURACIÓN DE RED, CLIENTE HTTP Y BUENAS PRÁCTICAS DE CRAWLING
# ==============================================================================
REQUEST_DELAY = float(os.getenv("CRAWLER_REQUEST_DELAY", 0.35))  # Retardo cortés entre peticiones (0.35s)
MAX_RETRIES = int(os.getenv("CRAWLER_MAX_RETRIES", 3))           # Intentos máximos por reconexión
HTTP_TIMEOUT = int(os.getenv("CRAWLER_HTTP_TIMEOUT", 30))         # Timeout de conexión HTTP en segundos
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "UniHubCrawler/1.0 (+https://github.com/Alejandro-UCA/UniHub-TFG; contacto@unihub)"
)

# Mapeo de dominios autonómicos obsoletos a dominios oficiales activos
DOMAIN_MAPPINGS = {
    "portaldogc.gencat.cat": "dogc.gencat.cat",
    "www.boa.aragon.es": "boa.aragon.es",
    "bocm.es": "bocm.madrid.org",
    "www.bocm.es": "bocm.madrid.org",
    "wwww.bocm.es": "bocm.madrid.org",
    "bocyl.jcyl.es": "bocyl.jcyl.es",
    "www.bocyl.jcyl.es": "bocyl.jcyl.es",
    "www.dogv.gva.es": "dogv.gva.es",
    "doe.gobex.es": "doe.juntaex.es",
    "boe.es": "www.boe.es",
    "ww.boe.es": "www.boe.es",
    "www.boe.es": "www.boe.es",
    "wwww.boe.es": "www.boe.es",
    "wwwww.boe.es": "www.boe.es",
    "vwww.boe.es": "www.boe.es",
    "pww.boe.es": "www.boe.es",
    "'www.boe.es": "www.boe.es"
}

# ==============================================================================
# 5. PATRÓN CIRCUIT BREAKER (RESILIENCIA ANTE CAÍDAS DE RED/SERVIDOR)
# ==============================================================================
CIRCUIT_BREAKER_FAILURES_THRESHOLD = 10  # Fallos seguidos para activar pausa
CIRCUIT_BREAKER_PAUSE_SECONDS = 300      # Duración de la pausa (5 minutos)
CIRCUIT_BREAKER_MAX_PAUSES = 3           # Pausas máximas acumuladas antes de omitir universidad (15 min)

# ==============================================================================
# 6. PARALELISMO Y MULTIPROCESAMIENTO (OPT-01 & OPT-03)
# ==============================================================================
CPU_WORKERS_COUNT = int(os.getenv("CRAWLER_CPU_WORKERS", max(1, min(4, os.cpu_count() or 4))))  # Pool multiprocesador PDF/OCR
ASYNC_PREFETCH_WORKERS = 4                                                                       # Hilos de precarga de titulaciones RUCT
WEB_CRAWLER_WORKERS = 4                                                                         # Hilos de escaneo web oficial

# ==============================================================================
# 7. PARÁMETROS DEL RASTREADOR WEB OFICIAL Y SITEMAPS (FASE 1 PARTE 2)
# ==============================================================================
WEB_ROBOTS_FALLBACK_DELAY = 0.5   # Retardo por defecto si robots.txt no especifica Crawl-delay
SITEMAP_FETCH_TIMEOUT = 4         # Timeout por candidato de Sitemap XML en segundos
WEB_SEARCH_SUBPAGES_LIMIT = 8     # Límite de subpáginas a inspeccionar por portal
WEB_SEARCH_SUBPAGES_DEPTH = 5     # Coincidencias máximas examinadas del Sitemap

PRIVATE_ECTS_MIN = 15.0           # Umbral mínimo razonable para precio ECTS en privada (€)
PRIVATE_ECTS_MAX = 500.0          # Umbral máximo razonable para precio ECTS en privada (€)
PRIVATE_ANNUAL_MIN = 1000.0       # Umbral mínimo razonable para matrícula anual en privada (€)
PRIVATE_ANNUAL_MAX = 45000.0      # Umbral máximo razonable para matrícula anual en privada (€)

# ==============================================================================
# 8. CÁLCULO DE TARIFAS PÚBLICAS SIIU (FASE 1 PARTE 3)
# ==============================================================================
DEFAULT_PUBLIC_ECTS_PRICE = 15.00  # Precio ECTS público por defecto (€)
DEFAULT_ADMIN_FEES = 45.00         # Tasas secretariales/administrativas estándar (€)
DOCTORATE_TUTELA_CREDITS = 10     # Créditos equivalentes de tutela académica anual en Doctorado
STANDARD_YEAR_ECTS_CREDITS = 60    # Créditos ECTS de un curso universitario estándar

# ==============================================================================
# 9. PARÁMETROS ADICIONALES DE RED, JITTER Y REINTENTOS HTTP 429
# ==============================================================================
JITTER_MIN_SECONDS = float(os.getenv("CRAWLER_JITTER_MIN", 0.10))          # Jitter aleatorio mínimo por petición (0.10s)
JITTER_MAX_SECONDS = float(os.getenv("CRAWLER_JITTER_MAX", 0.35))          # Jitter aleatorio máximo por petición (0.35s)
HTTP_429_DEFAULT_RETRY_AFTER = int(os.getenv("CRAWLER_429_RETRY_AFTER", 30))  # Retardo fallback para HTTP 429 si Retry-After no existe (30s)
DOWNLOAD_CHUNK_SIZE = int(os.getenv("CRAWLER_CHUNK_SIZE", 8192))           # Tamaño del bloque para descargas directas en streaming (8192 bytes)

# ==============================================================================
# 10. PARÁMETROS ADICIONALES DE CACHÉ, QUEUES Y SERVICIOS EXTERNOS
# ==============================================================================
ROBOTS_CACHE_TTL_SECONDS = int(os.getenv("CRAWLER_ROBOTS_CACHE_TTL", 86400))       # TTL de caché de robots.txt (24h según RFC 9309)
LAZY_SCANNED_PAGES_CACHE_LIMIT = int(os.getenv("CRAWLER_LAZY_LIMIT", 20))           # Límite de páginas escaneadas en caché RAM por titulación
ROBOTS_CHECK_TIMEOUT = int(os.getenv("CRAWLER_ROBOTS_TIMEOUT", 10))                # Timeout para comprobación de robots.txt
TASK_QUEUE_MAXSIZE = int(os.getenv("CRAWLER_TASK_QUEUE_MAXSIZE", 200))             # Tamaño máximo de la cola multiproceso
TASK_QUEUE_GET_TIMEOUT = int(os.getenv("CRAWLER_TASK_QUEUE_TIMEOUT", 5))            # Timeout de lectura en cola de tareas (5s)
DEFAULT_FALLBACK_CCAA = os.getenv("CRAWLER_DEFAULT_FALLBACK_CCAA", "Andalucía")      # CCAA por defecto para precios fallback
WIKIPEDIA_API_URL = os.getenv("CRAWLER_WIKIPEDIA_API_URL", "https://es.wikipedia.org/w/api.php")
WIKIDATA_API_URL = os.getenv("CRAWLER_WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php")
