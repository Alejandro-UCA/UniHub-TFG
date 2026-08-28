import os

def _safe_int(env_var: str, default: int) -> int:
    try:
        return int(os.getenv(env_var, str(default)))
    except (ValueError, TypeError):
        return default

def _safe_float(env_var: str, default: float) -> float:
    try:
        return float(os.getenv(env_var, str(default)))
    except (ValueError, TypeError):
        return default


# ==============================================================================
# 1. DIRECTORIOS Y RUTAS BASE DE SISTEMA
# ==============================================================================
# Carpeta raíz del módulo Crawler
BASE_DIR = os.getenv("CRAWLER_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))

# Carpeta donde se almacenan todos los datos persistidos (JSONs, SQLite, estadísticas)
DATA_DIR = os.getenv("CRAWLER_DATA_DIR", os.path.join(BASE_DIR, "Datos"))

# Directorio de logs auxiliares de la Fase 1. El registro estructurado principal
# continúa almacenándose en ERRORES_JSON, pero el orquestador necesita una ruta
# común para salidas de procesos y futuras rotaciones.
LOGS_DIR = os.getenv("CRAWLER_LOGS_DIR", os.path.join(DATA_DIR, "logs"))

# Subcarpeta donde se guardan los archivos JSON individuales de cada titulación/plan de estudio
PLANES_DIR = os.getenv("CRAWLER_PLANES_DIR", os.path.join(DATA_DIR, "planes_estudio"))

# Carpeta temporal para descarga en disco de PDFs del BOE antes de su análisis por los procesos CPU
TEMP_PDF_DIR = os.getenv("CRAWLER_TEMP_PDF_DIR", os.path.join(BASE_DIR, "temp_pdfs"))

# Asegurar la existencia automática de los directorios de trabajo en disco
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PLANES_DIR, exist_ok=True)
os.makedirs(TEMP_PDF_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

def get_plan_filepath(u_code: str, d_code: str, partitioned: bool = True, ensure_dirs: bool = True) -> str:
    """
    Retorna la ruta del archivo JSON para una titulación.
    Si partitioned=True, organiza en subcarpeta por universidad: Datos/planes_estudio/{u_code}/{d_code}.json
    Si partitioned=False, retorna la ruta plana histórica: Datos/planes_estudio/{d_code}.json
    """
    if partitioned and u_code:
        u_folder = os.path.join(PLANES_DIR, str(u_code).zfill(3))
        if ensure_dirs:
            os.makedirs(u_folder, exist_ok=True)
        return os.path.join(u_folder, f"{d_code}.json")
    return os.path.join(PLANES_DIR, f"{d_code}.json")

def find_plan_filepath(u_code: str, d_code: str) -> str:
    """
    Busca la ruta existente del plan de estudio, priorizando la ruta particionada
    y haciendo fallback automático a la ruta plana histórica.
    """
    if u_code:
        part_path = os.path.join(PLANES_DIR, str(u_code).zfill(3), f"{d_code}.json")
        if os.path.exists(part_path):
            return part_path
    flat_path = os.path.join(PLANES_DIR, f"{d_code}.json")
    if os.path.exists(flat_path):
        return flat_path
    return get_plan_filepath(u_code, d_code, partitioned=True, ensure_dirs=False)

# ==============================================================================
# 2. ARCHIVOS DE PERSISTENCIA Y CACHÉ DUAL (JSON & SQLITE WAL)
# ==============================================================================
# Archivo JSON con el catálogo de las 109 universidades de España (Públicas y Privadas)
UNIVERSIDADES_JSON = os.getenv("CRAWLER_UNIVERSIDADES_JSON", os.path.join(DATA_DIR, "universidades.json"))

# Archivo JSON con el catálogo consolidado de titulaciones vigentes por universidad
TITULACIONES_JSON = os.getenv("CRAWLER_TITULACIONES_JSON", os.path.join(DATA_DIR, "titulaciones_universidad.json"))

# Archivo JSON de registro de incidencias, errores de red y URLs no disponibles
ERRORES_JSON = os.getenv("CRAWLER_ERRORES_JSON", os.path.join(DATA_DIR, "errores_crawler.json"))

# Archivo JSON de respaldo de puntos de control (checkpoint) para reanudar el rastreo ante paradas
CHECKPOINT_JSON = os.getenv("CRAWLER_CHECKPOINT_JSON", os.path.join(DATA_DIR, "checkpoint.json"))

# Archivo JSON con métricas de Green IT, tiempos de CPU, esperas de red y consumo de RAM
ESTADISTICAS_JSON = os.getenv("CRAWLER_ESTADISTICAS_JSON", os.path.join(DATA_DIR, "estadisticas_rendimiento.json"))

# Estado de progreso consumido por el panel de administración.
PROGRESS_JSON = os.getenv("CRAWLER_PROGRESS_JSON", os.path.join(DATA_DIR, "progreso_en_vivo.json"))

# Archivo JSON con tarifas catalogadas por crédito ECTS; requieren verificación de vigencia.
PRECIOS_CCAA_JSON = os.getenv("CRAWLER_PRECIOS_CCAA_JSON", os.path.join(DATA_DIR, "precios_ccaa.json"))

# Base de datos transaccional SQLite WAL para indexación ultrarrápida (0ms) y firmas SHA-256 de PDFs
CACHE_DB_PATH = os.getenv("CRAWLER_CACHE_DB_PATH", os.path.join(DATA_DIR, "unihub_cache.sqlite3"))

# Caché persistente de guías docentes de la Parte 4.
SUBJECT_GUIDE_CACHE_DB = os.getenv(
    "CRAWLER_SUBJECT_GUIDE_CACHE_DB",
    os.path.join(DATA_DIR, "cache_guias_docentes.db"),
)

# Caché persistente de cuerpos HTTP para peticiones condicionales (ETag/Last-Modified).
HTTP_CACHE_DIR = os.getenv("CRAWLER_HTTP_CACHE_DIR", os.path.join(DATA_DIR, "http_cache"))
HTTP_CACHE_TTL_SECONDS = _safe_int("CRAWLER_HTTP_CACHE_TTL", str(7 * 24 * 3600))
HTTP_CACHE_MAX_BYTES = _safe_int("CRAWLER_HTTP_CACHE_MAX_BYTES", str(1024 * 1024 * 1024))
os.makedirs(HTTP_CACHE_DIR, exist_ok=True)

# Política de ejecución de la Fase 1. En una ejecución nacional normal se
# vuelven a descubrir las URLs y se revalidan todas las fuentes conocidas.
# Los límites explícitos de universidades/titulaciones siguen permitiendo
# ejecuciones parciales para diagnóstico o recuperación.
FULL_REVALIDATION = os.getenv("CRAWLER_FULL_REVALIDATION", "1").strip().lower() not in {"0", "false", "no"}
REDISCOVER_URLS_EVERY_RUN = os.getenv("CRAWLER_REDISCOVER_URLS", "1").strip().lower() not in {"0", "false", "no"}
_target_codes_raw = os.getenv("CRAWLER_UNIVERSITY_CODES", "")
TARGET_UNIVERSITY_CODES = tuple(sorted({code.strip().zfill(3) for code in _target_codes_raw.split(",") if code.strip()}))

# Integración con la Fase 2. Estas variables viven en la configuración central
# para evitar URLs y secretos repetidos en el orquestador y el emisor de progreso.
API_SYNC_URL = os.getenv("API_SYNC_URL", "http://api:8000/api/v1/admin/sync-etl")
API_PROGRESS_URL = os.getenv("API_PROGRESS_URL", "")
_admin_api_keys = [value.strip() for value in os.getenv("ADMIN_API_KEYS", "").split(",") if value.strip()]
_legacy_admin_api_key = os.getenv("ADMIN_API_KEY", "").strip()
if _legacy_admin_api_key and _legacy_admin_api_key not in _admin_api_keys:
    _admin_api_keys.insert(0, _legacy_admin_api_key)
ADMIN_API_KEYS = tuple(_admin_api_keys)
# El crawler necesita enviar una clave activa; se usa la primera para facilitar
# la rotación sin mantener secretos duplicados en su configuración.
ADMIN_API_KEY = ADMIN_API_KEYS[0] if ADMIN_API_KEYS else ""
# La ETL es transaccional y puede procesar miles de planes; este límite cubre
# una ejecución completa en vez de confundir una respuesta aún en curso con un fallo.
API_SYNC_TIMEOUT_SECONDS = _safe_float("CRAWLER_API_SYNC_TIMEOUT", "600")
PROGRESS_POST_TIMEOUT_SECONDS = _safe_float("CRAWLER_PROGRESS_POST_TIMEOUT", "0.15")

# ==============================================================================
# 3. ENDPOINTS Y PLANTILLAS OFICIALES DEL RUCT (MINISTERIO DE EDUCACIÓN)
# ==============================================================================
# URL oficial del Ministerio para exportar el listado completo de universidades españolas
URL_UNIVERSIDADES_LIST = os.getenv(
    "CRAWLER_URL_UNIV_LIST",
    "https://www.educacion.gob.es/ruct/listauniversidades"
    "?actual=universidades&cccaa=&tipo_univ=&d-8320336-e=2&6578706f7274=1&codigoUniversidad=&consulta=1"
)

# Plantilla de URL para exportar el catálogo de titulaciones de una universidad según su código
URL_ESTUDIOS_UNIV_TEMPLATE = os.getenv(
    "CRAWLER_URL_ESTUDIOS_TEMPLATE",
    "https://www.educacion.gob.es/ruct/listaestudiosuniversidad"
    "?actual=universidades&d-1335801-e=2&6578706f7274=1&codigoUniversidad={codigo_universidad}"
)

# Plantilla de URL para acceder a la ficha individual de una titulación y extraer sus enlaces al BOE
URL_DETALLE_ESTUDIO_TEMPLATE = os.getenv(
    "CRAWLER_URL_DETALLE_TEMPLATE",
    "https://www.educacion.gob.es/ruct/estudiouniversidad.action"
    "?codigoCiclo=SC&codigoEstudio={codigo_estudio}&actual=universidad"
)

# Plantilla de URL para verificar el estado de vigencia (Vigente vs Extinguida) en el buscador del RUCT
URL_VERIFICACION_ESTADO_TEMPLATE = os.getenv(
    "CRAWLER_URL_VERIFICACION_TEMPLATE",
    "https://www.educacion.gob.es/ruct/listaestudios"
    "?actual=estudios&codigoEstudio={codigo_estudio}"
)

# ==============================================================================
# 4. CONFIGURACIÓN DE RED, CLIENTE HTTP Y BUENAS PRÁCTICAS DE CRAWLING
# ==============================================================================
REQUEST_DELAY = _safe_float("CRAWLER_REQUEST_DELAY", 0.35)  # Retardo cortés entre peticiones (0.35s)
MAX_RETRIES = _safe_int("CRAWLER_MAX_RETRIES", 3)           # Intentos máximos por reconexión
HTTP_TIMEOUT = _safe_int("CRAWLER_HTTP_TIMEOUT", 30)         # Timeout de conexión HTTP en segundos
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "UniHubCrawler/1.0 (+https://github.com/Alejandro-UCA/UniHub-TFG; contacto@unihub)"
)
HTTP_POOL_CONNECTIONS = _safe_int("CRAWLER_HTTP_POOL_CONNECTIONS", 35)  # Tamaño del pool de hosts en caché Keep-Alive
HTTP_POOL_MAXSIZE = _safe_int("CRAWLER_HTTP_POOL_MAXSIZE", 25)          # Conexiones simultáneas por host
DOWNLOAD_CHUNK_SIZE = _safe_int("CRAWLER_CHUNK_SIZE", 8192)             # Bloque para descargas de PDF (bytes)
JITTER_MIN_SECONDS = _safe_float("CRAWLER_JITTER_MIN", 0.10)            # Jitter aleatorio mínimo por petición (0.10s)
JITTER_MAX_SECONDS = _safe_float("CRAWLER_JITTER_MAX", 0.35)            # Jitter aleatorio máximo por petición (0.35s)
HTTP_429_DEFAULT_RETRY_AFTER = _safe_int("CRAWLER_429_RETRY_AFTER", 30) # Retardo fallback para HTTP 429 (30s)
HTTP_429_MAX_RETRY_AFTER = _safe_int("CRAWLER_429_MAX_RETRY_AFTER", 300)
MAX_RESPONSE_SIZE_BYTES = _safe_int("CRAWLER_MAX_RESPONSE_BYTES", 50 * 1024 * 1024)
MAX_TEXT_RESPONSE_SIZE_BYTES = _safe_int("CRAWLER_MAX_TEXT_BYTES", 10 * 1024 * 1024)
RESPECT_ROBOTS = os.getenv("CRAWLER_RESPECT_ROBOTS", "1").strip().lower() not in {"0", "false", "no"}
ROBOTS_FAIL_CLOSED = os.getenv("CRAWLER_ROBOTS_FAIL_CLOSED", "1").strip().lower() not in {"0", "false", "no"}
# Orígenes cuyos responsables han confirmado expresamente que no publican
# robots.txt. Esta lista NO desactiva robots: solo permite continuar si la
# consulta de robots falla a nivel de red. Es una excepción manual que debe
# retirarse si el origen empieza a publicar reglas. Se expresa como una lista
# de hosts.
ROBOTS_CONFIRMED_NO_FILE_HOSTS = frozenset(
    host.strip().lower()
    for host in os.getenv("CRAWLER_ROBOTS_CONFIRMED_NO_FILE_HOSTS", "www.educacion.gob.es").split(",")
    if host.strip()
)
NEGATIVE_CACHE_TTL_SECONDS = _safe_int("CRAWLER_NEGATIVE_CACHE_TTL", "86400")
ADAPTIVE_BACKOFF_MULTIPLIER = _safe_float("CRAWLER_ADAPTIVE_BACKOFF_MULTIPLIER", 2.0) # Multiplicador de retardo adaptativo por dominio tras 429
ADAPTIVE_BACKOFF_MAX_DELAY = _safe_float("CRAWLER_ADAPTIVE_BACKOFF_MAX_DELAY", 5.0)   # Retardo adaptativo máximo por dominio (5.0s)


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
CIRCUIT_BREAKER_FAILURES_THRESHOLD = _safe_int("CRAWLER_CB_FAILURES_THRESHOLD", 10)  # Fallos seguidos para activar pausa
CIRCUIT_BREAKER_PAUSE_SECONDS = _safe_int("CRAWLER_CB_PAUSE_SECONDS", 300)           # Duración de la pausa (5 minutos)
CIRCUIT_BREAKER_MAX_PAUSES = _safe_int("CRAWLER_CB_MAX_PAUSES", 3)                    # Pausas máximas antes de omitir (15 min)

