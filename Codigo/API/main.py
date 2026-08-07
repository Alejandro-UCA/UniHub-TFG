import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Asegurar que el directorio padre esté en la ruta del sistema
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from routes import universidades, titulaciones, estadisticas

# Inicializar la aplicación FastAPI
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir ruteadores de la API REST
app.include_router(universidades.router)
app.include_router(titulaciones.router)
app.include_router(estadisticas.router)

from fastapi import BackgroundTasks
from database.etl_loader import run_etl

@app.get("/", tags=["General"])
def root():
    return {
        "mensaje": "Bienvenido a la API REST del Registro de Universidades, Centros y Títulos (RUCT) de España",
        "version": settings.API_VERSION,
        "documentacion_swagger": "/docs",
        "documentacion_redoc": "/redoc",
        "fase": "Fase 2 - API REST & Base de Datos PostgreSQL"
    }

@app.post("/api/v1/admin/sync-etl", tags=["Administración"])
def trigger_etl_sync(background_tasks: BackgroundTasks):
    """
    Sincronización reactiva en caliente: desencadena la migración ETL desde JSONs de la Fase 1
    hacia PostgreSQL en segundo plano sin reiniciar servicios.
    """
    background_tasks.add_task(run_etl)
    return {
        "status": "SUCCESS",
        "mensaje": "Migración ETL desencadenada con éxito en segundo plano."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
