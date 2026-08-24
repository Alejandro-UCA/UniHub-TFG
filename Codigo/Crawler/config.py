import os

# ==============================================================================
# 1. DIRECTORIOS Y RUTAS BASE DE SISTEMA
# ==============================================================================
# Carpeta raíz del módulo Crawler
BASE_DIR = os.getenv("CRAWLER_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))

# Carpeta donde se almacenan todos los datos persistidos (JSONs, SQLite, estadísticas)
DATA_DIR = os.getenv("CRAWLER_DATA_DIR", os.path.join(BASE_DIR, "Datos"))

# Subcarpeta donde se guardan los archivos JSON individuales de cada titulación/plan de estudio
PLANES_DIR = os.getenv("CRAWLER_PLANES_DIR", os.path.join(DATA_DIR, "planes_estudio"))

# Carpeta temporal para descarga en disco de PDFs del BOE antes de su análisis por los procesos CPU
TEMP_PDF_DIR = os.getenv("CRAWLER_TEMP_PDF_DIR", os.path.join(BASE_DIR, "temp_pdfs"))

# Asegurar la existencia automática de los directorios de trabajo en disco
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PLANES_DIR, exist_ok=True)
os.makedirs(TEMP_PDF_DIR, exist_ok=True)

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

# Archivo JSON con los precios oficiales por crédito ECTS de los 18 decretos autonómicos
PRECIOS_CCAA_JSON = os.getenv("CRAWLER_PRECIOS_CCAA_JSON", os.path.join(DATA_DIR, "precios_ccaa.json"))

# Base de datos transaccional SQLite WAL para indexación ultrarrápida (0ms) y firmas SHA-256 de PDFs
CACHE_DB_PATH = os.getenv("CRAWLER_CACHE_DB_PATH", os.path.join(DATA_DIR, "unihub_cache.sqlite3"))

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
REQUEST_DELAY = float(os.getenv("CRAWLER_REQUEST_DELAY", 0.35))  # Retardo cortés entre peticiones (0.35s)
MAX_RETRIES = int(os.getenv("CRAWLER_MAX_RETRIES", 3))           # Intentos máximos por reconexión
HTTP_TIMEOUT = int(os.getenv("CRAWLER_HTTP_TIMEOUT", 30))         # Timeout de conexión HTTP en segundos
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "UniHubCrawler/1.0 (+https://github.com/Alejandro-UCA/UniHub-TFG; contacto@unihub)"
)
HTTP_POOL_CONNECTIONS = int(os.getenv("CRAWLER_HTTP_POOL_CONNECTIONS", 20))  # Tamaño del pool de hosts en caché Keep-Alive
HTTP_POOL_MAXSIZE = int(os.getenv("CRAWLER_HTTP_POOL_MAXSIZE", 10))          # Conexiones simultáneas por host
DOWNLOAD_CHUNK_SIZE = int(os.getenv("CRAWLER_CHUNK_SIZE", 8192))             # Bloque para descargas de PDF (bytes)
JITTER_MIN_SECONDS = float(os.getenv("CRAWLER_JITTER_MIN", 0.10))            # Jitter aleatorio mínimo por petición (0.10s)
JITTER_MAX_SECONDS = float(os.getenv("CRAWLER_JITTER_MAX", 0.35))            # Jitter aleatorio máximo por petición (0.35s)
HTTP_429_DEFAULT_RETRY_AFTER = int(os.getenv("CRAWLER_429_RETRY_AFTER", 30)) # Retardo fallback para HTTP 429 (30s)

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
CIRCUIT_BREAKER_FAILURES_THRESHOLD = int(os.getenv("CRAWLER_CB_FAILURES_THRESHOLD", 10))  # Fallos seguidos para activar pausa
CIRCUIT_BREAKER_PAUSE_SECONDS = int(os.getenv("CRAWLER_CB_PAUSE_SECONDS", 300))           # Duración de la pausa (5 minutos)
CIRCUIT_BREAKER_MAX_PAUSES = int(os.getenv("CRAWLER_CB_MAX_PAUSES", 3))                    # Pausas máximas antes de omitir (15 min)

# ==============================================================================
# 6. PARALELISMO Y MULTIPROCESAMIENTO (OPT-01 & OPT-03)
# ==============================================================================
CPU_WORKERS_COUNT = int(os.getenv("CRAWLER_CPU_WORKERS", max(1, min(4, os.cpu_count() or 4))))  # Pool multiproceso PDF/OCR
ASYNC_PREFETCH_WORKERS = int(os.getenv("CRAWLER_PREFETCH_WORKERS", 4))                           # Hilos precarga RUCT
WEB_CRAWLER_WORKERS = int(os.getenv("CRAWLER_WEB_WORKERS", 4))                                   # Hilos escaneo web oficial
TASK_QUEUE_MAXSIZE = int(os.getenv("CRAWLER_TASK_QUEUE_MAXSIZE", 200))                           # Tamaño máximo cola multiproceso
TASK_QUEUE_GET_TIMEOUT = int(os.getenv("CRAWLER_TASK_QUEUE_TIMEOUT", 5))                          # Timeout de lectura en cola (5s)