# ==============================================================================
# 6. PARALELISMO Y MULTIPROCESAMIENTO (OPT-01 & OPT-03)
# ==============================================================================
CPU_WORKERS_COUNT = int(os.getenv("CRAWLER_CPU_WORKERS", max(1, min(4, os.cpu_count() or 4))))  # Pool multiproceso PDF/OCR
ENABLE_RUCT_ASYNC_PREFETCH = os.getenv("CRAWLER_ENABLE_RUCT_PREFETCH", "1").strip().lower() not in {"0", "false", "no"} # Activar precarga adelantada RUCT
ASYNC_PREFETCH_WORKERS = _safe_int("CRAWLER_PREFETCH_WORKERS", 2)                           # Hilos concurrentes de precarga acotada
RUCT_PREFETCH_LOOKAHEAD = _safe_int("CRAWLER_RUCT_PREFETCH_LOOKAHEAD", 3)                   # Ventana de titulaciones adelantadas en cola
WEB_CRAWLER_WORKERS = _safe_int("CRAWLER_WEB_WORKERS", 12)                                   # Hilos escaneo web oficial
TASK_QUEUE_MAXSIZE = _safe_int("CRAWLER_TASK_QUEUE_MAXSIZE", 40)                            # Tamaño máximo acotado de cola multiproceso (seguridad RAM Docker)
TASK_QUEUE_GET_TIMEOUT = _safe_int("CRAWLER_TASK_QUEUE_TIMEOUT", 5)                          # Timeout de lectura en cola (5s)
WORKER_RESULT_QUEUE_TIMEOUT = _safe_float("CRAWLER_WORKER_RESULT_QUEUE_TIMEOUT", 3.0)
WORKER_STOP_QUEUE_TIMEOUT = _safe_float("CRAWLER_WORKER_STOP_QUEUE_TIMEOUT", 3.0)
WORKER_RESULT_COLLECTION_TIMEOUT = _safe_float("CRAWLER_WORKER_RESULT_COLLECTION_TIMEOUT", 15.0)
WORKER_JOIN_TIMEOUT = _safe_float("CRAWLER_WORKER_JOIN_TIMEOUT", 5.0)
WORKER_TERMINATE_JOIN_TIMEOUT = _safe_float("CRAWLER_WORKER_TERMINATE_JOIN_TIMEOUT", 2.0)
WORKER_TASK_PUT_TIMEOUT = _safe_float("CRAWLER_WORKER_TASK_PUT_TIMEOUT", 5.0)
MAX_IN_MEMORY_PDF_BYTES = _safe_int("CRAWLER_MAX_IN_MEMORY_PDF_BYTES", str(5 * 1024 * 1024))  # Umbral híbrido RAM vs Disco (5 MB)
ENABLE_HTTP2 = os.getenv("CRAWLER_ENABLE_HTTP2", "1").strip().lower() not in {"0", "false", "no"}  # Activar conexiones multiplexadas HTTP/2
HTTP2_MAX_CONNECTIONS = _safe_int("CRAWLER_HTTP2_MAX_CONNECTIONS", 20)                         # Máximo de conexiones en pool HTTP/2
HTTP2_MAX_KEEPALIVE_CONNECTIONS = _safe_int("CRAWLER_HTTP2_MAX_KEEPALIVE", 10)                # Conexiones Keep-Alive retenidas en pool

