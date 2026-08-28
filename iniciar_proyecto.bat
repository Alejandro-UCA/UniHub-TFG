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
if errorlevel 1 (
    echo [ADVERTENCIA] Fallo 'docker compose', intentando con 'docker-compose'...
    docker-compose up --build -d
)

if errorlevel 1 (
    echo.
    echo [ERROR CRITICO] No se pudieron iniciar los contenedores Docker.
    echo Revisa los mensajes de error superiores.
    pause
    exit /b 1
)

echo.
echo [2/3] Esperando a que los servicios alcancen un estado saludable...
echo.
set /a WAIT_SECONDS=0
:wait_for_services
docker compose ps --format "{{.Service}} {{.State}} {{.Health}}" | findstr /i "exited dead unhealthy" >nul
if not errorlevel 1 goto services_failed
docker compose ps --format "{{.Service}} {{.Health}}" | findstr /i "starting" >nul
if errorlevel 1 goto services_ready
if %WAIT_SECONDS% GEQ 120 goto services_timeout
timeout /t 5 /nobreak >nul
set /a WAIT_SECONDS+=5
goto wait_for_services

:services_failed
echo [ERROR CRITICO] Al menos un contenedor esta detenido o no saludable.
exit /b 1

:services_timeout
echo [ERROR CRITICO] Los contenedores no alcanzaron estado saludable en 120 segundos.
exit /b 1

:services_ready
docker compose ps

echo.
echo ======================================================================
echo       !PROYECTO UNIHUB DESPLEGADO Y EN EJECUCION EXITOSA!
echo ======================================================================
echo.
echo  * Portal Web Frontend (Fase 3):          http://localhost:80
echo  * API REST ^& Swagger UI (Fase 2):        http://localhost/docs
echo  * Documentacion ReDoc:                   http://localhost/redoc
echo  * Panel de Administracion:               http://localhost/admin
echo.
echo ======================================================================
echo Presiona cualquier tecla para salir de este script.
pause >nul
exit /b 0
