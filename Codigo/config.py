import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "Datos")
PLANES_DIR = os.path.join(DATA_DIR, "planes_estudio")
TEMP_PDF_DIR = os.path.join(BASE_DIR, "temp_pdfs")

# Ensure required directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PLANES_DIR, exist_ok=True)
os.makedirs(TEMP_PDF_DIR, exist_ok=True)

# File Paths (ALL DATA FILES ARE .json AS REQUIRED)
UNIVERSIDADES_JSON = os.path.join(DATA_DIR, "universidades.json")
TITULACIONES_JSON = os.path.join(DATA_DIR, "titulaciones_universidad.json")
ERRORES_JSON = os.path.join(DATA_DIR, "errores_crawler.json")
CHECKPOINT_JSON = os.path.join(DATA_DIR, "checkpoint.json")

# RUCT Endpoints
URL_UNIVERSIDADES_LIST = (
    "https://www.educacion.gob.es/ruct/listauniversidades"
    "?actual=universidades&cccaa=&tipo_univ=&d-8320336-e=2&6578706f7274=1&codigoUniversidad=&consulta=1"
)

URL_ESTUDIOS_UNIV_TEMPLATE = (
    "https://www.educacion.gob.es/ruct/listaestudiosuniversidad"
    "?actual=universidades&d-1335801-e=2&6578706f7274=1&codigoUniversidad={codigo}"
)

URL_DETALLE_ESTUDIO_TEMPLATE = (
    "https://www.educacion.gob.es/ruct/estudiouniversidad.action"
    "?codigoCiclo=SC&codigoEstudio={codigo_estudio}&actual=universidad"
)

# Crawler Best Practices Configuration
REQUEST_DELAY = 1.0  # Seconds between requests to avoid overloading server
MAX_RETRIES = 3      # Max reconnection/request attempts
HTTP_TIMEOUT = 30    # Connection timeout in seconds
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