# ==============================================================================
# 7. PARÁMETROS DEL RASTREADOR WEB OFICIAL Y SITEMAPS (FASE 1 PARTE 2)
# ==============================================================================
WEB_ROBOTS_FALLBACK_DELAY = _safe_float("CRAWLER_ROBOTS_DELAY", 0.5)      # Retardo por defecto si no hay Crawl-delay
ROBOTS_CHECK_TIMEOUT = _safe_int("CRAWLER_ROBOTS_TIMEOUT", 10)             # Timeout para lectura de robots.txt
ROBOTS_CACHE_TTL_SECONDS = _safe_int("CRAWLER_ROBOTS_CACHE_TTL", 86400)    # TTL de caché robots.txt (24h RFC 9309)
SITEMAP_FETCH_TIMEOUT = _safe_int("CRAWLER_SITEMAP_TIMEOUT", 4)            # Timeout por candidato de Sitemap XML
WEB_CONNECTIVITY_TIMEOUT = _safe_float("CRAWLER_WEB_CONNECTIVITY_TIMEOUT", 10.0)
WEB_CONTENT_TIMEOUT = _safe_float("CRAWLER_WEB_CONTENT_TIMEOUT", 15.0)
WEB_PROBE_DELAY = _safe_float("CRAWLER_WEB_PROBE_DELAY", 0.1)
WEB_SEARCH_SUBPAGES_LIMIT = _safe_int("CRAWLER_SUBPAGES_LIMIT", 12)       # Subpáginas máximas a inspeccionar
WEB_SEARCH_SUBPAGES_DEPTH = _safe_int("CRAWLER_SUBPAGES_DEPTH", 6)        # Coincidencias máximas del Sitemap
LAZY_SCANNED_PAGES_CACHE_LIMIT = _safe_int("CRAWLER_LAZY_LIMIT", 25)      # Páginas escaneadas en caché RAM
SPA_ACCORDION_CLICK_DELAY = _safe_float("CRAWLER_SPA_CLICK_DELAY", 0.35)   # Pausa tras desplegar acordeón (s)
SPA_SUBPAGE_FETCH_TIMEOUT = _safe_int("CRAWLER_SPA_FETCH_TIMEOUT", 15)     # Timeout para descarga de subpáginas SPA (s)
WEB_SEARCH_RETRY_DELAY = _safe_float("CRAWLER_WEB_SEARCH_DELAY", 0.4)      # Pausa cortés entre búsquedas de subpáginas (s)