# ==============================================================================
# 7. PARÁMETROS DEL RASTREADOR WEB OFICIAL Y SITEMAPS (FASE 1 PARTE 2)
# ==============================================================================
WEB_ROBOTS_FALLBACK_DELAY = float(os.getenv("CRAWLER_ROBOTS_DELAY", 0.5))      # Retardo por defecto si no hay Crawl-delay
ROBOTS_CHECK_TIMEOUT = int(os.getenv("CRAWLER_ROBOTS_TIMEOUT", 10))             # Timeout para lectura de robots.txt
ROBOTS_CACHE_TTL_SECONDS = int(os.getenv("CRAWLER_ROBOTS_CACHE_TTL", 86400))    # TTL de caché robots.txt (24h RFC 9309)
SITEMAP_FETCH_TIMEOUT = int(os.getenv("CRAWLER_SITEMAP_TIMEOUT", 4))            # Timeout por candidato de Sitemap XML
WEB_SEARCH_SUBPAGES_LIMIT = int(os.getenv("CRAWLER_SUBPAGES_LIMIT", 12))       # Subpáginas máximas a inspeccionar
WEB_SEARCH_SUBPAGES_DEPTH = int(os.getenv("CRAWLER_SUBPAGES_DEPTH", 6))        # Coincidencias máximas del Sitemap
LAZY_SCANNED_PAGES_CACHE_LIMIT = int(os.getenv("CRAWLER_LAZY_LIMIT", 25))      # Páginas escaneadas en caché RAM
SPA_ACCORDION_CLICK_DELAY = float(os.getenv("CRAWLER_SPA_CLICK_DELAY", 0.35))   # Pausa tras desplegar acordeón (s)
SPA_SUBPAGE_FETCH_TIMEOUT = int(os.getenv("CRAWLER_SPA_FETCH_TIMEOUT", 15))     # Timeout para descarga de subpáginas SPA (s)
WEB_SEARCH_RETRY_DELAY = float(os.getenv("CRAWLER_WEB_SEARCH_DELAY", 0.4))      # Pausa cortés entre búsquedas de subpáginas (s)

# Parámetros del Patrón Hub-and-Spoke Catalog Indexing (Fase 1 Parte 2)
HUB_AND_SPOKE_MAX_HUBS = int(os.getenv("CRAWLER_HUB_MAX_HUBS", 45))             # Catálogos maestros, facultades y calidad a pre-indexar
HUB_AND_SPOKE_MAX_DEPTH = int(os.getenv("CRAWLER_HUB_MAX_DEPTH", 7))            # Cota máxima de profundidad en segmentos URL
HUB_AND_SPOKE_MAX_HOPS = int(os.getenv("CRAWLER_HUB_MAX_HOPS", 6))              # Cota máxima de saltos BFS entre sub-hubs de catálogo
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
    "asignaturas", "assignatures", "subjects", "materias", "guia docente", "guía docente",
    "guias docentes", "guies docents", "itinerario", "itineraris", "itinerarios", "docencia",
    "estructura", "curriculum", "syllabus", "irakasgaiak", "ikasketa-plana"
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
MAX_ORGANIC_AFFILIATED_HUBS_PER_UNIV = int(os.getenv("CRAWLER_MAX_ORGANIC_HUBS", 12))
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

PRIVATE_ECTS_MIN = float(os.getenv("CRAWLER_PRIVATE_ECTS_MIN", 15.0))          # Umbral mínimo precio ECTS privada (€)
PRIVATE_ECTS_MAX = float(os.getenv("CRAWLER_PRIVATE_ECTS_MAX", 500.0))         # Umbral máximo precio ECTS privada (€)
PRIVATE_ANNUAL_MIN = float(os.getenv("CRAWLER_PRIVATE_ANNUAL_MIN", 1000.0))    # Umbral mínimo matrícula anual privada (€)
PRIVATE_ANNUAL_MAX = float(os.getenv("CRAWLER_PRIVATE_ANNUAL_MAX", 45000.0))   # Umbral máximo matrícula anual privada (€)

# ==============================================================================
# 8. CÁLCULO DE TARIFAS PÚBLICAS SIIU Y PARÁMETROS ACADÉMICOS (FASE 1 PARTE 3)
# ==============================================================================
DOCTORATE_TUTELA_CREDITS = int(os.getenv("CRAWLER_DOCTORATE_TUTELA_CREDITS", 10))   # ECTS tutela anual en Doctorado
STANDARD_YEAR_ECTS_CREDITS = int(os.getenv("CRAWLER_STANDARD_YEAR_ECTS", 60))       # ECTS de curso universitario estándar
DEFAULT_SUBJECT_ECTS = float(os.getenv("CRAWLER_DEFAULT_SUBJECT_ECTS", 6.0))        # Créditos ECTS estándar por asignatura
GRADO_STANDARD_ECTS = int(os.getenv("CRAWLER_GRADO_STANDARD_ECTS", 240))             # ECTS oficiales de un Grado estándar (4 años)
MASTER_MIN_ECTS = int(os.getenv("CRAWLER_MASTER_MIN_ECTS", 60))                      # ECTS mínimos oficiales de un Máster
MEDICINA_ECTS = int(os.getenv("CRAWLER_MEDICINA_ECTS", 360))                         # ECTS oficiales de Grado en Medicina (6 años)
ESPECIALES_GRADO_ECTS = int(os.getenv("CRAWLER_ESPECIALES_GRADO_ECTS", 300))         # ECTS de Grados de 5 años (Farmacia, Odontología, Veterinaria, Arquitectura)
MAX_BOE_CANDIDATES_PER_DEGREE = int(os.getenv("CRAWLER_MAX_BOE_CANDIDATES", 8))       # Límite máximo de seguridad de BOEs candidatos a procesar por titulación

# ==============================================================================
# 9. PERSISTENCIA, CHECKPOINTS Y BASES DE DATOS
# ==============================================================================
CHECKPOINT_FLUSH_INTERVAL_SECONDS = float(os.getenv("CRAWLER_CHECKPOINT_INTERVAL", 30.0)) # Intervalo salvaguarda JSON (segundos)
SQLITE_CONNECT_TIMEOUT = float(os.getenv("CRAWLER_SQLITE_TIMEOUT", 30.0))                  # Timeout conexión SQLite WAL (segundos)

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

