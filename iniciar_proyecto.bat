@echo off
REM ==============================================================================
REM Script de Lanzamiento del Proyecto UniHub (Windows Batch)
REM Construye e inicia los 4 contenedores Docker (Fases 1, 2, 3 y 4)
REM ==============================================================================
chcp 65001 >nul
title Lanzador UniHub Docker - Windows

echo ======================================================================
echo          INICIANDO PROYECTO UNIHUB EN ENTORNO DOCKER
echo ======================================================================
echo.

REM 1. Verificacion de Docker en ejecucion
docker info >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR CRITICO] Docker Desktop no esta en ejecucion.
    echo Por favor, arranca Docker Desktop en Windows y vuelve a ejecutar este script.
    echo.
    pause
    exit /b 1
)

REM 2. Navegar a la carpeta de configuracion Docker
cd /d "%~dp0Codigo\Docker"

echo [1/3] Construyendo imagenes e iniciando contenedores en segundo plano...
docker compose up --build -d
if %ERRORLEVEL% NEQ 0 (
    echo [ADVERTENCIA] Fallo 'docker compose', intentando con 'docker-compose'...
    docker-compose up --build -d
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR CRITICO] No se pudieron iniciar los contenedores Docker.
    echo Revisa los mensajes de error superiores.
    pause
    exit /b 1
)

echo.
echo [2/3] Verificando estado de los 4 contenedores...
echo.
docker compose ps

echo.
echo ======================================================================
echo       !PROYECTO UNIHUB DESPLEGADO Y EN EJECUCION EXITOSA!
echo ======================================================================
echo.
echo  * Portal Web Frontend (Fase 3):          http://localhost:80
echo  * Portal Web (Puerto Alternativo):       http://localhost:5173
echo  * API REST ^& Swagger UI (Fase 2):        http://localhost:8000/docs
echo  * Documentacion ReDoc:                   http://localhost:8000/redoc
echo  * Panel de Administracion:               http://localhost/admin
echo.
echo ======================================================================
echo Presiona cualquier tecla para salir de este script.
pause >nul