# Parámetros del Patrón Hub-and-Spoke Catalog Indexing (Fase 1 Parte 2)
HUB_AND_SPOKE_MAX_HUBS = _safe_int("CRAWLER_HUB_MAX_HUBS", 45)             # Catálogos maestros, facultades y calidad a pre-indexar
HUB_AND_SPOKE_MAX_DEPTH = _safe_int("CRAWLER_HUB_MAX_DEPTH", 7)            # Cota máxima de profundidad en segmentos URL
HUB_AND_SPOKE_MAX_HOPS = _safe_int("CRAWLER_HUB_MAX_HOPS", 6)              # Cota máxima de saltos BFS entre sub-hubs de catálogo

# Parámetros del Motor Autónomo de Descubrimiento de HUBs Curriculares (6 Capas)
DYNAMIC_HUB_MIN_SIBLINGS = _safe_int("CRAWLER_HUB_MIN_SIBLINGS", 6)        # Mínimo de enlaces hermanos homogéneos para clasificar como HUB
DYNAMIC_HUB_MIN_TITLE_WORDS = 2                                                  # Mínimo de palabras en ancla para titulación académica
DYNAMIC_HUB_MAX_TITLE_WORDS = 10                                                 # Máximo de palabras en ancla para titulación académica
SPIDER_TRAP_PATH_MARKERS = [
    "/agenda/", "/calendario/", "/calendar/", "/eventos/", "/events/", 
    "/noticias/", "/news/", "/actualidad/", "/tag/", "/category/", 
    "/etiqueta/", "/autor/", "/author/", "/login", "/signin", 
    "/user/login", "/search/node", "/comentarios/", "/feed", "/rss",
    "/aviso-legal", "/politica-privacidad", "/cookies", "/mapa-web"
]

HUB_ACADEMIC_KEYWORDS = [
    "grados", "graus", "graos", "graduak", "bachelor",
    "masteres", "masters", "màsters", "posgrado", "postgrado", "postgrau", "posgrao",
    "oferta-academica", "oferta_academica", "oferta-formativa", "oferta-de-grados", "oferta-de-masteres",
    "estudios", "estudis", "estudos", "estudios-ofertados", "titulaciones", "titulacions",
    "facultades", "facultats", "facultad", "facultat", "centros", "centres", "planes-de-estudio",
    "calidad", "qualitat", "kalitatea", "sgic", "verificacion", "verificacio", "memorias", "memoria-verificada"
]

