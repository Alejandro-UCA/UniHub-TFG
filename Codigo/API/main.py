import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure parent directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from routes import universidades, titulaciones, estadisticas

# Initialize FastAPI Application
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
