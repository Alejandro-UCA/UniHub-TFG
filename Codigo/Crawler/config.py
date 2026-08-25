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

# Parámetros del Motor Autónomo de Descubrimiento de HUBs Curriculares (6 Capas)
DYNAMIC_HUB_MIN_SIBLINGS = int(os.getenv("CRAWLER_HUB_MIN_SIBLINGS", 6))        # Mínimo de enlaces hermanos homogéneos para clasificar como HUB
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
    "buscar por", "1º apellido", "2º apellido", "listado simple", "listado detallado", "cerca per", "bilatu"
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