# Palabras clave para la detección prioritaria de Memorias Verificadas (ANECA / AQU / ACCUA / SGIC)
MEMORIA_VERIFICADA_KEYWORDS = [
    "memoria", "verificad", "verificacio", "verificacion", "autoinforme",
    "acreditac", "acreditacio", "acreditacion", "informe-modificacion",
    "informemod", "sgic", "calidad", "qualitat", "kalitatea"
]

# Palabras clave para la detección dinámica de subpáginas docentes dentro de la ficha de titulación
ACADEMIC_SUBPAGE_KEYWORDS = [
    "plan de estudios", "plan d'estudis", "pla d'estudis", "pla de estudis", "plan", "pla",
    "seccions/pla-estudis", "seccions/plan-estudios", "seccions", "malla", "malla-curricular",
    "asignaturas", "assignatures", "subjects", "materias", "guia docente", "guía docente",
    "guias docentes", "guies docents", "itinerario", "itineraris", "itinerarios", "docencia",
    "estructura", "curriculum", "syllabus", "irakasgaiak", "ikasketa-plana", "courses", "sia", "apps"
]

# Palabras clave y subdominios institucionales de portales de gestión docente
INSTITUTIONAL_PORTAL_KEYWORDS = [
    "apps", "sia", "secretaria", "portal", "sies", "cvnet", "guias", "gestion", "ujiapps", "academico", "estudis"
]



# Metadatos de ficha administrativa a descartar para evitar confusión con asignaturas (Multilingüe: ES, CA, GL, EU)
INVALID_METADATA_LABELS = {
    # ES
    "centro de gestión", "centro de gestion", "modalidad de docencia", "ámbito de conocimiento",
    "ambito de conocimiento", "idioma de impartición", "idioma de imparticion", "idioma de docencia",
    "nota de corte", "precio orientativo por crédito", "precio orientativo", "plazas de nuevo ingreso",
    "plazas", "duración de los estudios", "duración", "duracion", "datos del grado", "datos del máster",
    "jefe de estudios", "coordinador", "coordinación", "dirección de correo", "prácticas externas", "practicas externas",
    # CA / VA
    "centre de gestió", "centre de gestio", "modalitat de docència", "modalitat de docencia",
    "àmbit de coneixement", "ambit de coneixement", "idioma de docència", "idioma de docencia",
    "nota de tall", "nota de tall / preinscripció", "preu orientatiu per crèdit", "preu orientatiu",
    "places de nou ingrés", "places", "durada", "dades del grau", "dades del màster", "dades del master",
    "cap d'estudis", "adreça electrònica", "pràctiques externes", "practiques externes",
    # GL
    "centro de xestión", "modalidade de docencia", "lingua de docencia", "nota de corte",
    "prezo por crédito", "prazas", "duración", "datos do grao", "datos do máster", "prácticas externas",
    # EU
    "kudeaketa zentroa", "irakaskuntza modalitatea", "ebaki nota", "kredituko prezioa",
    "plazak", "iraupena", "graduaren datuak", "masterraren datuak", "kanpoko praktikak"
}


# Parámetros para Descubrimiento Orgánico de Centros Adscritos y Alianzas Europeas (Patrones 1 y 3)
MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV = _safe_int("CRAWLER_MAX_ORGANIC_HUBS", 12)
ORGANIC_AFFILIATED_HUB_KEYWORDS = [
    "adscrit", "adscrito", "adscrita", "centres adscrits", "centros adscritos",
    "escuela adscrita", "instituto adscrito", "escola", "escuela", "institut", "instituto",
    "fundacio", "fundacion", "consorcio", "alianza", "sea-eu", "erasmus", "eunice", 
    "charmeu", "arqus", "civica", "civis", "eut+"
]
EUROPEAN_ALLIANCES_KEYWORDS = [
    "erasmus mundus", "joint master", "european master", "sea-eu", "eunice", 
    "charmeu", "charm-eu", "arqus", "civica", "civis", "eut+", "neurotecheu", 
    "circle u", "unite!", "enlight", "4eu+", "una europa", "eureca-pro", "ingenium"
]

PRIVATE_ECTS_MIN = _safe_float("CRAWLER_PRIVATE_ECTS_MIN", 15.0)          # Umbral mínimo precio ECTS privada (€)
PRIVATE_ECTS_MAX = _safe_float("CRAWLER_PRIVATE_ECTS_MAX", 500.0)         # Umbral máximo precio ECTS privada (€)
PRIVATE_ANNUAL_MIN = _safe_float("CRAWLER_PRIVATE_ANNUAL_MIN", 1000.0)    # Umbral mínimo matrícula anual privada (€)
PRIVATE_ANNUAL_MAX = _safe_float("CRAWLER_PRIVATE_ANNUAL_MAX", 45000.0)   # Umbral máximo matrícula anual privada (€)

