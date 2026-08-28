import sys
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

# Asegurar que el directorio padre esté en la ruta del sistema
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from API.config import settings
    from API.routes import universidades, titulaciones, estadisticas
    from API.database.etl_loader import run_etl
    from API.security import verify_api_key
except (ImportError, AttributeError):
    from config import settings
    from routes import universidades, titulaciones, estadisticas
    from database.etl_loader import run_etl
    from security import verify_api_key

logger = logging.getLogger("unihub_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización y validación de seguridad en arranque
    settings.validate_production_security()
    yield
    # Limpieza en apagado si fuera necesario

# Inicializar la aplicación FastAPI con ciclo de vida moderno
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Manejador global de excepciones de base de datos SQLAlchemy
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Error de base de datos no controlado en {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Database Error",
            "detail": "Se ha producido un error interno en la base de datos. La transacción ha sido cancelada de forma segura."
        }
    )

# Manejador global de errores de validación
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Error de validación de petición en {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": exc.errors()
        }
    )

# Configurar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# Incluir ruteadores de la API REST
app.include_router(universidades.router)
app.include_router(titulaciones.router)
app.include_router(estadisticas.router)

@app.get("/", tags=["General"])
def root():
    return {
        "mensaje": "Bienvenido a la API REST del Registro de Universidades, Centros y Títulos (RUCT) de España",
        "version": settings.API_VERSION,
        "documentacion_swagger": "/docs",
        "documentacion_redoc": "/redoc",
        "fase": "Fase 2 - API REST & Base de Datos PostgreSQL"
    }

@app.get("/salud", tags=["General"])
def health():
    return {"status": "ok", "service": "unihub_api", "database": "not_checked"}

@app.post("/api/v1/admin/sync-etl", tags=["Administración"])
def trigger_etl_sync(api_key: str = Depends(verify_api_key)):
    """
    Sincronización reactiva en caliente: desencadena la migración ETL desde JSONs de la Fase 1
    hacia PostgreSQL. La respuesta sólo confirma éxito cuando la transacción
    completa ha finalizado, para que el crawler no publique falsos positivos.
    """
    if not run_etl():
        raise HTTPException(status_code=503, detail="La sincronización ETL no pudo completarse.")
    return {
        "status": "SUCCESS",
        "mensaje": "Migración ETL completada correctamente."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