# ==============================================================================
# 8. CÁLCULO DE TARIFAS PÚBLICAS SIIU Y PARÁMETROS ACADÉMICOS (FASE 1 PARTE 3)
# ==============================================================================
DOCTORATE_TUTELA_CREDITS = _safe_int("CRAWLER_DOCTORATE_TUTELA_CREDITS", 10)   # ECTS tutela anual en Doctorado
STANDARD_YEAR_ECTS_CREDITS = _safe_int("CRAWLER_STANDARD_YEAR_ECTS", 60)       # ECTS de curso universitario estándar
DEFAULT_SUBJECT_ECTS = _safe_float("CRAWLER_DEFAULT_SUBJECT_ECTS", 6.0)        # Créditos ECTS estándar por asignatura
GRADO_STANDARD_ECTS = _safe_int("CRAWLER_GRADO_STANDARD_ECTS", 240)             # ECTS oficiales de un Grado estándar (4 años)
MASTER_MIN_ECTS = _safe_int("CRAWLER_MASTER_MIN_ECTS", 60)                      # ECTS mínimos oficiales de un Máster
MEDICINA_ECTS = _safe_int("CRAWLER_MEDICINA_ECTS", 360)                         # ECTS oficiales de Grado en Medicina (6 años)
ESPECIALES_GRADO_ECTS = _safe_int("CRAWLER_ESPECIALES_GRADO_ECTS", 300)         # ECTS de Grados de 5 años (Farmacia, Odontología, Veterinaria, Arquitectura)
MAX_BOE_CANDIDATES_PER_DEGREE = _safe_int("CRAWLER_MAX_BOE_CANDIDATES", 8)       # Límite máximo de seguridad de BOEs candidatos a procesar por titulación

# Aliases canónicos para validación curricular
CREDITOS_TOTALES_GRADO = GRADO_STANDARD_ECTS
CREDITOS_TOTALES_GRADO_MIN = GRADO_STANDARD_ECTS
CREDITOS_TOTALES_MASTER_HABILITANTE = 90
CREDITOS_TOTALES_MASTER_ESTANDAR = MASTER_MIN_ECTS
CREDITOS_TOTALES_MASTER_ANUAL = MASTER_MIN_ECTS
CREDITOS_TOTALES_MASTER_MIN = MASTER_MIN_ECTS
CREDITOS_TOTALES_ARQUITECTURA_MEDICINA = MEDICINA_ECTS
CREDITOS_TOTALES_VETERINARIA_ODONTOLOGIA = ESPECIALES_GRADO_ECTS
CREDITOS_TOTALES_DOBLE_GRADO_MIN = 300

# ==============================================================================
# 9. PERSISTENCIA, CHECKPOINTS Y BASES DE DATOS
# ==============================================================================
CHECKPOINT_FLUSH_INTERVAL_SECONDS = _safe_float("CRAWLER_CHECKPOINT_INTERVAL", 30.0) # Intervalo salvaguarda JSON (segundos)
SQLITE_CONNECT_TIMEOUT = _safe_float("CRAWLER_SQLITE_TIMEOUT", 30.0)                  # Timeout conexión SQLite WAL (segundos)
SUBJECT_GUIDE_CACHE_LIMIT = _safe_int("CRAWLER_SUBJECT_GUIDE_CACHE_LIMIT", 5000)

# ==============================================================================
# 10. SERVICIOS EXTERNOS Y APIS PÚBLICAS
# ==============================================================================
WIKIPEDIA_API_URL = os.getenv("CRAWLER_WIKIPEDIA_API_URL", "https://es.wikipedia.org/w/api.php")
WIKIDATA_API_URL = os.getenv("CRAWLER_WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php")

# ==============================================================================
# 11. INFERENCIA DINÁMICA DE ESQUEMAS EN PDFs DE RESOLUCIONES BOE (RD 822/2021)
# ==============================================================================
BOE_SCHEMA_CONCEPT_VOCABULARY = {
    "modulo": ["modulo", "módulo", "modul", "mòdul"],
    "materia": ["materia", "materias"],
    "asignatura": [
        "asignatura", "asignaturas", "denominación", "denominacion",
        "nombre", "actividad", "assignatura", "irakasgaia"
    ],
    "tipo": ["tipo", "carácter", "caracter", "tipus", "mota", "modalidad"],
    "creditos": ["créditos", "creditos", "crèdits", "credits", "ects", "kredituak"],
    "curso": ["curso", "curs", "año", "ano", "maila"],
    "semestre": ["semestre", "cuatrimestre", "quadrimestre", "lauhilekoa", "organización temporal", "organizacion temporal"],
    "especialidad": ["especialidad", "mención", "mencion", "itinerario"]
}

BOE_SPURIOUS_MARKERS = [
    "boletín oficial del estado", "boletin oficial", "cve: boe-", "el rector", "la rectora",
    "el decano", "la decana", "el secretario", "la secretaria", "doy fe", "ante mí",
    "distribución de créditos", "total de créditos", "rama de conocimiento", "ámbito de conocimiento",
    "centro de impartición", "menciones: no tiene", "condiciones de terminación"
]

# ==============================================================================
# 12. VOCABULARIO ACADÉMICO, STOPWORDS Y FILTROS ANTI-ESPURIOS (CENTRALIZADO)
# ==============================================================================

# Stop words en español para extracción discriminativa de lemas en títulos de grado
SPANISH_STOP_WORDS = {
    # Spanish articles, prepositions, conjunctions, generics
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "a", "al", "por", "con", "sin", "sobre", "para", "entre", "hacia", "desde", "hasta", "segun", "tras", "durante", "mediante",
    "y", "e", "o", "u", "ni", "que", "como", "donde", "cuando",
    "graduado", "graduada", "graduados", "graduadas", "grado", "grados",
    "master", "masteres", "máster", "másteres",
    "doctor", "doctora", "doctorado", "doctorados",
    "titulo", "titulos", "titulacion", "titulaciones", "título", "títulos", "titulación", "titulaciones",
    "estudio", "estudios", "plan", "planes", "oficial", "oficiales",
    "universidad", "universidades", "universitaria", "universitarias", "universitario", "universitarios",
    "conducente", "conducentes", "obtencion", "obtención", "superacion", "superación",
    "anexo", "anexos", "resolucion", "resolución", "decreto", "orden", "acuerdo",
    "centro", "centros", "facultad", "facultades", "escuela", "escuelas",
    "programa", "programas", "ensenanzas", "enseñanzas", "ensenanza", "enseñanza",
    "rama", "ramas", "conocimiento", "conocimientos", "mencion", "mención", "menciones",
    "distribucion", "distribución", "creditos", "créditos", "resumen", "estructura",
    # Administrative & layout structural tokens
    "apartado", "materia", "materias", "asignatura", "asignaturas", "modulo", "módulo",
    "docon", "rector", "rectora", "secretario", "secretaria", "emilio", "lora", "tamayo",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    # English generics & connectives for bilingual resolutions (UC3M, UAB, UPF, etc.)
    "bachelor", "bachelors", "master", "masters", "doctor", "phd", "degree", "degrees",
    "and", "in", "of", "for", "with", "the", "an", "science", "sciences",
    "engineering", "studies", "study", "university", "business", "management", "international",
    "applied", "advanced", "official", "curriculum", "syllabus",
    # Catalan / Valenciano / Balear generics & connectives
    "grau", "graus", "estudis", "estudi", "pla", "plans", "oficial", "oficials",
    "universitat", "universitats", "universitari", "universitaris", "universitaria", "universitaries",
    "ciencies", "ciències", "socials", "juridiques", "jurídiques", "humanitats", "enginyeria", "enginyeries", "dels", "deles", "dela", "per", "amb",
    # Galician & Basque generics
    "grao", "graos", "estudos", "estudo", "plano", "planos", "universidade", "gradua", "graduak", "masterra", "unibertsitatea",
    # Adjetivos y calificadores genéricos no discriminativos (evita colisiones como Matemática Avanzada vs Arritmología Avanzada)
    "avanzado", "avanzada", "avanzados", "avanzadas", "avancat", "avancats", "avancada", "avancades", "advanced",
    "aplicado", "aplicada", "aplicados", "aplicadas", "aplicat", "aplicats", "applied",
    "fundamental", "fundamentales", "basic", "basico", "basica",
    "contemporaneo", "contemporanea", "contemporani", "contemporania", "contemporary",
    "comparado", "comparada", "comparat", "comparats", "comparative",
    "interdisciplinar", "interdisciplinario", "interdisciplinaria", "multidisciplinar",
    "internacional", "international", "global", "europeo", "europea", "european",
    # Protocolos y artefactos web en URLs
    "http", "https", "www", "html", "htm", "php", "asp", "aspx", "pdf", 
    "com", "org", "net", "edu", "cat", "index", "web", "portal", "default",
    "site", "sites", "page", "pages", "view", "link", "param", "param1", "param2", "grau", "graus"
}

# Stopwords de títulos académicos multilingües (ES / CA / GL / EU / EN)
TITLE_STOPWORDS = {
    "grado", "grados", "graduado", "graduada", "graduats", "graduades", "grau", "graus", "grao", "graos", "gradua", "graduak", "bachelor", "undergraduate",
    "máster", "master", "másteres", "masteres", "màster", "màsters", "masterra", "masterrak", "postgrado", "posgrado", "postgrau", "posgrao", "postgraduate",
    "doctor", "doctora", "doctorado", "doctorados", "doctorat", "doctorats", "doutoramento", "doktoregoa", "doctorate", "phd",
    "universitario", "universitaria", "universitaris", "universitaries", "oficial", "oficials", "programa", "programas", "título", "titulo", "titulacion", "titulaciones", "titulacions",
    "estudio", "estudios", "estudis", "estudos", "ikasketak", "enseñanza", "ensenanza", "mención", "mencion",
    "universidad", "universidades", "universitat", "universitats", "universidade", "unibertsitatea", "university",
    "sobre", "entre", "para", "como", "esta", "este", "estos", "estas", "del", "los", "las", "por", "con", "una", "uno", "que", "sus", "mas", "más",
    "autónoma", "autonoma", "politécnica", "politecnica", "internacional", "nacional", "distancia",
    "en", "the", "and", "for", "of", "in", "to", "i", "de", "a", "el", "la", "l'", "d'", "els", "les", "o", "u",
    "avanzado", "avanzada", "avanzados", "avanzadas", "avancat", "avancats", "avancada", "avancades", "advanced",
    "aplicado", "aplicada", "aplicados", "aplicadas", "aplicat", "aplicats", "applied",
    "fundamental", "fundamentales", "basic", "basico", "basica",
    "contemporaneo", "contemporanea", "contemporani", "contemporania", "contemporary",
    "comparado", "comparada", "comparat", "comparats", "comparative",
    "http", "https", "www", "html", "htm", "php", "asp", "aspx", "pdf", "edu", "cat", "com", "org", "net"
}

# Cabeceras de tabla canónicas en planes de estudio multilingües (ES / CA / GL / EU / EN)
HEADER_KEYWORDS = [
    # Español
    "código", "codigo", "asignatura", "asignaturas", "materia", "materias", "denominación", "denominacion",
    "nombre", "créditos", "creditos", "ects", "carácter", "caracter", "tipo", "curso", "cuatrimestre", "semestre", "modulo", "módulo",
    # Català / Valencià
    "assignatura", "assignatures", "matèria", "materies", "crèdits", "credits", "caràcter", "tipus", "curs", "quadrimestre", "modul",
    # Galego
    "asineira", "asineiras", "créditos", "carácter", "ano", "cuadrimestre", "módulo",
    # Euskara
    "irakasgaia", "irakasgaiak", "kredituak", "maila", "ikasturtea", "mota", "lauhilekoa",
    # English
    "subject", "subjects", "course", "courses", "module", "credits", "type", "year", "semester", "term", "syllabus"
]

# Palabras clave y metadatos no curriculares a descartar (horarios, notas, calificaciones, trámites)
INVALID_SUBJECT_KEYWORDS = [
    # Días de la semana y horarios (Multilingüe)
    "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado",
    "dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte",
    "luns", "mércores", "venres",
    "astelehena", "asteartea", "asteazkena", "osteguna", "ostirala", "larunbata",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # Infraestructura y calendario específico
    "aula magna", "aula virtual", "número de aula", "numero de aula", "despacho",
    "horario de clases", "horari de classes", "timetable", "schedule",
    "calendario de exámenes", "calendari d'exàmens", "egutegia",
    "convocatoria ordinaria", "convocatoria extraordinaria",
    # Calificaciones, notas y trámites administrativos de secretaría (ES / CA / GL / EU / EN)
    "suspenso", "aprobado", "notable", "sobresaliente", "matrícula de honor", "matricula de honor",
    "calificación cualitativa", "calificacion cualitativa", "calificación numérica", "calificacion numerica",
    "calificación estándar", "calificacion estandar", "escala de calificaciones", "tabla de equivalencias",
    "baremo", "convalidación", "convalidacion", "reconocimiento de créditos", "reconocimiento de creditos",
    "suspes", "suspès", "aprovat", "excel·lent", "matricula d'honor", "matricula de honor",
    "qualificació qualitativa", "qualificacio qualitativa", "qualificació numèrica", "qualificacio numerica",
    "escala de qualificacions", "taula d'equivalències", "taula dequivalencies", "reconeixement de crèdits", "reconeixement de credits",
    "sobresalinte", "cualificación cualitativa", "cualificacion cualitativa", "táboa de equivalencias", "taboa de equivalencias", "recoñecemento de créditos",
    "ez-gai", "oso ondo", "bikain", "ohorezko matrikula", "kalifikazio kualitatiboa", "kalifikazio numerikoa", "kreditu-aitorpena",
    "grading scale", "qualitative grade", "numerical grade", "credit recognition",
    "buscar por", "1º apellido", "2º apellido", "listado simple", "listado detallado", "cerca per", "bilatu",
    # Oferta de plazas, notas de corte y precios administrativos
    "plazas ofertadas", "plazas de nuevo ingreso", "plazas disponibles", "places de nou ingrés", "prazas",
    "nota de corte", "notas de corte", "nota de tall", "ebaki nota", "precios públicos", "prezo por crédito",
    # Privacidad, RGPD y Políticas de Cookies
    "política de cookies", "politica de cookies", "política de privacidad", "politica de privacidad",
    "protección de datos", "proteccion de datos", "datos de carácter personal", "datos de caracter personal",
    "responsable del tratamiento", "delegado de protección", "delegado de proteccion", "dpo",
    "derechos de los interesados", "base jurídica", "base juridica", "ejercicio de derechos",
    "cookie", "cookies", "google analytics", "_ga", "_gid", "_fbp", "consentimiento", "duración de la cookie"
]

# Marcadores de fuentes y matrices tipográficas invertidas/espejadas en BOE antiguo (2009-2014)
REVERSED_SPANISH_MARKERS = [
    "oxena", "odnum", "airotsih", "soidutse", "sotidérc", "sotiderc", "odaudarg", "adaudarg",
    "retsám", "retsam", "odarg", "ohcered", "aígolocisp", "acitámrofni", "aírenigneg",
    "airenigneg", "aicneic", "lartsemes", "latot", "acisáb", "acisab", "sairotagilbo", "savitatpo", "laveidem"
]

# Marcadores para excluir plantillas de Curriculum Vitae (CVN), formularios de profesorado y proyectos de tesis
CV_EXCLUSION_MARKERS = [
    "curriculum_modelo", "curriculum_vitae", "curriculum-vitae", "cv_normalizado",
    "cvn", "modelo_normalizado", "curriculum_normalizado", "anexo_iii_curriculum",
    "proyectos_", "proyectos-grupo", "proyecto_tesis", "lineas_investigacion",
    "modelo_cv", "cv_form"
]

# Patrones de preámbulo administrativo de resoluciones rectorales/ministeriales
PREAMBLE_REJECTION_PATTERNS = [
    r"relacionados\s+a\s+continuaci[oó]n",
    r"este\s+rectorado\s+ha\s+resuelto",
    r"publicar\s+(?:el|los)\s+plan(?:es)?\s+de\s+estudios",
    r"publicaci[oó]n\s+del?\s+plan\s+de\s+estudios",
    r"aprobar\s+(?:el|los)\s+plan",
    r"haberse\s+establecido",
    r"una\s+vez\s+homologad",
    r"homologado\s+por",
    r"inscrito\s+en\s+el\s+registro",
    r"previa\s+homologaci[oó]n",
    r"consejo\s+de\s+ministros",
    r"consejo\s+de\s+gobierno",
    r"t[ií]tulos\s+oficiales\s+de\s+grado\s+siguientes",
    r"siguientes\s+ense[ñn]anzas",
    r"siguientes\s+planes"
]

# Marcadores para excluir cursos de extensión, títulos propios no oficiales y formularios administrativos
NON_OFFICIAL_COURSE_MARKERS = [
    "extension-universitaria", "cursos-extension", "precios-publicos", 
    "formacion-continua", "titulos-propios", "diploma-extension", "master-propio"
]

# Ramas o términos paraguas que por sí solos no identifican la especialidad si van acompañados
UMBRELLA_BRANCH_WORDS = {
    "ingenieria", "enginyeria", "engineering",
    "educacion", "educacio", "education",
    "comunicacion", "comunicacio", "communication",
    "administracion", "administracio", "administration",
    "ciencias", "ciencies", "sciences", "science",
    "humanidades", "humanitats", "humanities",
    "estudios", "estudis", "studies",
    "lengua", "lenguas", "llengua", "llengues", "language", "languages",
    "literatura", "literatures", "literature",
    "filologia", "filologies", "philology",
    "artes", "arts"
}

